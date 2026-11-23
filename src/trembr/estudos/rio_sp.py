"""Estudo de caso Rio–São Paulo (Fase 2): a mesma linha, um ingrediente novo por versão.

Configuração em ``config/estudos/rio_sp.yaml``; resultados em ``resultados/rio_sp/v<N>/``.

**v1 — só relevo.** Superfície de custo → corredor A* entre as pontas → suavização → greide
ótimo. Sem nenhuma indicação de caminho, acha o Vale do Paraíba.

**v2 — relevo + cidades.** O otimizador decide onde parar. Fluxo:
1. candidatas: "cidades" do REGIC dentro de uma elipse com focos nas pontas
   (``config/estudos/rio_sp.yaml``), em ordem de avanço ao longo do eixo SP → Rio;
2. relevo recortado do mosaico regional → superfície de custo (a mesma da v1);
3. corredor ótimo entre cada par de nós em ordem de avanço (Dijkstra de uma origem para vários
   destinos, ``tracado/corredor.py``);
4. fronteira de Pareto exata custo × população atendida (``tracado/paradas.py``);
5. três rotas da fronteira em detalhe (direta, joelho, máxima): suavização e greide ótimo por
   trecho entre paradas, com a estação em nível.

Custos em **km-equivalentes**: custo do corredor ÷ custo de 1 km de linha em terreno plano. Só
dependem das razões entre os preços (placeholder); não são reais e não devem ser lidos como R$.
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from pyproj import Transformer
from shapely.geometry import LineString

from trembr.config import ParamCorredor, carregar_corredor, carregar_custos, carregar_norma
from trembr.fontes import copernicus
from trembr.paths import CONFIG, PROCESSADOS, RESULTADOS, garantir
from trembr.regiao import carregar_regiao
from trembr.terreno.dem import Raster, carregar_reprojetado
from trembr.terreno.superficie_custo import superficie_custo
from trembr.tracado.corredor import caminho_minimo, caminhos_a_partir_de
from trembr.tracado.geometria import (
    comprimento_acumulado,
    raio_curvatura,
    reamostrar,
    suavizar,
)
from trembr.tracado.paradas import Rota, fronteira, joelho, suportadas
from trembr.tracado.perfil import discretizacao, otimizar_greide
from trembr.tracado.secao import NOMES_TIPO

WGS84 = "EPSG:4326"


def carregar_config(nome: str = "rio_sp") -> dict:
    with (CONFIG / "estudos" / f"{nome}.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _cidade_regic(lon: float, lat: float) -> int:
    """Código da "cidade" do REGIC que contém o ponto (via polígono do município)."""
    mun = gpd.read_parquet(PROCESSADOS / "ibge" / "municipios_2022.parquet")
    ponto = gpd.GeoSeries.from_xy([lon], [lat], crs=WGS84).to_crs(mun.crs).iloc[0]
    cod = int(mun.loc[mun.contains(ponto), "cod_ibge"].iloc[0])
    cid = pd.read_parquet(
        PROCESSADOS / "ibge" / "cidades.parquet", columns=["cod_ibge", "regic_cod_cidade"]
    )
    return int(cid.loc[cid["cod_ibge"] == cod, "regic_cod_cidade"].iloc[0])


def nos_do_problema(cfg: dict) -> gpd.GeoDataFrame:
    """Origem, candidatas (em ordem de avanço) e destino, no CRS métrico do estudo."""
    crs, v2 = cfg["crs"], cfg["v2"]
    para = Transformer.from_crs(WGS84, crs, always_xy=True)
    o = np.array(para.transform(cfg["origem"]["lon"], cfg["origem"]["lat"]))
    d = np.array(para.transform(cfg["destino"]["lon"], cfg["destino"]["lat"]))
    eixo = np.linalg.norm(d - o)
    pontas = {
        _cidade_regic(cfg[p]["lon"], cfg[p]["lat"]) for p in ("origem", "destino")
    }  # as próprias metrópoles das pontas não são "paradas"

    c = gpd.read_parquet(PROCESSADOS / "ibge" / "cidades_regic.parquet")
    c = c[
        c["uf"].isin(v2["ufs"])
        & (c["populacao_2022"] >= v2["populacao_min"])
        & ~c["regic_cod_cidade"].isin(pontas)
    ].to_crs(crs)
    xy = np.column_stack([c.geometry.x, c.geometry.y])
    soma = np.linalg.norm(xy - o, axis=1) + np.linalg.norm(xy - d, axis=1)
    avanco = (xy - o) @ (d - o) / eixo
    folga = v2["avanco_min_km"] * 1000
    dentro = (soma <= (1 + v2["folga_elipse"]) * eixo) & (avanco > folga) & (avanco < eixo - folga)
    c = c[dentro].assign(avanco_km=avanco[dentro] / 1000, desvio=soma[dentro] / eixo - 1)
    c = c.sort_values("avanco_km")

    linhas = [
        {"nome": cfg["origem"]["nome"], "tipo": "origem", "populacao": 0, "avanco_km": 0.0,
         "desvio": 0.0, "x": o[0], "y": o[1]},
        *[
            {"nome": r["nome"], "tipo": "candidata", "populacao": int(r["populacao_2022"]),
             "avanco_km": r["avanco_km"], "desvio": r["desvio"], "x": r.geometry.x,
             "y": r.geometry.y, "regic_nivel": r["regic_nivel"]}
            for _, r in c.iterrows()
        ],
        {"nome": cfg["destino"]["nome"], "tipo": "destino", "populacao": 0,
         "avanco_km": eixo / 1000, "desvio": 0.0, "x": d[0], "y": d[1]},
    ]  # fmt: skip
    df = pd.DataFrame(linhas)
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["x"], df["y"]), crs=crs)


def limites_dos_nos(nos: gpd.GeoDataFrame, margem_km: float) -> tuple[float, ...]:
    """Retângulo (graus) em volta dos nós, com margem medida em metros."""
    area = nos.geometry.union_all().convex_hull.buffer(margem_km * 1000)
    return tuple(gpd.GeoSeries([area], crs=nos.crs).to_crs("EPSG:4674").total_bounds)


def relevo(cfg: dict, limites: tuple[float, ...]) -> Raster:
    """DEM do estudo no CRS métrico: recorte do mosaico regional do Sudeste (``trembr dados
    relevo``) ou, se ele não existir, download só do recorte."""
    regional = copernicus.caminho_bbox(carregar_regiao("sudeste").bbox(), "glo90")
    if regional.exists():
        return carregar_reprojetado(regional, cfg["crs"], cfg["resolucao_m"], limites)
    arq = copernicus.ler_bbox(limites, "glo90")
    return carregar_reprojetado(arq, cfg["crs"], cfg["resolucao_m"])


def _celula_valida(custo: np.ndarray, lin: int, col: int, raio: int = 15) -> tuple[int, int]:
    """A célula do ponto, ou a mais próxima com custo finito (cidade na beira d'água)."""
    if np.isfinite(custo[lin, col]):
        return lin, col
    l0, l1 = max(0, lin - raio), min(custo.shape[0], lin + raio + 1)
    c0, c1 = max(0, col - raio), min(custo.shape[1], col + raio + 1)
    ll, cc = np.nonzero(np.isfinite(custo[l0:l1, c0:c1]))
    if ll.size == 0:
        raise RuntimeError(f"nenhuma célula viável perto de {(lin, col)}")
    k = np.argmin((ll + l0 - lin) ** 2 + (cc + c0 - col) ** 2)
    return int(ll[k] + l0), int(cc[k] + c0)


def matriz_de_custos(
    custo: np.ndarray, celulas: list[tuple[int, int]], res: float, custo_km_plano: float, log=print
) -> tuple[np.ndarray, dict[tuple[int, int], np.ndarray]]:
    """Custo (km-equivalentes) e caminho do corredor ótimo para cada par i < j."""
    n = len(celulas)
    matriz = np.full((n, n), np.inf)
    caminhos: dict[tuple[int, int], np.ndarray] = {}
    for i in range(n - 1):
        t0 = time.perf_counter()
        resultados = caminhos_a_partir_de(custo, celulas[i], celulas[i + 1 :], res)
        for k, (rota, total) in enumerate(resultados):
            j = i + 1 + k
            matriz[i, j] = total / custo_km_plano
            caminhos[(i, j)] = rota
        log(f"    nó {i + 1}/{n - 1}: {n - 1 - i} destinos em {time.perf_counter() - t0:.1f} s")
    return matriz, caminhos


def detalhar(
    rota: Rota,
    nos: gpd.GeoDataFrame,
    caminhos: dict[tuple[int, int], np.ndarray],
    dem: Raster,
    norma,
    custos,
    corredor: ParamCorredor,
    passo_m: float,
) -> tuple[dict, pd.DataFrame]:
    """Suaviza e calcula o greide ótimo trecho a trecho (estação em nível em cada parada)."""
    disc = discretizacao(norma, passo_m)
    partes, km_estrutura, rampa_max, s0 = [], dict.fromkeys(NOMES_TIPO.values(), 0.0), 0.0, 0.0
    for trecho, (a, b) in enumerate(itertools.pairwise(rota.nos)):
        celulas = caminhos[(a, b)]
        xy = dem.lc_para_xy(celulas[:, 0], celulas[:, 1])
        sv = corredor.suavizacao
        xy = suavizar(xy, sv.tolerancia_m, sv.iteracoes) if len(xy) > 2 else xy
        xy, _ = reamostrar(xy, disc.passo_m)
        zg = dem.amostrar(xy)
        if not np.isfinite(zg).all():
            ok = np.isfinite(zg)
            zg = np.interp(np.arange(zg.size), np.flatnonzero(ok), zg[ok])
        perfil = otimizar_greide(zg, disc, norma, custos)
        r = perfil.resumo()
        for nome, km in r["km_por_estrutura"].items():
            km_estrutura[nome] += km
        rampa_max = max(rampa_max, r["rampa_max_usada"])
        partes.append(
            pd.DataFrame(
                {
                    "trecho": trecho,
                    "s_m": s0 + perfil.s_m,
                    "x": xy[:, 0],
                    "y": xy[:, 1],
                    "z_terreno": perfil.z_terreno,
                    "z_trilho": perfil.z_trilho,
                    "estrutura": [NOMES_TIPO[int(t)] for t in perfil.tipo],
                }
            )
        )
        s0 += r["extensao_km"] * 1000
    tab = pd.concat(partes, ignore_index=True)
    xy = tab[["x", "y"]].to_numpy()
    raio = raio_curvatura(xy)
    extensao = float(s0 / 1000)
    reta = float(
        np.hypot(*(nos.iloc[-1][["x", "y"]].to_numpy() - nos.iloc[0][["x", "y"]].to_numpy())) / 1000
    )
    resumo = {
        "paradas": [nos.iloc[k]["nome"] for k in rota.paradas],
        "n_paradas": len(rota.paradas),
        "populacao_atendida": int(rota.beneficio),
        "custo_corredor_km_eq": round(rota.custo, 1),
        "extensao_km": round(extensao, 1),
        "sinuosidade": round(extensao / reta, 3),
        "km_por_estrutura": {k: round(v, 1) for k, v in km_estrutura.items()},
        "pct_por_estrutura": {k: round(100 * v / extensao, 1) for k, v in km_estrutura.items()},
        "rampa_max_usada": rampa_max,
        "raio_horizontal_min_m": round(float(raio.min())),
        "km_abaixo_raio_min": round(
            float((raio < norma.raio_horizontal_min_m).sum() * disc.passo_m / 1000), 1
        ),
    }
    return resumo, tab


def rodar_v2(nome_cfg: str = "rio_sp", log=print) -> tuple[dict, Path]:
    """v2: relevo + cidades. Fronteira de Pareto das paradas e três rotas em destaque."""
    t0 = time.perf_counter()
    cfg = carregar_config(nome_cfg)
    norma, custos = carregar_norma(cfg["norma"]), carregar_custos(cfg["custos"])
    corredor = carregar_corredor(cfg["corredor"])
    saida = garantir(RESULTADOS / nome_cfg / "v2")

    log("1/5 candidatas (REGIC, elipse com focos nas pontas)…")
    nos = nos_do_problema(cfg)
    for _, r in nos.iterrows():
        log(
            f"    {r['avanco_km']:6.1f} km  {r['nome']}  {r['populacao']:>11,}  desvio {r['desvio']:.0%}"
        )

    log("2/5 relevo e superfície de custo…")
    dem = relevo(cfg, limites_dos_nos(nos, cfg["v2"]["margem_km"]))
    custo = superficie_custo(dem, norma, custos, corredor)
    log(f"    {dem.dados.shape[1]}×{dem.dados.shape[0]} células de {dem.resolucao:.0f} m")

    log("3/5 corredor ótimo entre cada par de nós (Dijkstra)…")
    celulas = [
        _celula_valida(custo, *dem.xy_para_lc(x, y))
        for x, y in zip(nos["x"], nos["y"], strict=True)
    ]
    km_plano = custos.precos.via_e_sistemas_m * 1000
    matriz, caminhos = matriz_de_custos(custo, celulas, dem.resolucao, km_plano, log)

    log("4/5 fronteira de Pareto custo × população atendida…")
    rotas = fronteira(matriz, nos["populacao"].to_numpy(float))
    sup = suportadas(rotas)
    limite = rotas[0].custo * (1 + cfg["v2"]["tolerancia_no_caminho"])
    no_caminho = max((r for r in rotas if r.custo <= limite), key=lambda r: r.beneficio)
    destaques = {
        "direta": rotas[0],
        "no_caminho": no_caminho,
        "joelho": joelho(rotas),
        "maxima": rotas[-1],
    }
    log(f"    {len(rotas)} rotas na fronteira ({len(sup)} suportadas)")

    log("5/5 greide ótimo das rotas em destaque…")
    resumos, perfis = {}, []
    for nome, rota in destaques.items():
        resumos[nome], tab = detalhar(
            rota, nos, caminhos, dem, norma, custos, corredor, cfg["passo_m"]
        )
        perfis.append(tab.assign(rota=nome))
        log(f"    {nome}: {resumos[nome]['n_paradas']} paradas, {resumos[nome]['extensao_km']} km")

    tabela = pd.DataFrame(
        [
            {
                "custo_km_eq": r.custo,
                "populacao_atendida": int(r.beneficio),
                "n_paradas": len(r.paradas),
                "suportada": r in sup,
                "paradas": " → ".join(nos.iloc[k]["nome"] for k in r.paradas),
            }
            for r in rotas
        ]
    )
    tabela.to_csv(saida / "fronteira.csv", index=False, encoding="utf-8")
    perfis = pd.concat(perfis, ignore_index=True)
    perfis.to_parquet(saida / "perfis.parquet")
    gpd.GeoDataFrame(
        {"rota": list(destaques)},
        geometry=[
            LineString(perfis.loc[perfis["rota"] == n, ["x", "y"]].to_numpy()) for n in destaques
        ],
        crs=cfg["crs"],
    ).to_parquet(saida / "rotas.parquet")
    nos.drop(columns="geometry").to_csv(saida / "nos.csv", index=False, encoding="utf-8")

    resumo = {
        "versao": "v2 — relevo + cidades",
        "n_candidatas": int((nos["tipo"] == "candidata").sum()),
        "n_rotas_fronteira": len(rotas),
        "n_rotas_suportadas": len(sup),
        "destaques": resumos,
        "custo_unidade": "km-equivalentes de linha em terreno plano (razões de preço placeholder)",
        "dem": "copernicus_glo90",
        "crs": cfg["crs"],
        "tempo_execucao_s": round(time.perf_counter() - t0, 1),
    }
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    from trembr.estudos.figuras import figura_fronteira, figura_mapa_rotas

    figura_fronteira(rotas, sup, destaques, nos, saida / "fronteira.png")
    figura = figura_mapa_rotas(dem, nos, perfis, destaques, resumos, saida / "mapa.png")
    return resumo, figura


def rodar_v1(nome_cfg: str = "rio_sp", log=print) -> tuple[dict, Path]:
    """v1: só relevo. Corredor A* entre as pontas, suavização e greide ótimo."""
    t0 = time.perf_counter()
    cfg = carregar_config(nome_cfg)
    norma, custos = carregar_norma(cfg["norma"]), carregar_custos(cfg["custos"])
    corredor = carregar_corredor(cfg["corredor"])
    saida = garantir(RESULTADOS / nome_cfg / "v1")

    log("1/5 relevo (recorte do mosaico regional)…")
    dem = relevo(cfg, tuple(cfg["v1"]["recorte"]))
    log(f"    {dem.dados.shape[1]}×{dem.dados.shape[0]} células de {dem.resolucao:.0f} m")

    log("2/5 superfície de custo (rugosidade + excesso de declividade)…")
    custo = superficie_custo(dem, norma, custos, corredor)

    log("3/5 corredor de menor custo (A*, 16 direções)…")
    para = Transformer.from_crs(WGS84, cfg["crs"], always_xy=True)
    pontas = [para.transform(cfg[p]["lon"], cfg[p]["lat"]) for p in ("origem", "destino")]
    o, d = (_celula_valida(custo, *dem.xy_para_lc(x, y)) for x, y in pontas)
    rota, _ = caminho_minimo(custo, o, d, dem.resolucao)

    log("4/5 suavização e estaqueamento…")
    sv = corredor.suavizacao
    xy = suavizar(dem.lc_para_xy(rota[:, 0], rota[:, 1]), sv.tolerancia_m, sv.iteracoes)
    disc = discretizacao(norma, cfg["passo_m"])
    xy, _ = reamostrar(xy, disc.passo_m)
    zg = dem.amostrar(xy)
    if not np.isfinite(zg).all():
        ok = np.isfinite(zg)
        zg = np.interp(np.arange(zg.size), np.flatnonzero(ok), zg[ok])

    log(f"5/5 greide ótimo: {zg.size} estacas a cada {disc.passo_m:.2f} m…")
    perfil = otimizar_greide(zg, disc, norma, custos)
    raio = raio_curvatura(xy)
    reta_km = float(np.hypot(*(xy[-1] - xy[0])) / 1000)
    resumo = perfil.resumo() | {
        "versao": "v1 — só relevo",
        "norma": cfg["norma"],
        "dem": "copernicus_glo90",
        "crs": cfg["crs"],
        "raio_horizontal_min_m": float(raio.min()),
        "km_abaixo_raio_min": float(
            (raio < norma.raio_horizontal_min_m).sum() * disc.passo_m / 1000
        ),
        "distancia_reta_km": reta_km,
        "sinuosidade": float(comprimento_acumulado(xy)[-1] / 1000 / reta_km),
        "tempo_execucao_s": round(time.perf_counter() - t0, 1),
    }

    gpd.GeoDataFrame(
        {"rota": ["direta"], "norma": [cfg["norma"]]}, geometry=[LineString(xy)], crs=cfg["crs"]
    ).to_parquet(saida / "rotas.parquet")
    pd.DataFrame(
        {
            "s_m": perfil.s_m,
            "x": xy[:, 0],
            "y": xy[:, 1],
            "z_terreno": perfil.z_terreno,
            "z_trilho": perfil.z_trilho,
            "estrutura": [NOMES_TIPO[int(t)] for t in perfil.tipo],
        }
    ).to_parquet(saida / "perfis.parquet")
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    from trembr.estudos.figuras import figura_tracado

    velocidade = f"{norma.velocidade_projeto_kmh:.0f} km/h"
    figura = figura_tracado(
        dem,
        xy,
        perfil,
        resumo,
        titulo=f"São Paulo ↔ Rio de Janeiro, v1: só relevo ({velocidade})",
        rotulos=(cfg["origem"]["nome"], cfg["destino"]["nome"]),
        caminho=saida / "mapa.png",
    )
    return resumo, figura


VERSOES = {1: rodar_v1, 2: rodar_v2}


def rodar(versao: int, nome_cfg: str = "rio_sp", log=print) -> tuple[dict, Path]:
    """Roda uma versão do estudo (1 = só relevo, 2 = relevo + cidades)."""
    if versao not in VERSOES:
        raise ValueError(f"versão {versao} não existe; disponíveis: {sorted(VERSOES)}")
    return VERSOES[versao](nome_cfg, log)

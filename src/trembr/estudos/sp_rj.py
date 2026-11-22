"""Estudo de caso 1 — São Paulo ↔ Rio de Janeiro (ponta a ponta, exploratório).

Encadeia: DEM (Copernicus GLO-90 por streaming) → superfície de custo → corredor A* →
suavização → estaqueamento → greide ótimo (programação dinâmica) → quantitativos → figura.

Pontas aproximadas nas estações previstas no projeto do TAV (Campo de Marte e Leopoldina),
para permitir comparação futura com o estudo oficial (catálogo: estudos_tav_rj_sp).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import LineString

from trembr.config import carregar_custos, carregar_norma
from trembr.crs import epsg_utm_sirgas
from trembr.fontes import copernicus
from trembr.graficos import figura_tracado
from trembr.paths import RESULTADOS, garantir
from trembr.terreno.dem import carregar_reprojetado
from trembr.terreno.superficie_custo import superficie_custo
from trembr.tracado.corredor import caminho_minimo
from trembr.tracado.geometria import comprimento_acumulado, raio_curvatura, reamostrar, suavizar
from trembr.tracado.perfil import discretizacao, otimizar_greide
from trembr.tracado.secao import NOMES_TIPO


@dataclass(frozen=True)
class Ponto:
    nome: str
    lon: float
    lat: float


ORIGEM = Ponto("São Paulo (Campo de Marte)", -46.637, -23.509)
DESTINO = Ponto("Rio de Janeiro (Leopoldina)", -43.211, -22.903)
BBOX = (-47.0, -23.85, -42.95, -22.25)


def rodar(
    norma_id: str = "as350", custos_id: str = "referencia", passo_m: float = 100.0, log=print
) -> tuple[dict, Path]:
    t0 = time.perf_counter()
    norma, custos = carregar_norma(norma_id), carregar_custos(custos_id)
    saida = garantir(RESULTADOS / f"sp_rj_{norma_id}")

    log("1/6 DEM Copernicus GLO-90 (streaming dos tiles necessários)…")
    arq_dem = copernicus.ler_bbox(BBOX, "glo90")
    crs = epsg_utm_sirgas((BBOX[0] + BBOX[2]) / 2, (BBOX[1] + BBOX[3]) / 2)
    dem = carregar_reprojetado(arq_dem, crs, 90.0)
    log(f"    {dem.dados.shape[1]}×{dem.dados.shape[0]} células de 90 m em {crs}")

    log("2/6 superfície de custo (rugosidade + excesso de declividade)…")
    custo = superficie_custo(dem, norma, custos)

    log("3/6 corredor de menor custo (A*, 16 direções)…")
    para_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    o_xy = para_utm.transform(ORIGEM.lon, ORIGEM.lat)
    d_xy = para_utm.transform(DESTINO.lon, DESTINO.lat)
    rota, _ = caminho_minimo(custo, dem.xy_para_lc(*o_xy), dem.xy_para_lc(*d_xy), dem.resolucao)

    log("4/6 suavização e estaqueamento…")
    xy_suave = suavizar(dem.lc_para_xy(rota[:, 0], rota[:, 1]), tolerancia_m=500.0, iteracoes=5)
    disc = discretizacao(norma, passo_m)
    xy, _ = reamostrar(xy_suave, disc.passo_m)
    zg = dem.amostrar(xy)
    if not np.isfinite(zg).all():
        validos = np.isfinite(zg)
        zg = np.interp(np.arange(zg.size), np.flatnonzero(validos), zg[validos])

    log(
        f"5/6 greide ótimo: {zg.size} estacas a cada {disc.passo_m:.2f} m, rampa ≤ {1000 * disc.rampa_max_efetiva:.0f}‰, R_v ≥ {norma.raio_vertical_min_m:.0f} m…"
    )
    perfil = otimizar_greide(zg, disc, norma, custos)

    raio = raio_curvatura(xy)
    reta_km = float(np.hypot(*(xy[-1] - xy[0])) / 1000)
    resumo = perfil.resumo() | {
        "norma": norma_id,
        "dem": "copernicus_glo90",
        "crs": crs,
        "raio_horizontal_min_m": float(raio.min()),
        "km_abaixo_raio_min": float(
            (raio < norma.raio_horizontal_min_m).sum() * disc.passo_m / 1000
        ),
        "distancia_reta_km": reta_km,
        "sinuosidade": float(comprimento_acumulado(xy)[-1] / 1000 / reta_km),
        "tempo_execucao_s": round(time.perf_counter() - t0, 1),
    }

    log("6/6 salvando resultados e figura…")
    gpd.GeoDataFrame(
        {"nome": ["SP–RJ"], "norma": [norma_id]}, geometry=[LineString(xy)], crs=crs
    ).to_parquet(saida / "tracado.parquet")
    pd.DataFrame(
        {
            "s_m": perfil.s_m,
            "x": xy[:, 0],
            "y": xy[:, 1],
            "z_terreno": perfil.z_terreno,
            "z_trilho": perfil.z_trilho,
            "estrutura": [NOMES_TIPO[int(t)] for t in perfil.tipo],
            "custo_infra_r_por_m": perfil.custo_infra_m,
        }
    ).to_parquet(saida / "perfil.parquet")
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    figura = figura_tracado(
        dem,
        xy,
        perfil,
        resumo,
        titulo=f"São Paulo ↔ Rio de Janeiro — primeiro traçado exploratório ({norma.velocidade_projeto_kmh:.0f} km/h)",
        rotulos=(ORIGEM.nome, DESTINO.nome),
        caminho=saida / "figura.png",
    )
    return resumo, figura

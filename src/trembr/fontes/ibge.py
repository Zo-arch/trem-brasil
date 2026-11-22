"""IBGE: mapa base (país, UFs, municípios) + população do Censo 2022."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd

from trembr import proveniencia
from trembr.crs import SIRGAS2000
from trembr.paths import BRUTOS, PROCESSADOS, garantir

URL_POPULACAO = "https://apisidra.ibge.gov.br/values/t/4709/n6/all/v/93/p/2022"
_URL_MALHAS = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?formato=application/vnd.geo+json&qualidade=intermediaria"
)
URL_MALHA_PAIS = _URL_MALHAS
URL_MALHA_UF = _URL_MALHAS + "&intrarregiao=UF"
URL_MALHA = _URL_MALHAS + "&intrarregiao=municipio"
LICENCA = "IBGE — dados públicos (Lei de Acesso à Informação); citar a fonte"

UF_SIGLA = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}  # fmt: skip

UF_NOME = {
    "RO": "Rondônia", "AC": "Acre", "AM": "Amazonas", "RR": "Roraima", "PA": "Pará",
    "AP": "Amapá", "TO": "Tocantins", "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará",
    "RN": "Rio Grande do Norte", "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas",
    "SE": "Sergipe", "BA": "Bahia", "MG": "Minas Gerais", "ES": "Espírito Santo",
    "RJ": "Rio de Janeiro", "SP": "São Paulo", "PR": "Paraná", "SC": "Santa Catarina",
    "RS": "Rio Grande do Sul", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
    "GO": "Goiás", "DF": "Distrito Federal",
}  # fmt: skip

# O primeiro dígito do código IBGE da UF é a grande região.
REGIAO_POR_DIGITO = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}


def baixar(url: str, destino: Path, fonte_id: str, forcar: bool) -> Path:
    if destino.exists() and not forcar:
        return destino
    with httpx.Client(
        timeout=300, follow_redirects=True, headers={"User-Agent": "trembr/0.1"}
    ) as c:
        r = c.get(url)
        r.raise_for_status()
    destino.write_bytes(r.content)
    proveniencia.registrar(destino, fonte_id=fonte_id, urls=[url], licenca=LICENCA)
    return destino


def preparar_municipios(*, forcar: bool = False) -> Path:
    """GeoParquet com código IBGE, nome, UF, população 2022 e polígono de cada município."""
    pasta = garantir(BRUTOS / "ibge")
    arq_pop = baixar(URL_POPULACAO, pasta / "sidra_4709_pop2022.json", "ibge_censo2022_pop", forcar)
    arq_malha = baixar(
        URL_MALHA, pasta / "malha_municipios.geojson", "ibge_malha_municipal", forcar
    )

    pop = pd.read_json(arq_pop, dtype=str).iloc[1:]  # 1ª linha é o cabeçalho descritivo do SIDRA
    pop = pd.DataFrame(
        {
            "cod_ibge": pop["D1C"].astype(int),
            # o SIDRA escreve "Ariquemes - RO": a UF vai para a coluna própria
            "nome": pop["D1N"].str.replace(r" - [A-Z]{2}$", "", regex=True),
            "populacao_2022": pd.to_numeric(pop["V"], errors="coerce").astype("Int64"),
        }
    )

    malha = gpd.read_file(arq_malha)
    malha = malha.set_crs(SIRGAS2000, allow_override=True)
    malha["cod_ibge"] = malha["codarea"].astype(int)
    gdf = malha[["cod_ibge", "geometry"]].merge(pop, on="cod_ibge", how="left", validate="1:1")
    gdf["uf"] = (gdf["cod_ibge"] // 100_000).map(UF_SIGLA)
    faltando = gdf["populacao_2022"].isna().sum()
    if faltando:
        print(f"aviso: {faltando} municípios da malha sem população no SIDRA")

    destino = garantir(PROCESSADOS / "ibge") / "municipios_2022.parquet"
    gdf[["cod_ibge", "nome", "uf", "populacao_2022", "geometry"]].to_parquet(destino)
    return destino


def preparar_base(*, forcar: bool = False) -> dict[str, Path]:
    """Mapa base: contorno do país, UFs e municípios (GeoParquet em SIRGAS 2000)."""
    pasta = garantir(BRUTOS / "ibge")
    saida = garantir(PROCESSADOS / "ibge")

    arq_pais = baixar(URL_MALHA_PAIS, pasta / "malha_pais.geojson", "ibge_malha_uf", forcar)
    pais = gpd.read_file(arq_pais).set_crs(SIRGAS2000, allow_override=True)
    pais = gpd.GeoDataFrame({"nome": ["Brasil"]}, geometry=[pais.union_all()], crs=SIRGAS2000)
    pais.to_parquet(saida / "pais.parquet")

    arq_ufs = baixar(URL_MALHA_UF, pasta / "malha_ufs.geojson", "ibge_malha_uf", forcar)
    ufs = gpd.read_file(arq_ufs).set_crs(SIRGAS2000, allow_override=True)
    ufs["cod_uf"] = ufs["codarea"].astype(int)
    ufs["uf"] = ufs["cod_uf"].map(UF_SIGLA)
    ufs["nome"] = ufs["uf"].map(UF_NOME)
    ufs["regiao"] = (ufs["cod_uf"] // 10).map(REGIAO_POR_DIGITO)
    if ufs[["uf", "nome", "regiao"]].isna().any().any() or len(ufs) != 27:
        raise RuntimeError(f"malha de UFs inesperada: {len(ufs)} feições")
    ufs[["cod_uf", "uf", "nome", "regiao", "geometry"]].to_parquet(saida / "ufs.parquet")

    return {
        "pais": saida / "pais.parquet",
        "ufs": saida / "ufs.parquet",
        "municipios": preparar_municipios(forcar=forcar),
    }

"""IBGE: malha municipal + população do Censo 2022 (semente da camada de demanda)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd

from trembr import proveniencia
from trembr.crs import SIRGAS2000
from trembr.paths import BRUTOS, PROCESSADOS, garantir

URL_POPULACAO = "https://apisidra.ibge.gov.br/values/t/4709/n6/all/v/93/p/2022"
URL_MALHA = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?formato=application/vnd.geo+json&qualidade=intermediaria&intrarregiao=municipio"
)
LICENCA = "IBGE — dados públicos (Lei de Acesso à Informação); citar a fonte"

UF_SIGLA = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}  # fmt: skip


def _baixar(url: str, destino: Path, fonte_id: str, forcar: bool) -> Path:
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
    arq_pop = _baixar(
        URL_POPULACAO, pasta / "sidra_4709_pop2022.json", "ibge_censo2022_pop", forcar
    )
    arq_malha = _baixar(
        URL_MALHA, pasta / "malha_municipios.geojson", "ibge_malha_municipal", forcar
    )

    pop = pd.read_json(arq_pop, dtype=str).iloc[1:]  # 1ª linha é o cabeçalho descritivo do SIDRA
    pop = pd.DataFrame(
        {
            "cod_ibge": pop["D1C"].astype(int),
            "nome": pop["D1N"].str.rsplit(" (", n=1).str[0],
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

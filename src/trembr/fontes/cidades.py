"""IBGE: cidades — sedes municipais, PIB, hierarquia urbana (REGIC 2018) e áreas urbanizadas.

Saídas em ``data/processed/ibge``:
- ``cidades.parquet``: um ponto por município (a sede, não o centroide do polígono, que em
  municípios grandes cai no meio do mato), com população 2022, PIB e nível na hierarquia urbana;
- ``areas_urbanizadas_2022.parquet``: a mancha urbana mapeada pelo IBGE em imagens de 2022.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from trembr.crs import SIRGAS2000
from trembr.fontes.ibge import baixar_ibge, preparar_municipios
from trembr.paths import BRUTOS, PROCESSADOS, garantir

_GEOFTP = "https://geoftp.ibge.gov.br/organizacao_do_territorio"
URL_LOCALIDADES = (
    f"{_GEOFTP}/estrutura_territorial/localidades/Localidades_do_Brasil/2022/"
    "Localidades_Brasil_gpkg.zip"
)
URL_PIB = "https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/last%201"
URL_REGIC = (
    f"{_GEOFTP}/divisao_regional/regioes_de_influencia_das_cidades/"
    "Regioes_de_influencia_das_cidades_2018_Resultados_definitivos/base_tabular/"
    "REGIC2018_Municipios_Hierarquia_e_regiao.xlsx"
)
URL_AREAS_URBANIZADAS = (
    f"{_GEOFTP}/tipologias_do_territorio/areas_urbanizadas_do_brasil/2022/Shapefile/"
    "AreasUrbanizadas2022_Brasil.zip"
)


def _sedes(arq_zip: Path) -> gpd.GeoDataFrame:
    """Ponto da sede de cada município (Localidades 2022)."""
    loc = pyogrio.read_dataframe(
        f"/vsizip/{arq_zip.as_posix()}/BR_localidades_2022.gpkg",
        columns=["CD_MUN", "CT_LOCALIDADE", "SCT_LOCALIDADE"],
        # Fernando de Noronha é distrito estadual, sem "Cidade", mas conta como município
        where="CT_LOCALIDADE IN ('Cidade', 'Distrito Estadual de Fernando de Noronha')",
    )
    # As capitais aparecem duas vezes ("Sede Municipal" e "Capital Estadual"): fica uma só.
    loc["capital"] = loc["SCT_LOCALIDADE"].isin(["Capital Estadual", "Capital Federal"])
    loc = loc.sort_values("capital", ascending=False).drop_duplicates("CD_MUN")
    loc["cod_ibge"] = loc["CD_MUN"].astype(int)
    return loc[["cod_ibge", "capital", "geometry"]].set_crs(SIRGAS2000, allow_override=True)


def _pib(arq_json: Path) -> pd.DataFrame:
    pib = pd.read_json(arq_json, dtype=str).iloc[1:]  # 1ª linha: cabeçalho descritivo do SIDRA
    return pd.DataFrame(
        {
            "cod_ibge": pib["D1C"].astype(int),
            "pib_mil_reais": pd.to_numeric(pib["V"], errors="coerce"),
            "pib_ano": pib["D3N"].astype(int),
        }
    ).reset_index(drop=True)


def preparar_areas_urbanizadas(*, forcar: bool = False) -> Path:
    pasta = garantir(BRUTOS / "ibge")
    arq = baixar_ibge(
        URL_AREAS_URBANIZADAS,
        pasta / "AreasUrbanizadas2022_Brasil.zip",
        "ibge_areas_urbanizadas",
        forcar,
    )
    au = pyogrio.read_dataframe(
        f"/vsizip/{arq.as_posix()}/AreasUrbanizadas2022_Brasil/"
        "AU_2026_AreasUrbanizadas_2022_Brasil.shp",
        columns=["Tipo", "Densidade", "Area_km2"],
    )
    au = au.rename(columns={"Tipo": "tipo", "Densidade": "densidade", "Area_km2": "area_km2"})
    au = au.set_crs(SIRGAS2000, allow_override=True)
    destino = garantir(PROCESSADOS / "ibge") / "areas_urbanizadas_2022.parquet"
    au.to_parquet(destino)
    return destino


def _regic(arq_xlsx: Path) -> pd.DataFrame:
    """Hierarquia urbana (REGIC 2018) por município: a que "cidade" pertence e o nível dela."""
    r = pd.read_excel(arq_xlsx, sheet_name=0, dtype=str)
    grupo = r["Hierarquia - grupo"].str.split(" - ", n=1)
    return pd.DataFrame(
        {
            "cod_ibge": r["codmun"].astype(int),
            # "cidade" do REGIC: o arranjo populacional (ex.: São Paulo/SP, com dezenas de
            # municípios) ou o próprio município, se isolado
            "regic_cod_cidade": r["codcid"].astype(int),
            "regic_cidade": r["Arranjo Populacional"].fillna(r["Município"]),
            "arranjo": r["Categoria"].str.startswith("Arranjo"),
            # membros de arranjo vêm como "1A - Integrante de Arranjo Populacional": o nível é o
            # do arranjo inteiro, e a marca de integrante já está na coluna "arranjo"
            "regic_nivel": r["Hierarquia 3"].str.split(" - ").str[0],  # 1A, 1B, 1C, 2A … 5
            "regic_grupo_ord": grupo.str[0].astype(int),  # 1 = Metrópole … 5 = Centro Local
            "regic_grupo": grupo.str[1].str.split(" - ").str[0],
        }
    )


def preparar_cidades(*, forcar: bool = False) -> dict[str, Path]:
    """Sedes + população + PIB + REGIC por município, e a agregação por "cidade" do REGIC."""
    pasta = garantir(BRUTOS / "ibge")
    sedes = _sedes(
        baixar_ibge(
            URL_LOCALIDADES, pasta / "Localidades_Brasil_gpkg.zip", "ibge_localidades", forcar
        )
    )
    pib = _pib(baixar_ibge(URL_PIB, pasta / "sidra_5938_pib.json", "ibge_pib_municipal", forcar))
    regic = _regic(
        baixar_ibge(URL_REGIC, pasta / "REGIC2018_Municipios_Hierarquia.xlsx", "ibge_regic", forcar)
    )
    mun = gpd.read_parquet(preparar_municipios(forcar=False)).drop(columns="geometry")

    cid = sedes.merge(mun, on="cod_ibge", how="inner", validate="1:1")
    cid = cid.merge(pib, on="cod_ibge", how="left", validate="1:1")
    cid = cid.merge(regic, on="cod_ibge", how="left", validate="1:1")
    if len(cid) != len(mun) or cid["regic_nivel"].isna().any():
        raise RuntimeError(
            f"junção incompleta: {len(cid)} sedes × {len(mun)} municípios; "
            f"{cid['regic_nivel'].isna().sum()} sem REGIC"
        )
    # PIB do último ano publicado ÷ população do Censo 2022 (anos podem diferir; ver pib_ano)
    cid["pib_per_capita_reais"] = 1000 * cid["pib_mil_reais"] / cid["populacao_2022"]
    saida = garantir(PROCESSADOS / "ibge")
    cid = gpd.GeoDataFrame(cid, geometry="geometry", crs=SIRGAS2000)
    cid.to_parquet(saida / "cidades.parquet")

    # Uma linha por "cidade" do REGIC; o ponto é a sede do município mais populoso dela.
    nucleo = cid.sort_values("populacao_2022", ascending=False).drop_duplicates("regic_cod_cidade")
    soma = cid.groupby("regic_cod_cidade").agg(
        populacao_2022=("populacao_2022", "sum"),
        pib_mil_reais=("pib_mil_reais", "sum"),
        pib_ano=("pib_ano", "max"),
        n_municipios=("cod_ibge", "size"),
    )
    agreg = nucleo[
        ["regic_cod_cidade", "regic_cidade", "uf", "regic_nivel", "regic_grupo",
         "regic_grupo_ord", "arranjo", "geometry"]
    ].merge(soma, left_on="regic_cod_cidade", right_index=True)  # fmt: skip
    agreg.insert(
        1,
        "nome",
        agreg["regic_cidade"]
        .str.replace(r"^Arranjo Populacional d[aeo]s? ", "", regex=True)
        .where(agreg["arranjo"], agreg["regic_cidade"] + "/" + agreg["uf"]),
    )
    agreg = gpd.GeoDataFrame(agreg, geometry="geometry", crs=SIRGAS2000)
    agreg.sort_values("populacao_2022", ascending=False).to_parquet(saida / "cidades_regic.parquet")

    return {
        "cidades": saida / "cidades.parquet",
        "cidades_regic": saida / "cidades_regic.parquet",
        "areas_urbanizadas": preparar_areas_urbanizadas(forcar=forcar),
    }

"""Áreas protegidas: unidades de conservação (CNUC/MMA) e terras indígenas (FUNAI).

Classes para o traçado (Fase 2 · v3):
- ``protecao_integral`` (parque, estação ecológica, reserva biológica, monumento natural,
  refúgio de vida silvestre): barreira;
- ``uso_sustentavel`` (floresta nacional, RESEX, RDS, ARIE, RPPN…): custo extra de licenciamento;
- ``apa`` (Área de Proteção Ambiental): a mais permissiva; licenciamento comum, com condicionantes;
- terras indígenas: barreira.

As TIs vêm do GeoServer da FUNAI, que recusa downloads automatizados. Baixe no navegador, pela
página oficial (``PAGINA_TIS``), o shapefile nacional ou os dos estados da região, e salve os
.zip em ``data/raw/funai/``.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from trembr import proveniencia
from trembr.crs import SIRGAS2000
from trembr.fontes.baixar import baixar
from trembr.paths import BRUTOS, PROCESSADOS, garantir

URL_CNUC = (
    "https://dados.mma.gov.br/dataset/44b6dc8a-dc82-4a84-8d95-1b0da7c85dac/resource/"
    "6ba9a557-87e8-4882-acb7-b3e0f0ea192d/download/shp_cnuc_2025_08.zip"
)
PAGINA_TIS = "https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas"
PASTA_TIS = BRUTOS / "funai"  # um ou mais .zip (nacional ou por UF) baixados da PAGINA_TIS
# Colunas lidas do CNUC: os campos de texto longos (atos legais) vêm cortados no meio de um
# caractere UTF-8 no limite de 254 bytes do DBF e quebram a leitura.
COLUNAS_CNUC = ["cd_cnuc", "nome_uc", "grupo", "categoria", "esfera", "cria_ano", "ha_total"]


def classe_uc(grupo: str, categoria: str) -> str:
    if grupo == "Proteção Integral":
        return "protecao_integral"
    if categoria == "Área de Proteção Ambiental":
        return "apa"
    return "uso_sustentavel"


def _ucs(arq_zip: Path) -> gpd.GeoDataFrame:
    shp = next(n for n in pyogrio.list_layers(f"/vsizip/{arq_zip.as_posix()}")[:, 0]
               if not n.endswith("_pontos"))  # fmt: skip
    ucs = pyogrio.read_dataframe(
        f"/vsizip/{arq_zip.as_posix()}/{shp}.shp", columns=COLUNAS_CNUC
    ).set_crs(SIRGAS2000, allow_override=True)
    ucs["classe"] = [classe_uc(g, c) for g, c in zip(ucs["grupo"], ucs["categoria"], strict=True)]
    ucs["ha_total"] = pd.to_numeric(ucs["ha_total"], errors="coerce")  # vem como texto no DBF
    return ucs


def _tis(zips: list[Path]) -> gpd.GeoDataFrame:
    partes = []
    for z in zips:
        camada = pyogrio.list_layers(f"/vsizip/{z.as_posix()}")[0, 0]
        partes.append(pyogrio.read_dataframe(f"/vsizip/{z.as_posix()}/{camada}.shp"))
    tis = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=partes[0].crs)
    # baixadas por UF, as TIs que cruzam divisas vêm repetidas
    if "terrai_cod" in tis:
        tis = tis.drop_duplicates("terrai_cod")
    else:
        tis = tis[~tis.geometry.to_wkb().duplicated()]
    nomes = {"terrai_nom": "nome", "etnia_nome": "etnia", "fase_ti": "fase", "uf_sigla": "uf"}
    tis = tis.rename(columns={k: v for k, v in nomes.items() if k in tis})
    manter = [c for c in ("nome", "etnia", "fase", "uf") if c in tis]
    return tis[[*manter, "geometry"]].to_crs(SIRGAS2000)


def preparar_areas_protegidas(*, forcar: bool = False, log=print) -> dict[str, Path]:
    arquivos = {}
    cnuc = baixar(
        URL_CNUC,
        BRUTOS / "mma" / "shp_cnuc_2025_08.zip",
        fonte_id="cnuc_ucs",
        licenca="Creative Commons Atribuição (dados.mma.gov.br)",
        forcar=forcar,
        log=log,
    )
    arquivos["ucs"] = garantir(PROCESSADOS / "mma") / "unidades_conservacao.parquet"
    _ucs(cnuc).to_parquet(arquivos["ucs"])

    zips = sorted(PASTA_TIS.glob("*.zip"))
    for z in zips:  # baixados à mão: a proveniência registra a página de origem e o hash
        if not proveniencia.caminho_proveniencia(z).exists():
            proveniencia.registrar(
                z,
                fonte_id="funai_ti",
                urls=[PAGINA_TIS],
                licenca="Pública (FUNAI)",
                extra={"obtencao": "download manual pelo navegador, na página oficial"},
            )
    if zips:
        arquivos["tis"] = garantir(PROCESSADOS / "funai") / "terras_indigenas.parquet"
        _tis(zips).to_parquet(arquivos["tis"])
    else:
        log(
            "  terras indígenas: o GeoServer da FUNAI recusa download automatizado. Na página\n"
            f"    {PAGINA_TIS}\n  baixe o shapefile das TIs (nacional ou por UF) e salve os .zip "
            f"em {PASTA_TIS}; depois rode de novo."
        )
    return arquivos


def resumo_ucs(ucs: gpd.GeoDataFrame) -> pd.DataFrame:
    return ucs.groupby("classe").agg(n=("cd_cnuc", "size"), ha=("ha_total", "sum"))

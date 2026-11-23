"""OpenStreetMap (extratos do Geofabrik): rodovias, ferrovias, estações e aeroportos existentes.

Para que servem (decisão de 2026-11-22, docs/roteiro.md): contexto no mapa, "atalho" no traçado
(andar ao lado de uma faixa já aberta) e concorrência (tempo de carro e de ônibus).

Fluxo: extrato regional ``.osm.pbf`` → ``osmium tags-filter`` (só as tags que interessam; de
~900 MB para dezenas de MB) → GDAL, driver OSM → GeoParquet em ``data/processed/osm``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import yaml

from trembr.crs import SIRGAS2000
from trembr.fontes.baixar import baixar
from trembr.paths import BRUTOS, CONFIG, INTERMEDIARIOS, PROCESSADOS, garantir

GEOFABRIK = "https://download.geofabrik.de"
LICENCA = "ODbL 1.0 — © colaboradores do OpenStreetMap (openstreetmap.org/copyright)"

RODOVIAS = {
    # tag highway → classe do estudo
    "motorway": "autoestrada", "motorway_link": "autoestrada",
    "trunk": "troncal", "trunk_link": "troncal",
    "primary": "principal", "primary_link": "principal",
    "secondary": "secundaria", "secondary_link": "secundaria",
}  # fmt: skip
FERROVIAS = {
    "rail": "em_operacao", "narrow_gauge": "em_operacao",
    "light_rail": "urbana", "subway": "urbana",
    "construction": "em_obras",
    "disused": "desativada", "abandoned": "desativada",
}  # fmt: skip
ETIQUETAS_EXTRAS = ["ref", "maxspeed", "lanes", "usage", "service", "gauge", "electrified",
                    "operator", "iata", "icao", "aerodrome:type"]  # fmt: skip

_HSTORE = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')


def ler_hstore(texto: str | None) -> dict[str, str]:
    """``"ref"=>"BR-116","maxspeed"=>"110"`` → dict (formato do campo other_tags do GDAL)."""
    if not isinstance(texto, str) or not texto:  # ausente vem como None ou NaN
        return {}
    return {k.replace('\\"', '"'): v.replace('\\"', '"') for k, v in _HSTORE.findall(texto)}


def extratos(regiao_id: str) -> list[str]:
    with (CONFIG / "regioes.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)["regioes"][regiao_id]["osm_geofabrik"]


def _filtrar(pbf: Path, destino: Path) -> Path:
    if shutil.which("osmium") is None:
        raise RuntimeError("osmium-tool não encontrado no ambiente (pixi add osmium-tool)")
    # chamado pelo nome: no Windows o osmium recusa o argv[0] "osmium.EXE" que o which devolve
    osmium = "osmium"
    filtros = [
        "w/highway=" + ",".join(RODOVIAS),
        "w/railway=" + ",".join(FERROVIAS),
        "n/railway=station,halt",
        "nwr/aeroway=aerodrome",
    ]
    r = subprocess.run(
        [osmium, "tags-filter", str(pbf), *filtros, "-o", str(destino), "--overwrite"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"osmium falhou ({r.returncode}): {r.stderr.strip()}")
    return destino


def _ler(
    pbf: Path, camada: str, colunas: list[str], etiquetas: list[str] = ETIQUETAS_EXTRAS
) -> gpd.GeoDataFrame:
    """Lê uma camada do driver OSM do GDAL e abre o ``other_tags`` nas ``etiquetas`` pedidas."""
    gdf = pyogrio.read_dataframe(pbf, layer=camada, columns=[*colunas, "other_tags"])
    extras = pd.DataFrame([ler_hstore(t) for t in gdf["other_tags"]], index=gdf.index)
    for etiqueta in etiquetas:
        gdf[etiqueta.replace(":", "_")] = extras[etiqueta] if etiqueta in extras else None
    return gdf.drop(columns="other_tags").set_crs(SIRGAS2000, allow_override=True)


def preparar_transporte(regiao_id: str = "sudeste", *, forcar: bool = False, log=print) -> dict:
    """Rodovias, ferrovias, estações e aeroportos da região → GeoParquet."""
    saida = garantir(PROCESSADOS / "osm")
    partes: dict[str, list[gpd.GeoDataFrame]] = {
        "rodovias": [], "ferrovias": [], "estacoes": [], "aeroportos": []
    }  # fmt: skip
    for extrato in extratos(regiao_id):
        nome = extrato.rsplit("/", 1)[-1]
        pbf = baixar(
            f"{GEOFABRIK}/{extrato}-latest.osm.pbf",
            BRUTOS / "osm" / f"{nome}-latest.osm.pbf",
            fonte_id="osm_brasil",
            licenca=LICENCA,
            forcar=forcar,
            log=log,
        )
        log(f"  filtrando {pbf.name} com osmium…")
        filtrado = _filtrar(pbf, garantir(INTERMEDIARIOS / "osm") / f"{nome}-transporte.osm.pbf")

        linhas = _ler(filtrado, "lines", ["osm_id", "name", "highway", "railway"])
        rod = linhas[linhas["highway"].isin(RODOVIAS)].copy()
        rod["classe"] = rod["highway"].map(RODOVIAS)
        rod["maxspeed_kmh"] = pd.to_numeric(rod["maxspeed"], errors="coerce")
        partes["rodovias"].append(rod.drop(columns="railway"))
        fer = linhas[linhas["railway"].isin(FERROVIAS)].copy()
        fer["situacao"] = fer["railway"].map(FERROVIAS)
        partes["ferrovias"].append(fer.drop(columns="highway"))

        pontos = _ler(
            filtrado, "points", ["osm_id", "name"], [*ETIQUETAS_EXTRAS, "railway", "aeroway"]
        )
        partes["estacoes"].append(pontos[pontos["railway"].isin(["station", "halt"])])

        areas = _ler(filtrado, "multipolygons", ["osm_id", "osm_way_id", "name", "aeroway"])
        aero = areas[areas["aeroway"] == "aerodrome"].copy()
        aero["geometry"] = aero.geometry.representative_point()
        aero_pt = pontos[pontos["aeroway"] == "aerodrome"]
        partes["aeroportos"].append(pd.concat([aero, aero_pt], ignore_index=True))

    arquivos = {}
    for tipo, lista in partes.items():
        gdf = gpd.GeoDataFrame(pd.concat(lista, ignore_index=True), crs=SIRGAS2000)
        gdf = gdf.loc[:, gdf.notna().any()]  # descarta colunas sempre vazias
        arquivos[tipo] = saida / f"{regiao_id}_{tipo}.parquet"
        gdf.to_parquet(arquivos[tipo])
    return arquivos

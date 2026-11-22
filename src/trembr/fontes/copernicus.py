"""Copernicus DEM (GLO-30 e GLO-90) lido por streaming dos COGs públicos na AWS.

Não baixamos tiles inteiros: o GDAL faz requisições HTTP de intervalo e lê só a janela pedida.
Isso é o que torna viável trabalhar com 30 m no Brasil inteiro num disco de notebook.

Atenção científica: o Copernicus é um modelo de SUPERFÍCIE (DSM) — inclui copa de árvores e
prédios. Em mata atlântica isso enviesa a cota para cima em 10–30 m. Para o traçado final usar
um modelo de TERRENO (ANADEM; ver data/catalogo.yaml). Aqui ele serve para triagem.

Nomes dos tiles referem-se ao canto sudoeste: ``S23_00_W044_00`` cobre 23°S–22°S, 44°W–43°W.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.merge import merge

from trembr import proveniencia
from trembr.paths import BRUTOS, garantir

PRODUTOS = {"glo30": ("copernicus-dem-30m", "10"), "glo90": ("copernicus-dem-90m", "30")}
LICENCA = (
    "Copernicus DEM — produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus "
    "Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA"
)
GDAL_HTTP = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "2",
}

Bbox = tuple[float, float, float, float]  # oeste, sul, leste, norte (graus)


def nome_tile(lat_sw: int, lon_sw: int, produto: str) -> str:
    _, cod = PRODUTOS[produto]
    ns = "N" if lat_sw >= 0 else "S"
    ew = "E" if lon_sw >= 0 else "W"
    return f"Copernicus_DSM_COG_{cod}_{ns}{abs(lat_sw):02d}_00_{ew}{abs(lon_sw):03d}_00_DEM"


def url_tile(lat_sw: int, lon_sw: int, produto: str) -> str:
    bucket, _ = PRODUTOS[produto]
    nome = nome_tile(lat_sw, lon_sw, produto)
    return f"https://{bucket}.s3.amazonaws.com/{nome}/{nome}.tif"


def tiles_bbox(bbox: Bbox) -> list[tuple[int, int]]:
    oeste, sul, leste, norte = bbox
    if not (oeste < leste and sul < norte):
        raise ValueError(f"bbox inválido {bbox}; use (oeste, sul, leste, norte)")
    return [
        (lat, lon)
        for lat in range(math.floor(sul), math.ceil(norte))
        for lon in range(math.floor(oeste), math.ceil(leste))
    ]


def ler_bbox(bbox: Bbox, produto: str = "glo90", *, forcar: bool = False) -> Path:
    """Mosaico do DEM recortado no bbox, salvo como GeoTIFF comprimido (cache local)."""
    if produto not in PRODUTOS:
        raise ValueError(f"produto deve ser um de {list(PRODUTOS)}")
    oeste, sul, leste, norte = bbox
    destino = garantir(BRUTOS / "copernicus") / (
        f"{produto}_{oeste:.3f}_{sul:.3f}_{leste:.3f}_{norte:.3f}.tif"
    )
    if destino.exists() and not forcar:
        return destino

    urls: list[str] = []
    abertos = []
    with rasterio.Env(**GDAL_HTTP):
        try:
            for lat, lon in tiles_bbox(bbox):
                url = url_tile(lat, lon, produto)
                try:
                    abertos.append(rasterio.open(f"/vsicurl/{url}"))
                    urls.append(url)
                except RasterioIOError:
                    pass  # tile inexistente = oceano
            if not abertos:
                raise RuntimeError(f"Nenhum tile Copernicus encontrado para {bbox}")
            mosaico, transform = merge(abertos, bounds=bbox, nodata=np.nan, dtype="float32")
            perfil = abertos[0].profile | {
                "driver": "GTiff",
                "height": mosaico.shape[1],
                "width": mosaico.shape[2],
                "transform": transform,
                "nodata": np.nan,
                "dtype": "float32",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
                "compress": "deflate",
                "predictor": 3,
            }
        finally:
            for ds in abertos:
                ds.close()

    with rasterio.open(destino, "w", **perfil) as dst:
        dst.write(mosaico)
        dst.update_tags(fonte="Copernicus DEM", produto=produto, datum_vertical="EGM2008")
    proveniencia.registrar(
        destino,
        fonte_id=f"copernicus_{produto}",
        urls=urls,
        licenca=LICENCA,
        extra={"bbox": list(bbox), "tipo_modelo": "DSM", "datum_vertical": "EGM2008"},
    )
    return destino

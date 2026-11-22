"""Região de estudo e utilidades do atlas (sem rede)."""

import geopandas as gpd
import numpy as np
import pytest
from matplotlib.colors import to_rgb
from shapely.geometry import MultiPolygon, Point, box

from trembr.atlas.estilo import fmt_dec, fmt_int
from trembr.atlas.relevo import colorir
from trembr.atlas.web import CamadaWeb, montar_html, para_geojson
from trembr.graficos import MAR
from trembr.regiao import Regiao, carregar_regiao, sem_ilhas_oceanicas


def test_sem_ilhas_oceanicas_tira_so_as_ilhas_distantes():
    continente = box(0, 0, 500_000, 500_000)
    costeira = Point(510_000, 250_000).buffer(3_000)  # 7 km da costa
    oceanica = Point(1_600_000, 250_000).buffer(3_000)  # 1.100 km da costa
    g = sem_ilhas_oceanicas(MultiPolygon([continente, costeira, oceanica]), 150_000)
    assert len(g.geoms) == 2
    assert g.bounds[2] < 600_000
    assert sem_ilhas_oceanicas(continente, 1) is continente


def test_regioes_do_config():
    se = carregar_regiao("sudeste")
    assert set(se.ufs) == {"SP", "RJ", "MG", "ES"} and se.margem_km > 0
    assert len(carregar_regiao("brasil").ufs) == 27
    with pytest.raises(ValueError, match="não existe"):
        carregar_regiao("atlantida")


def test_formatos_brasileiros():
    assert fmt_int(84_840_113) == "84.840.113"
    assert fmt_dec(84.840113) == "84,8"
    assert fmt_dec(1234.5, 2) == "1.234,50"


def test_geojson_leve_e_html(tmp_path):
    gdf = gpd.GeoDataFrame(
        {"nome": ["A"], "pop": [1234], "lixo": ["x"]},
        geometry=[box(-46.6, -23.6, -46.5, -23.5)],
        crs="EPSG:4674",
    )
    gj = para_geojson(gdf, ["nome", "pop"], tolerancia_m=10, casas=3)
    props = gj["features"][0]["properties"]
    assert props == {"nome": "A", "pop": 1234}
    x, y = gj["features"][0]["geometry"]["coordinates"][0][0]
    assert x == round(x, 3) and y == round(y, 3)

    regiao = Regiao("teste", "Teste", ("SP",), 10.0, 150.0)
    camada = CamadaWeb("a", "A", "G", "fill", {"fill-color": "#000"}, "#000", geojson=gj)
    regiao_bbox = (-47.0, -24.0, -46.0, -23.0)
    object.__setattr__(regiao, "bbox", lambda: regiao_bbox)  # sem depender da malha do IBGE
    html = montar_html(regiao, [camada], tmp_path / "index.html").read_text(encoding="utf-8")
    assert "maplibre-gl@" in html and '"id":"a"' in html and "Atlas · Teste" in html
    assert "__CAMADAS__" not in html and "__LIMITES__" not in html


def test_relevo_mar_sem_dado_e_terra():
    z = np.array([[np.nan, 0.0], [500.0, 2500.0]])
    rgba = colorir(z, 90.0, alfa=True)
    assert rgba.shape == (2, 2, 4) and rgba.dtype == np.uint8
    assert rgba[0, 0, 3] == 0 and (rgba[1, :, 3] == 255).all()  # sem dado = transparente
    mar = (np.array(to_rgb(MAR)) * 255).round()
    assert np.abs(rgba[0, 1, :3] - mar).max() <= 1  # cota 0 = mar
    assert (
        rgba[1, 0, :3].tolist() != rgba[1, 1, :3].tolist()
    )  # altitudes diferentes, cores diferentes
    assert colorir(z, 90.0).shape == (2, 2, 3)

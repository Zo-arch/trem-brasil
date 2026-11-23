"""Geometria, CRS, nomes de tiles, configuração e superfície de custo."""

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS

from trembr.config import Limites, carregar_custos, carregar_norma
from trembr.crs import epsg_utm_sirgas
from trembr.fontes.catalogo import carregar_catalogo
from trembr.fontes.copernicus import nome_tile, tiles_bbox
from trembr.terreno.dem import Raster
from trembr.terreno.superficie_custo import superficie_custo
from trembr.tracado.geometria import chaikin, raio_curvatura, reamostrar


def test_raio_de_um_circulo():
    t = np.linspace(0, np.pi, 400)
    xy = 5000 * np.column_stack([np.cos(t), np.sin(t)])
    r = raio_curvatura(xy)[1:-1]
    assert np.allclose(r, 5000, rtol=1e-3)


def test_reamostrar_espaco_constante_e_chaikin_mantem_pontas():
    xy = np.array([[0, 0], [1000, 0], [1000, 1000.0]])
    pts, s = reamostrar(xy, 100)
    assert np.allclose(np.diff(s), 100) and len(pts) == 21
    suave = chaikin(xy, 4)
    assert np.allclose(suave[0], xy[0]) and np.allclose(suave[-1], xy[-1])


@pytest.mark.parametrize(
    ("lon", "lat", "epsg"),
    [(-46.63, -23.55, "EPSG:31983"), (-60.0, -3.1, "EPSG:31981"), (-60.67, 2.82, "EPSG:31974")],
)
def test_utm_sirgas(lon, lat, epsg):
    assert epsg_utm_sirgas(lon, lat) == epsg


def test_tiles_copernicus():
    assert nome_tile(-23, -44, "glo90") == "Copernicus_DSM_COG_30_S23_00_W044_00_DEM"
    assert nome_tile(2, -61, "glo30") == "Copernicus_DSM_COG_10_N02_00_W061_00_DEM"
    tiles = tiles_bbox((-46.9, -23.8, -43.0, -22.3))
    assert len(tiles) == 8 and (-24, -47) in tiles and (-23, -44) in tiles
    with pytest.raises(ValueError):
        tiles_bbox((-43, -22, -46, -23))


def test_configs_carregam_e_limites_sem_lacuna():
    assert carregar_norma("as350").rampa_max == 0.030
    assert carregar_custos("referencia").status == "placeholder"
    with pytest.raises(ValueError, match="sem solução"):
        Limites(
            aterro_altura_max_m=5,
            corte_profundidade_max_m=25,
            viaduto_altura_min_m=8,
            viaduto_altura_max_m=100,
            tunel_profundidade_min_m=15,
        )


def test_catalogo_valido_e_ids_unicos():
    fontes = carregar_catalogo()
    ids = [f.id for f in fontes]
    assert len(ids) == len(set(ids))
    assert any(f.status == "implementado" for f in fontes)


def test_superficie_custo_relevo_encarece_e_agua_proibe():
    norma, custos = carregar_norma("as350"), carregar_custos("referencia")
    rng = np.random.default_rng(0)
    z = np.full((120, 120), 300.0)
    z[:, 60:] += rng.normal(0, 40, (120, 60))  # metade direita acidentada
    z[:10, :10] = 0.0  # "mar"
    dem = Raster(z, Affine(90, 0, 0, 0, -90, 0), CRS.from_epsg(31983))
    c = superficie_custo(dem, norma, custos)
    plano, acidentado = np.median(c[30:, 15:40]), np.median(c[30:, 80:])
    assert np.isclose(plano, custos.precos.via_e_sistemas_m, rtol=0.05)
    assert acidentado > 2 * plano
    assert np.isinf(c[:10, :10]).all()


def test_configs_do_corredor_e_do_estudo_rio_sp():
    from trembr.config import carregar_corredor
    from trembr.estudos.rio_sp import carregar_config, rodar

    corredor = carregar_corredor()
    assert corredor.status == "nao_calibrado" and corredor.superficie.janela_m > 0
    cfg = carregar_config("rio_sp")
    assert {"origem", "destino", "v1", "v2", "corredor"} <= set(cfg)
    assert len(cfg["v1"]["recorte"]) == 4 and 0 < cfg["v2"]["folga_elipse"] < 1
    with pytest.raises(ValueError, match="versão"):
        rodar(99)

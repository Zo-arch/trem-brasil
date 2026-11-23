"""Leitura de fontes vetoriais: etiquetas do OpenStreetMap e classes de áreas protegidas."""

import math

from trembr.fontes.osm import FERROVIAS, RODOVIAS, extratos, ler_hstore


def test_hstore_do_gdal():
    texto = '"ref"=>"BR-116","maxspeed"=>"110","name:en"=>"President \\"Dutra\\" Hwy"'
    assert ler_hstore(texto) == {
        "ref": "BR-116",
        "maxspeed": "110",
        "name:en": 'President "Dutra" Hwy',
    }
    assert ler_hstore(None) == {} and ler_hstore(math.nan) == {} and ler_hstore("") == {}


def test_classes_e_extratos():
    assert RODOVIAS["motorway_link"] == "autoestrada" and RODOVIAS["secondary"] == "secundaria"
    assert FERROVIAS["abandoned"] == FERROVIAS["disused"] == "desativada"
    assert extratos("sudeste") == ["south-america/brazil/sudeste"]


def test_classes_de_unidades_de_conservacao():
    from trembr.fontes.protegidas import classe_uc

    assert classe_uc("Proteção Integral", "Parque") == "protecao_integral"
    assert classe_uc("Uso Sustentável", "Área de Proteção Ambiental") == "apa"
    assert classe_uc("Uso Sustentável", "Floresta") == "uso_sustentavel"
    assert (
        classe_uc("Uso Sustentável", "Reserva Particular do Patrimônio Natural")
        == "uso_sustentavel"
    )

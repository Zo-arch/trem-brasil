"""Leitura das tabelas de cidades do IBGE (sem rede)."""

import json

import pandas as pd

from trembr.fontes.cidades import _pib, _regic


def test_regic_normaliza_nivel_de_integrante_de_arranjo(tmp_path):
    linhas = pd.DataFrame(
        {
            "codmun": ["3550308", "3509502", "3170206"],
            "Município": ["São Paulo", "Campinas", "Uberlândia"],
            "Categoria": ["Arranjo populacional", "Arranjo populacional", "Município isolado"],
            "Arranjo Populacional": [
                "Arranjo Populacional de São Paulo/SP",
                "Arranjo Populacional de Campinas/SP",
                None,
            ],
            "codcid": ["9999001", "9999002", "3170206"],
            "Hierarquia 3": [
                "1A - Integrante de Arranjo Populacional",
                "1C - Integrante de Arranjo Populacional",
                "2B",
            ],
            "Hierarquia - grupo": [
                "1 - Metrópole - Integrante de Arranjo Populacional",
                "1 - Metrópole - Integrante de Arranjo Populacional",
                "2 - Capital Regional",
            ],
        }
    )
    arq = tmp_path / "regic.xlsx"
    linhas.to_excel(arq, index=False)
    r = _regic(arq)
    assert r["regic_nivel"].tolist() == ["1A", "1C", "2B"]
    assert r["regic_grupo"].tolist() == ["Metrópole", "Metrópole", "Capital Regional"]
    assert r["regic_grupo_ord"].tolist() == [1, 1, 2]
    assert r["arranjo"].tolist() == [True, True, False]
    assert r.loc[2, "regic_cidade"] == "Uberlândia"  # isolado: a "cidade" é o próprio município


def test_pib_do_sidra_pula_cabecalho(tmp_path):
    sidra = [
        {"D1C": "Município (Código)", "V": "Valor", "D3N": "Ano"},
        {"D1C": "3550308", "V": "945946483", "D3N": "2023"},
        {"D1C": "1100015", "V": "...", "D3N": "2023"},  # SIDRA usa "..." para dado ausente
    ]
    arq = tmp_path / "pib.json"
    arq.write_text(json.dumps(sidra), encoding="utf-8")
    pib = _pib(arq)
    assert pib["cod_ibge"].tolist() == [3550308, 1100015]
    assert pib.loc[0, "pib_mil_reais"] == 945946483 and pd.isna(pib.loc[1, "pib_mil_reais"])
    assert (pib["pib_ano"] == 2023).all()

"""Escolha de paradas: fronteira de Pareto contra enumeração exaustiva."""

import itertools

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from trembr.tracado.paradas import Rota, fronteira, joelho, suportadas


def _forca_bruta(custo: np.ndarray, beneficio: np.ndarray) -> set[tuple[float, float]]:
    n = len(beneficio)
    pontos = []
    meio = range(1, n - 1)
    for k in range(n - 1):
        for paradas in itertools.combinations(meio, k):
            nos = (0, *paradas, n - 1)
            c = sum(custo[a, b] for a, b in itertools.pairwise(nos))
            if np.isfinite(c):
                pontos.append((c, float(sum(beneficio[list(paradas)]))))
    pareto = {
        (c, b)
        for c, b in pontos
        if not any((c2 <= c and b2 >= b) and (c2 < c or b2 > b) for c2, b2 in pontos)
    }
    return {(round(c, 9), round(b, 9)) for c, b in pareto}


@st.composite
def instancias(draw):
    n = draw(st.integers(2, 9))
    rng = np.random.default_rng(draw(st.integers(0, 2**32 - 1)))
    custo = np.full((n, n), np.inf)
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() > 0.15 or (i == 0 and j == n - 1):
                custo[i, j] = round(float(rng.uniform(1, 100)), 3)
    beneficio = rng.integers(0, 50, n).astype(float)
    return custo, beneficio


@settings(max_examples=300, deadline=None)
@given(instancias())
def test_fronteira_igual_a_forca_bruta(inst):
    custo, beneficio = inst
    rotas = fronteira(custo, beneficio)
    obtido = {(round(r.custo, 9), round(r.beneficio, 9)) for r in rotas}
    assert obtido == _forca_bruta(custo, beneficio)
    # cada rota devolvida é viável e seus números batem com os nós
    for r in rotas:
        assert r.nos[0] == 0 and r.nos[-1] == len(beneficio) - 1
        assert all(a < b for a, b in itertools.pairwise(r.nos))
        c = sum(custo[a, b] for a, b in itertools.pairwise(r.nos))
        assert np.isclose(c, r.custo) and np.isclose(beneficio[list(r.paradas)].sum(), r.beneficio)


@settings(max_examples=200, deadline=None)
@given(instancias())
def test_suportadas_sao_as_escolhidas_por_soma_ponderada(inst):
    custo, beneficio = inst
    rotas = fronteira(custo, beneficio)
    sup = {(r.custo, r.beneficio) for r in suportadas(rotas)}
    for lam in np.concatenate([[0.0], np.geomspace(1e-3, 1e3, 200)]):
        valores = [lam * r.beneficio - r.custo for r in rotas]
        melhor = max(valores)
        vencedoras = {
            (r.custo, r.beneficio)
            for r, v in zip(rotas, valores, strict=True)
            if np.isclose(v, melhor)
        }
        assert vencedoras & sup  # algum ponto ótimo para esse λ está entre os suportados


def test_exemplo_a_mao_e_joelho():
    # 0 → 3 direto custa 10; passar por 1 (100 pessoas) custa 12; por 2 (5 pessoas) custa 30
    custo = np.full((4, 4), np.inf)
    custo[0, 3] = 10
    custo[0, 1], custo[1, 3] = 6, 6
    custo[0, 2], custo[2, 3] = 15, 15
    custo[1, 2] = 15
    beneficio = np.array([0, 100, 5, 0.0])
    rotas = fronteira(custo, beneficio)
    assert [r.nos for r in rotas] == [(0, 3), (0, 1, 3), (0, 1, 2, 3)]
    assert joelho(rotas).nos == (0, 1, 3)
    assert suportadas(rotas)[0] == Rota((0, 3), 10.0, 0.0)

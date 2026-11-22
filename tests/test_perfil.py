"""O greide ótimo é mesmo ótimo e respeita as restrições?"""

import itertools
import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from trembr.config import carregar_custos, carregar_norma
from trembr.tracado.perfil import _programacao_dinamica, discretizacao, otimizar_greide
from trembr.tracado.secao import ATERRO, CORTE, TUNEL, VIADUTO, param_secao, secao

NORMA = carregar_norma("as350")
CUSTOS = carregar_custos("referencia")
P = param_secao(NORMA, CUSTOS)
DISC = discretizacao(NORMA, 100.0)


def forca_bruta(zg, z_base, dz, J, K, passo, j0, jn, k_ext):
    """Enumera TODAS as sequências de rampas viáveis e devolve o menor custo."""
    n = len(zg)
    melhor = math.inf
    for j_ini in range(j0[0], j0[1] + 1):
        for k_ini in range(-k_ext, k_ext + 1):
            for ks in itertools.product(range(-K, K + 1), repeat=n - 1):
                seq = (k_ini, *ks)
                if any(abs(seq[i] - seq[i - 1]) > 1 for i in range(1, n)) or abs(ks[-1]) > k_ext:
                    continue
                js = list(itertools.accumulate(ks, initial=j_ini))
                if not all(0 <= j < J for j in js) or not jn[0] <= js[-1] <= jn[1]:
                    continue
                custo = sum(secao(z_base + js[i] * dz - zg[i], P)[0] for i in range(n)) * passo
                melhor = min(melhor, custo)
    return melhor


@settings(max_examples=40, deadline=None)
@given(
    zg=st.lists(st.floats(0, 30), min_size=6, max_size=6),
    K=st.integers(1, 2),
    k_ext=st.integers(0, 1),
)
def test_programacao_dinamica_igual_a_forca_bruta(zg, K, k_ext):
    zg = np.array(zg)
    dz, J, passo = 1.0, 45, 10.0
    j0 = (max(0, round(zg[0]) - 1), round(zg[0]) + 1)
    jn = (max(0, round(zg[-1]) - 1), round(zg[-1]) + 1)
    custo_dp, js, _ = _programacao_dinamica(zg, 0.0, dz, J, K, passo, P, *j0, *jn, k_ext)
    custo_fb = forca_bruta(zg, 0.0, dz, J, K, passo, j0, jn, k_ext)
    assert math.isclose(custo_dp, custo_fb, rel_tol=1e-9) or (
        math.isinf(custo_dp) and math.isinf(custo_fb)
    )
    if math.isfinite(custo_dp):  # a reconstrução reproduz o custo
        recalc = sum(secao(js[i] * dz - zg[i], P)[0] for i in range(len(zg))) * passo
        assert math.isclose(recalc, custo_dp, rel_tol=1e-9)


@settings(max_examples=25, deadline=None)
@given(st.lists(st.floats(-40, 40), min_size=10, max_size=10))
def test_restricoes_de_rampa_curva_vertical_e_pontas(ondas):
    s = np.arange(120) * DISC.passo_m
    zg = 500 + np.interp(s, np.linspace(0, s[-1], 10), ondas)
    r = otimizar_greide(zg, DISC, NORMA, CUSTOS, folga_extremos_m=1.0)
    rampa = r.rampa
    tol = 1e-9
    assert np.all(np.abs(rampa) <= NORMA.rampa_max + tol)
    assert np.all(np.abs(np.diff(rampa)) <= DISC.passo_m / NORMA.raio_vertical_min_m + tol)
    assert abs(r.z_trilho[0] - zg[0]) <= 1.0 + tol
    assert abs(r.z_trilho[-1] - zg[-1]) <= 1.0 + tol
    assert np.isfinite(r.custo_infra_m).all()


def test_rampa_maxima_nao_e_arredondada():
    assert math.isclose(DISC.rampa_max_efetiva, NORMA.rampa_max)
    assert math.isclose(DISC.delta_rampa, DISC.passo_m / NORMA.raio_vertical_min_m)


def test_terreno_plano_vira_greide_colado_no_chao():
    zg = np.full(80, 312.3)
    r = otimizar_greide(zg, DISC, NORMA, CUSTOS)
    assert np.all(np.abs(r.z_trilho - zg) <= DISC.delta_z_m)
    assert set(np.unique(r.tipo)) <= {ATERRO, CORTE}


def test_morro_alto_e_estreito_pede_tunel():
    s = np.arange(250) * DISC.passo_m
    zg = 100 + 250 * np.exp(-(((s - s[-1] / 2) / 1500) ** 2))
    r = otimizar_greide(zg, DISC, NORMA, CUSTOS)
    assert (r.tipo == TUNEL).any()


def test_vale_profundo_e_estreito_pede_viaduto():
    s = np.arange(250) * DISC.passo_m
    zg = 400 - 120 * np.exp(-(((s - s[-1] / 2) / 800) ** 2))
    r = otimizar_greide(zg, DISC, NORMA, CUSTOS)
    assert (r.tipo == VIADUTO).any()


def test_terreno_com_buraco_falha_explicitamente():
    zg = np.full(10, 100.0)
    zg[4] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        otimizar_greide(zg, DISC, NORMA, CUSTOS)

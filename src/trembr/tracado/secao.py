"""Modelo de seção transversal: quanto custa, por metro, pôr o trilho a uma altura ``d`` do terreno.

``d = z_trilho − z_terreno``. ``d > 0``: o trilho passa acima do chão (aterro ou viaduto);
``d < 0``: abaixo do chão (corte ou túnel). Em cada ponto o modelo escolhe a estrutura
**tecnicamente viável** mais barata. Não há limiar arbitrário entre corte e túnel: a troca
acontece onde os custos se cruzam, dentro das faixas de viabilidade de ``config/custos``.

Volumes de terraplenagem por metro (seção trapezoidal, plataforma ``b``, talude ``n`` H:V):
    A(h) = (b + n·h)·h
"""

from __future__ import annotations

from collections import namedtuple

import numpy as np
from numba import njit

from trembr.config import ModeloCustos, Norma

ATERRO, CORTE, VIADUTO, TUNEL, INVIAVEL = 0, 1, 2, 3, -1
NOMES_TIPO = {ATERRO: "aterro", CORTE: "corte", VIADUTO: "viaduto", TUNEL: "túnel"}

ParamSecao = namedtuple(
    "ParamSecao",
    [
        "largura",
        "talude_corte",
        "talude_aterro",
        "preco_corte_m3",
        "preco_aterro_m3",
        "preco_viaduto_m",
        "preco_viaduto_m_por_m",
        "preco_tunel_m",
        "aterro_max",
        "corte_max",
        "viaduto_min",
        "viaduto_max",
        "tunel_min",
    ],
)


def param_secao(norma: Norma, custos: ModeloCustos) -> ParamSecao:
    p, g, lim = custos.precos, custos.geotecnia, custos.limites
    return ParamSecao(
        float(norma.largura_plataforma_m),
        float(g.talude_corte_h_por_v),
        float(g.talude_aterro_h_por_v),
        float(p.corte_m3),
        float(p.aterro_m3),
        float(p.viaduto_m),
        float(p.viaduto_m_por_m_altura),
        float(p.tunel_m),
        float(lim.aterro_altura_max_m),
        float(lim.corte_profundidade_max_m),
        float(lim.viaduto_altura_min_m),
        float(lim.viaduto_altura_max_m),
        float(lim.tunel_profundidade_min_m),
    )


@njit(cache=True)
def secao(d, p):
    """Devolve (custo R$/m, tipo) da estrutura mais barata viável para o desnível ``d``."""
    melhor = np.inf
    tipo = INVIAVEL
    if d >= 0.0:
        if d <= p.aterro_max:
            melhor = p.preco_aterro_m3 * (p.largura + p.talude_aterro * d) * d
            tipo = ATERRO
        if p.viaduto_min <= d <= p.viaduto_max:
            c = p.preco_viaduto_m + p.preco_viaduto_m_por_m * d
            if c < melhor:
                melhor = c
                tipo = VIADUTO
    else:
        h = -d
        if h <= p.corte_max:
            melhor = p.preco_corte_m3 * (p.largura + p.talude_corte * h) * h
            tipo = CORTE
        if h >= p.tunel_min and p.preco_tunel_m < melhor:
            melhor = p.preco_tunel_m
            tipo = TUNEL
    return melhor, tipo


@njit(cache=True)
def secao_vetor(d, p):
    n = d.size
    custo = np.empty(n)
    tipo = np.empty(n, np.int8)
    for i in range(n):
        custo[i], tipo[i] = secao(d[i], p)
    return custo, tipo


def volumes_por_metro(
    d: np.ndarray, tipo: np.ndarray, p: ParamSecao
) -> tuple[np.ndarray, np.ndarray]:
    """Área de corte e de aterro (m³ por metro de via) em cada ponto."""
    h = np.abs(d)
    corte = np.where(tipo == CORTE, (p.largura + p.talude_corte * h) * h, 0.0)
    aterro = np.where(tipo == ATERRO, (p.largura + p.talude_aterro * h) * h, 0.0)
    return corte, aterro

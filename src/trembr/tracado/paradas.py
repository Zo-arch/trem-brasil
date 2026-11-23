r"""Escolha de paradas de uma linha: fronteira de Pareto exata entre custo e gente atendida.

Os nós ficam em ordem de avanço ao longo do eixo da linha: 0 é a origem, n-1 o destino, e a
linha só anda para a frente (aresta i → j só com i < j). Isso é um grafo acíclico. Cada aresta
tem um custo :math:`C_{ij}` (o corredor ótimo entre as duas cidades) e cada nó intermediário um
benefício :math:`b_j` (a população atendida). Uma rota é uma sequência
:math:`0 = v_0 < v_1 < \dots < v_k = n-1`, com

.. math:: \text{custo} = \sum_t C_{v_{t-1} v_t}, \qquad \text{benefício} = \sum_{t=1}^{k-1} b_{v_t}.

Não há um "peso" entre reais e pessoas escolhido à mão: devolvemos a fronteira de Pareto
inteira (todas as rotas para as quais não existe outra mais barata *e* com mais gente). Ela é
calculada por programação dinâmica com rótulos (label-setting): cada nó guarda os rótulos
(custo, benefício) não dominados que chegam até ele, em ordem topológica. É exata, inclusive
nos pontos que uma soma ponderada nunca encontraria (os "não suportados"), e é testada contra
a enumeração de todos os subconjuntos de paradas.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Rota:
    nos: tuple[int, ...]  # 0, ..., n-1
    custo: float
    beneficio: float

    @property
    def paradas(self) -> tuple[int, ...]:
        return self.nos[1:-1]


def _nao_dominados(rotulos: list[Rota]) -> list[Rota]:
    """Mantém só os pontos de Pareto (custo menor, benefício maior); empates ficam com um só."""
    ordem = sorted(rotulos, key=lambda r: (r.custo, -r.beneficio, len(r.nos)))
    saida: list[Rota] = []
    melhor_b = -np.inf
    for r in ordem:
        if r.beneficio > melhor_b:
            saida.append(r)
            melhor_b = r.beneficio
    return saida


def fronteira(custo: np.ndarray, beneficio: np.ndarray) -> list[Rota]:
    """Fronteira de Pareto das rotas 0 → n-1, ordenada por custo crescente.

    ``custo[i, j]`` (i < j) é o custo da aresta; ``inf`` proíbe. ``beneficio[j]`` vale para os
    nós intermediários (os das pontas são ignorados).
    """
    n = len(beneficio)
    if custo.shape != (n, n):
        raise ValueError("custo deve ser n × n")
    if n < 2:
        raise ValueError("precisa de origem e destino")
    if (np.asarray(beneficio)[1:-1] < 0).any():
        raise ValueError("benefícios devem ser >= 0")
    rotulos: list[list[Rota]] = [[] for _ in range(n)]
    rotulos[0] = [Rota((0,), 0.0, 0.0)]
    for j in range(1, n):
        b = 0.0 if j == n - 1 else float(beneficio[j])
        candidatos = [
            Rota((*r.nos, j), r.custo + float(custo[i, j]), r.beneficio + b)
            for i in range(j)
            if np.isfinite(custo[i, j])
            for r in rotulos[i]
        ]
        rotulos[j] = _nao_dominados(candidatos)
    return rotulos[n - 1]


def suportadas(rotas: list[Rota]) -> list[Rota]:
    """Pontos da fronteira na envoltória convexa: os que alguma soma ponderada
    ``benefício·λ − custo`` (λ >= 0) escolheria. Ordem de custo crescente."""
    casco: list[Rota] = []
    for r in rotas:  # rotas já em ordem de custo crescente e benefício crescente
        while len(casco) >= 2:
            a, b = casco[-2], casco[-1]
            # remove b se ficar abaixo (ou sobre) a reta de a até r
            cruz = (b.custo - a.custo) * (r.beneficio - a.beneficio) - (
                b.beneficio - a.beneficio
            ) * (r.custo - a.custo)
            if cruz >= 0:
                casco.pop()
            else:
                break
        casco.append(r)
    return casco


def joelho(rotas: list[Rota]) -> Rota:
    """Ponto da fronteira mais distante da reta entre os dois extremos (custo e benefício
    normalizados): onde parar de acrescentar paradas deixa de compensar ("kneedle")."""
    if len(rotas) <= 2:
        return rotas[-1]
    c = np.array([r.custo for r in rotas])
    b = np.array([r.beneficio for r in rotas])
    cn = (c - c[0]) / (c[-1] - c[0]) if c[-1] > c[0] else np.zeros_like(c)
    bn = (b - b[0]) / (b[-1] - b[0]) if b[-1] > b[0] else np.zeros_like(b)
    return rotas[int(np.argmax(bn - cn))]

r"""Corredor de menor custo sobre uma superfície raster (A* em numba).

Vizinhança de 16 direções (8 vizinhos + "pulos de cavalo"): o erro máximo de comprimento em
relação à linha reta cai de ~8% (8 direções) para ~2,7%. O custo de um movimento é

.. math:: w = \ell \cdot \overline{c}

com :math:`\ell` o comprimento em metros e :math:`\overline{c}` a média dos custos (R$/m) das
células atravessadas — nos pulos de cavalo, inclui as duas células do meio. Se qualquer célula
atravessada for proibida (``inf``), o movimento é proibido: não dá para "pular" barreiras finas.

Heurística: :math:`h = c_{min}\cdot d_{euclid}`, admissível e consistente (todo movimento custa
pelo menos :math:`c_{min}\,\ell`), então o A* devolve o mesmo ótimo que Dijkstra, mais rápido.
"""

from __future__ import annotations

import heapq
import math

import numpy as np
from numba import njit

_OFFSETS_8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_CAVALO = [(-1, -2), (-1, 2), (1, -2), (1, 2), (-2, -1), (-2, 1), (2, -1), (2, 1)]


def _vizinhanca(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    offs = _OFFSETS_8 + (_CAVALO if n == 16 else [])
    meio = np.zeros((len(offs), 2, 2), np.int64)
    n_meio = np.zeros(len(offs), np.int64)
    for m, (dr, dc) in enumerate(offs):
        if abs(dr) == 1 and abs(dc) == 2:
            meio[m] = [(0, np.sign(dc)), (dr, np.sign(dc))]
            n_meio[m] = 2
        elif abs(dr) == 2 and abs(dc) == 1:
            meio[m] = [(np.sign(dr), 0), (np.sign(dr), dc)]
            n_meio[m] = 2
    return np.array(offs, np.int64), meio, n_meio


@njit(cache=True)
def _a_estrela(custo, r0, c0, r1, c1, res, offs, meio, n_meio, c_min):
    H, W = custo.shape
    N = H * W
    g = np.full(N, np.inf)
    pred = np.full(N, -1, np.int64)
    fechado = np.zeros(N, np.bool_)
    comp = np.empty(offs.shape[0])
    for m in range(offs.shape[0]):
        comp[m] = math.hypot(offs[m, 0], offs[m, 1]) * res

    origem = r0 * W + c0
    alvo = r1 * W + c1
    g[origem] = 0.0
    fila = [(c_min * res * math.hypot(r0 - r1, c0 - c1), origem)]
    while len(fila) > 0:
        _, u = heapq.heappop(fila)
        if fechado[u]:
            continue
        fechado[u] = True
        if u == alvo:
            break
        ur = u // W
        uc = u - ur * W
        cu = custo[ur, uc]
        for m in range(offs.shape[0]):
            vr = ur + offs[m, 0]
            vc = uc + offs[m, 1]
            if vr < 0 or vr >= H or vc < 0 or vc >= W:
                continue
            v = vr * W + vc
            if fechado[v]:
                continue
            cv = custo[vr, vc]
            if not cv < np.inf:
                continue
            soma = cu + cv
            ok = True
            for t in range(n_meio[m]):
                cm = custo[ur + meio[m, t, 0], uc + meio[m, t, 1]]
                if not cm < np.inf:
                    ok = False
                    break
                soma += cm
            if not ok:
                continue
            novo = g[u] + comp[m] * soma / (2 + n_meio[m])
            if novo < g[v]:
                g[v] = novo
                pred[v] = u
                heapq.heappush(fila, (novo + c_min * res * math.hypot(vr - r1, vc - c1), v))

    if not g[alvo] < np.inf:
        return np.empty((0, 2), np.int64), np.inf
    n = 1
    u = alvo
    while u != origem:
        u = pred[u]
        n += 1
    rota = np.empty((n, 2), np.int64)
    u = alvo
    for i in range(n - 1, -1, -1):
        rota[i, 0] = u // W
        rota[i, 1] = u % W
        u = pred[u]
    return rota, g[alvo]


def caminho_minimo(
    custo_por_m: np.ndarray,
    origem: tuple[int, int],
    destino: tuple[int, int],
    resolucao_m: float,
    vizinhanca: int = 16,
) -> tuple[np.ndarray, float]:
    """Caminho de menor custo entre duas células.

    ``custo_por_m``: R$/m para atravessar cada célula, positivo; ``inf`` = proibido.
    Devolve (array N×2 de [linha, coluna], custo acumulado em R$).
    """
    if vizinhanca not in (8, 16):
        raise ValueError("vizinhanca deve ser 8 ou 16")
    custo = np.ascontiguousarray(custo_por_m, dtype=np.float64)
    for nome, (lin, col) in (("origem", origem), ("destino", destino)):
        if not (0 <= lin < custo.shape[0] and 0 <= col < custo.shape[1]):
            raise ValueError(f"{nome} {(lin, col)} fora do raster")
        if not np.isfinite(custo[lin, col]):
            raise ValueError(f"{nome} {(lin, col)} cai numa célula proibida")
    finitos = custo[np.isfinite(custo)]
    if (finitos <= 0).any():
        raise ValueError("custos devem ser positivos (use inf para proibir)")

    offs, meio, n_meio = _vizinhanca(vizinhanca)
    rota, total = _a_estrela(
        custo, *origem, *destino, float(resolucao_m), offs, meio, n_meio, float(finitos.min())
    )
    if not np.isfinite(total):
        raise RuntimeError("Destino inalcançável a partir da origem")
    return rota, float(total)


@njit(cache=True)
def _dijkstra_varios(custo, r0, c0, alvos, res, offs, meio, n_meio):
    """Dijkstra de uma origem até vários alvos (para quando todos estão fechados).

    Mesmo modelo de movimento do A*; devolve o vetor de custos acumulados e os predecessores.
    """
    H, W = custo.shape
    N = H * W
    g = np.full(N, np.inf)
    pred = np.full(N, -1, np.int64)
    fechado = np.zeros(N, np.bool_)
    comp = np.empty(offs.shape[0])
    for m in range(offs.shape[0]):
        comp[m] = math.hypot(offs[m, 0], offs[m, 1]) * res
    eh_alvo = np.zeros(N, np.bool_)
    faltam = 0
    for k in range(alvos.shape[0]):
        a = alvos[k, 0] * W + alvos[k, 1]
        if not eh_alvo[a]:
            eh_alvo[a] = True
            faltam += 1

    origem = r0 * W + c0
    g[origem] = 0.0
    fila = [(0.0, origem)]
    while len(fila) > 0 and faltam > 0:
        _, u = heapq.heappop(fila)
        if fechado[u]:
            continue
        fechado[u] = True
        if eh_alvo[u]:
            faltam -= 1
        ur = u // W
        uc = u - ur * W
        cu = custo[ur, uc]
        for m in range(offs.shape[0]):
            vr = ur + offs[m, 0]
            vc = uc + offs[m, 1]
            if vr < 0 or vr >= H or vc < 0 or vc >= W:
                continue
            v = vr * W + vc
            if fechado[v]:
                continue
            cv = custo[vr, vc]
            if not cv < np.inf:
                continue
            soma = cu + cv
            ok = True
            for t in range(n_meio[m]):
                cm = custo[ur + meio[m, t, 0], uc + meio[m, t, 1]]
                if not cm < np.inf:
                    ok = False
                    break
                soma += cm
            if not ok:
                continue
            novo = g[u] + comp[m] * soma / (2 + n_meio[m])
            if novo < g[v]:
                g[v] = novo
                pred[v] = u
                heapq.heappush(fila, (novo, v))
    return g, pred


def caminhos_a_partir_de(
    custo_por_m: np.ndarray,
    origem: tuple[int, int],
    destinos: list[tuple[int, int]],
    resolucao_m: float,
    vizinhanca: int = 16,
) -> list[tuple[np.ndarray, float]]:
    """Caminhos de menor custo de uma origem até cada destino, numa só busca (Dijkstra).

    Equivale a chamar ``caminho_minimo`` para cada destino, mas explora a grade uma vez só.
    Destino inalcançável devolve (array vazio, inf).
    """
    if vizinhanca not in (8, 16):
        raise ValueError("vizinhanca deve ser 8 ou 16")
    custo = np.ascontiguousarray(custo_por_m, dtype=np.float64)
    finitos = custo[np.isfinite(custo)]
    if (finitos <= 0).any():
        raise ValueError("custos devem ser positivos (use inf para proibir)")
    for lin, col in [origem, *destinos]:
        if not (0 <= lin < custo.shape[0] and 0 <= col < custo.shape[1]):
            raise ValueError(f"ponto {(lin, col)} fora do raster")
    offs, meio, n_meio = _vizinhanca(vizinhanca)
    alvos = np.array(destinos, np.int64).reshape(-1, 2)
    g, pred = _dijkstra_varios(custo, *origem, alvos, float(resolucao_m), offs, meio, n_meio)
    W = custo.shape[1]
    o = origem[0] * W + origem[1]
    saida = []
    for lin, col in destinos:
        u = lin * W + col
        if not np.isfinite(g[u]):
            saida.append((np.empty((0, 2), np.int64), np.inf))
            continue
        celulas = [u]
        while u != o:
            u = pred[u]
            celulas.append(u)
        celulas = np.array(celulas[::-1], np.int64)
        saida.append((np.column_stack([celulas // W, celulas % W]), float(g[lin * W + col])))
    return saida

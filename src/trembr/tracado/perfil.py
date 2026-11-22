r"""Otimização do greide (perfil vertical) por programação dinâmica — ótimo global.

Problema. Dado o terreno :math:`z_g(s)` amostrado a cada :math:`\Delta s` ao longo de um traçado
horizontal fixo, escolher a cota do trilho :math:`z(s)` que minimiza

.. math:: C = \sum_i c\big(z_i - z_{g,i}\big)\,\Delta s

onde :math:`c(d)` é o custo por metro da estrutura mais barata viável (``secao.py``), sujeito a

* rampa máxima: :math:`|z_{i+1}-z_i| \le i_{max}\,\Delta s`;
* raio mínimo de curva vertical :math:`R_v`: a rampa muda no máximo :math:`\Delta s/R_v` por passo;
* cotas das pontas próximas do terreno e rampa de estação nas pontas.

Discretização exata. Com :math:`\Delta i = \Delta s / R_v` e :math:`\Delta z = \Delta i\,\Delta s`,
o estado :math:`(j, k)` representa cota :math:`z = z_0 + j\,\Delta z` e rampa :math:`k\,\Delta i`.
A transição :math:`(j', k') \to (j'+k,\,k)` com :math:`|k-k'| \le 1` respeita **as duas**
restrições por construção, então a solução é o ótimo global do problema discretizado
(verificado contra força bruta em ``tests/test_perfil.py``). Escolhemos :math:`\Delta s` para que
:math:`i_{max}/\Delta i` seja inteiro e a rampa máxima não seja arredondada.

Custo: :math:`O(n \cdot J \cdot K)` tempo e :math:`n \cdot J \cdot (2K+1)` bytes de memória.

Limitações conhecidas (ver docs/metodologia.md): sem compensação corte/aterro (mass haul),
sem custo fixo de emboque de túnel/encontro de viaduto, sem restrição de rampa média em 10 km.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numba import njit

from trembr.config import ModeloCustos, Norma
from trembr.tracado.secao import (
    NOMES_TIPO,
    ParamSecao,
    param_secao,
    secao,
    secao_vetor,
    volumes_por_metro,
)


@dataclass(frozen=True)
class Discretizacao:
    passo_m: float  # Δs
    delta_rampa: float  # Δi = Δs / R_v
    delta_z_m: float  # Δz = Δi·Δs
    k_max: int  # rampa máxima = k_max·Δi
    k_estacao: int

    @property
    def rampa_max_efetiva(self) -> float:
        return self.k_max * self.delta_rampa


def discretizacao(norma: Norma, passo_desejado_m: float = 100.0) -> Discretizacao:
    """Escolhe Δs perto do desejado tal que a rampa máxima seja múltiplo exato de Δi."""
    produto = norma.rampa_max * norma.raio_vertical_min_m
    k = max(1, round(produto / passo_desejado_m))
    passo = produto / k
    delta_rampa = passo / norma.raio_vertical_min_m
    k_est = math.floor(norma.rampa_estacao_max / delta_rampa + 1e-9)
    return Discretizacao(passo, delta_rampa, delta_rampa * passo, k, min(k_est, k))


@njit(cache=True)
def _programacao_dinamica(zg, z_base, dz, J, K, passo, p, j0_lo, j0_hi, jn_lo, jn_hi, k_ext):
    n = zg.size
    NK = 2 * K + 1
    V = np.full((J, NK), np.inf)
    Vn = np.empty((J, NK))
    volta = np.zeros((n, J, NK), dtype=np.int8)

    for j in range(j0_lo, j0_hi + 1):
        c, _ = secao(z_base + j * dz - zg[0], p)
        if c < np.inf:
            for kk in range(K - k_ext, K + k_ext + 1):
                V[j, kk] = c * passo

    for i in range(1, n):
        Vn[:, :] = np.inf
        for j in range(J):
            c, _ = secao(z_base + j * dz - zg[i], p)
            if c == np.inf:
                continue
            c *= passo
            for kk in range(NK):
                jp = j - (kk - K)
                if jp < 0 or jp >= J:
                    continue
                melhor = np.inf
                arg = 0
                for dk in range(-1, 2):
                    kp = kk - dk
                    if 0 <= kp < NK:
                        v = V[jp, kp]
                        if v < melhor:
                            melhor = v
                            arg = dk
                if melhor < np.inf:
                    Vn[j, kk] = melhor + c
                    volta[i, j, kk] = arg
        V, Vn = Vn, V

    melhor = np.inf
    jb = -1
    kb = -1
    for j in range(jn_lo, jn_hi + 1):
        for kk in range(K - k_ext, K + k_ext + 1):
            if V[j, kk] < melhor:
                melhor = V[j, kk]
                jb = j
                kb = kk

    js = np.full(n, -1, np.int64)
    ks = np.full(n, -1, np.int64)
    if jb < 0:
        return melhor, js, ks
    js[n - 1] = jb
    ks[n - 1] = kb
    for i in range(n - 1, 0, -1):
        j = js[i]
        kk = ks[i]
        js[i - 1] = j - (kk - K)
        ks[i - 1] = kk - volta[i, j, kk]
    return melhor, js, ks


@dataclass
class ResultadoPerfil:
    s_m: np.ndarray
    z_terreno: np.ndarray
    z_trilho: np.ndarray
    tipo: np.ndarray
    custo_infra_m: np.ndarray  # R$/m em cada estaca (sem via e sistemas)
    disc: Discretizacao
    param: ParamSecao
    custos: ModeloCustos

    @property
    def rampa(self) -> np.ndarray:
        return np.diff(self.z_trilho) / self.disc.passo_m

    def resumo(self) -> dict:
        passo = self.disc.passo_m
        n = self.s_m.size
        extensao_m = n * passo
        d = self.z_trilho - self.z_terreno
        corte, aterro = volumes_por_metro(d, self.tipo, self.param)
        infra = float(self.custo_infra_m.sum() * passo)
        via = self.custos.precos.via_e_sistemas_m * extensao_m
        km = {nome: float((self.tipo == t).sum() * passo / 1000) for t, nome in NOMES_TIPO.items()}
        return {
            "extensao_km": extensao_m / 1000,
            "km_por_estrutura": km,
            "pct_por_estrutura": {k: 100 * v / (extensao_m / 1000) for k, v in km.items()},
            "volume_corte_milhoes_m3": float(corte.sum() * passo / 1e6),
            "volume_aterro_milhoes_m3": float(aterro.sum() * passo / 1e6),
            "rampa_max_usada": float(np.abs(self.rampa).max()) if n > 1 else 0.0,
            "rampa_max_permitida": self.disc.rampa_max_efetiva,
            "passo_m": passo,
            "custo_infra_bilhoes": infra / 1e9,
            "custo_via_sistemas_bilhoes": via / 1e9,
            "custo_total_bilhoes": (infra + via) / 1e9,
            "custo_status": self.custos.status,
        }


def otimizar_greide(
    z_terreno: np.ndarray,
    disc: Discretizacao,
    norma: Norma,
    custos: ModeloCustos,
    *,
    folga_extremos_m: float = 1.0,
    memoria_max_gb: float = 4.0,
) -> ResultadoPerfil:
    """Greide ótimo para o terreno amostrado a cada ``disc.passo_m``."""
    zg = np.ascontiguousarray(z_terreno, dtype=np.float64)
    if zg.ndim != 1 or zg.size < 2:
        raise ValueError("z_terreno deve ser 1D com pelo menos 2 pontos")
    if not np.isfinite(zg).all():
        raise ValueError("z_terreno tem NaN/inf (buraco no DEM); preencha antes de otimizar")

    p = param_secao(norma, custos)
    dz = disc.delta_z_m
    margem = folga_extremos_m + dz
    z_base = math.floor((zg.min() - margem) / dz) * dz
    J = math.ceil((zg.max() + p.viaduto_max - z_base) / dz) + 1
    K = disc.k_max
    memoria = zg.size * J * (2 * K + 1) / 1e9
    if memoria > memoria_max_gb:
        raise MemoryError(
            f"Programação dinâmica precisaria de {memoria:.1f} GB (n={zg.size}, J={J}, K={K}). "
            "Aumente o passo, divida o trecho ou suba memoria_max_gb."
        )

    def faixa(z: float) -> tuple[int, int]:
        lo = math.ceil((z - folga_extremos_m - z_base) / dz)
        hi = math.floor((z + folga_extremos_m - z_base) / dz)
        return max(lo, 0), min(hi, J - 1)

    j0 = faixa(zg[0])
    jn = faixa(zg[-1])
    custo, js, _ = _programacao_dinamica(
        zg, z_base, dz, J, K, disc.passo_m, p, *j0, *jn, disc.k_estacao
    )
    if not np.isfinite(custo):
        raise RuntimeError(
            "Sem greide viável: revise limites de estrutura, rampa ou folga das pontas"
        )

    z = z_base + js * dz
    custo_m, tipo = secao_vetor(z - zg, p)
    return ResultadoPerfil(
        s_m=np.arange(zg.size) * disc.passo_m,
        z_terreno=zg,
        z_trilho=z,
        tipo=tipo,
        custo_infra_m=custo_m,
        disc=disc,
        param=p,
        custos=custos,
    )

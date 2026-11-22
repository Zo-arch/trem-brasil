r"""Superfície de custo para a busca de corredor (camada 2).

Na busca de corredor ainda não sabemos o greide, então estimamos o custo por metro de cruzar
cada célula com um proxy **coerente com o mesmo modelo de seção** usado no greide:

1. rugosidade :math:`\sigma` = desvio-padrão do terreno após remover a tendência (média móvel
   numa janela :math:`w`). Mede ondulações que o greide não consegue acompanhar;
2. excesso de declividade: onde a encosta suavizada passa da rampa máxima, o greide se afasta
   do terreno em :math:`(S - i_{max})\cdot L`, com :math:`L` um comprimento característico;
3. desnível típico :math:`h = \sigma + \max(0, S - i_{max})\,L` e custo
   :math:`c = c_{via} + \tfrac12[c_{secao}(+h) + c_{secao}(-h)]`
   (meio aterro/viaduto, meio corte/túnel).

Os parâmetros :math:`w` e :math:`L` NÃO estão calibrados. Calibração planejada (roteiro: Fase 2 · v6):
regressão do custo ótimo do greide (programação dinâmica) contra :math:`\sigma` e :math:`S` em
milhares de trechos amostrados. Até lá, o corredor é exploratório.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter

from trembr.config import ModeloCustos, Norma
from trembr.terreno.dem import Raster
from trembr.tracado.secao import param_secao, secao_vetor


def superficie_custo(
    dem: Raster,
    norma: Norma,
    custos: ModeloCustos,
    *,
    janela_m: float = 1500.0,
    comprimento_rampa_m: float = 1000.0,
    cota_agua_m: float = 0.5,
) -> np.ndarray:
    """R$/m para atravessar cada célula; ``inf`` em água/mar e sem dado."""
    z = dem.dados
    sem_dado = ~np.isfinite(z)
    zf = np.where(sem_dado, np.nanmean(z), z)
    res = dem.resolucao

    w = max(3, round(janela_m / res) | 1)  # ímpar
    media = uniform_filter(zf, w, mode="nearest")
    # o filtro usa somas acumuladas; arredondamento pode dar -1e-12 → limitar em zero
    sigma = np.sqrt(np.maximum(uniform_filter((zf - media) ** 2, w, mode="nearest"), 0.0))

    gy, gx = np.gradient(media, res)
    excesso = np.maximum(0.0, np.hypot(gx, gy) - norma.rampa_max) * comprimento_rampa_m
    h = (sigma + excesso).ravel()

    p = param_secao(norma, custos)
    acima, _ = secao_vetor(np.minimum(h, p.viaduto_max), p)
    abaixo, _ = secao_vetor(-h, p)
    custo = (custos.precos.via_e_sistemas_m + 0.5 * (acima + abaixo)).reshape(z.shape)

    custo[sem_dado | (zf <= cota_agua_m)] = np.inf
    return custo

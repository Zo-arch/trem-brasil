import math

import numpy as np
import pytest

from trembr.tracado.corredor import caminho_minimo


def test_contorna_parede_pelo_unico_buraco():
    custo = np.ones((50, 50))
    custo[:, 24:27] = np.inf
    custo[40:46, 24:27] = 1.0
    rota, _ = caminho_minimo(custo, (5, 5), (5, 45), resolucao_m=10)
    na_parede = rota[(rota[:, 1] >= 24) & (rota[:, 1] <= 26)]
    assert len(na_parede) > 0
    assert np.all((na_parede[:, 0] >= 40) & (na_parede[:, 0] <= 45))


def test_vizinhanca_16_aproxima_distancia_euclidiana():
    custo = np.ones((40, 60))
    _, total = caminho_minimo(custo, (0, 0), (11, 37), resolucao_m=1.0, vizinhanca=16)
    euclid = math.hypot(11, 37)
    assert euclid <= total <= euclid * 1.03


def test_a_estrela_8_igual_a_referencia_scikit_image():
    from skimage.graph import MCP_Geometric

    rng = np.random.default_rng(42)
    for _ in range(5):
        custo = rng.uniform(1, 10, (60, 80))
        custo[rng.random(custo.shape) < 0.15] = np.inf
        custo[0, 0] = custo[59, 79] = 1.0
        ref = MCP_Geometric(np.where(np.isfinite(custo), custo, -1), sampling=(30, 30))
        acum, _ = ref.find_costs([(0, 0)], [(59, 79)])
        if not np.isfinite(acum[59, 79]):
            continue
        _, total = caminho_minimo(custo, (0, 0), (59, 79), resolucao_m=30, vizinhanca=8)
        assert math.isclose(total, acum[59, 79], rel_tol=1e-9)


def test_pulo_de_cavalo_nao_atravessa_parede_fina():
    custo = np.ones((30, 30))
    custo[:, 15] = np.inf  # parede de 1 célula, sem buraco
    with pytest.raises(RuntimeError, match="inalcançável"):
        caminho_minimo(custo, (10, 5), (10, 25), resolucao_m=1, vizinhanca=16)


def test_origem_proibida_falha():
    custo = np.ones((5, 5))
    custo[0, 0] = np.inf
    with pytest.raises(ValueError, match="origem"):
        caminho_minimo(custo, (0, 0), (4, 4), resolucao_m=1)


def test_dijkstra_varios_destinos_igual_a_estrela_um_a_um():
    from trembr.tracado.corredor import caminhos_a_partir_de

    rng = np.random.default_rng(7)
    for viz in (8, 16):
        custo = rng.uniform(1, 10, (70, 90))
        custo[rng.random(custo.shape) < 0.1] = np.inf
        pontos = [(0, 0), (69, 89), (35, 10), (5, 80), (60, 40)]
        for p in pontos:
            custo[p] = 1.0
        resultado = caminhos_a_partir_de(custo, pontos[0], pontos[1:], 30.0, viz)
        for destino, (rota, total) in zip(pontos[1:], resultado, strict=True):
            try:
                _, ref = caminho_minimo(custo, pontos[0], destino, 30.0, viz)
            except RuntimeError:
                assert not np.isfinite(total)
                continue
            assert math.isclose(total, ref, rel_tol=1e-9)
            assert tuple(rota[0]) == pontos[0] and tuple(rota[-1]) == destino

"""Monta o atlas de uma região: figuras PNG numeradas + ``index.html`` interativo.

Cada camada é um módulo com ``ID``, ``NOME``, ``COMANDO`` (como obter os dados),
``disponivel(regiao)``, ``web(regiao)`` e, se tiver figura própria, ``figura(regiao, caminho)``.
Camadas sem dados são puladas com um aviso de como obtê-los.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from trembr.atlas import base, cidades, estudos, protegidas, relevo, transporte
from trembr.atlas.web import CamadaWeb, montar_html
from trembr.paths import RESULTADOS, garantir
from trembr.regiao import carregar_regiao

# na ordem do atlas; cada camada nova entra aqui
CAMADAS = [base, relevo, cidades, transporte, protegidas, estudos]


def pasta_atlas(regiao_id: str) -> Path:
    return RESULTADOS / "atlas" / regiao_id


def caminho_html(regiao_id: str) -> Path:
    return pasta_atlas(regiao_id) / "index.html"


def montar_atlas(regiao_id: str = "sudeste", log: Callable = print) -> tuple[list[Path], Path]:
    regiao = carregar_regiao(regiao_id)
    pasta = garantir(pasta_atlas(regiao_id))
    figuras: list[Path] = []
    camadas_web: list[CamadaWeb] = []
    busca: list[dict] = []
    for i, camada in enumerate(CAMADAS, start=1):
        if not camada.disponivel(regiao):
            log(f"  – {camada.NOME}: sem dados; rode `pixi run {camada.COMANDO}`")
            continue
        log(f"  {i}. {camada.NOME}")
        if hasattr(camada, "figura"):
            figuras.append(camada.figura(regiao, pasta / f"{i:02d}_{camada.ID}.png"))
        camadas_web += camada.web(regiao)
        if hasattr(camada, "busca"):
            busca += camada.busca(regiao)
    html = montar_html(regiao, camadas_web, caminho_html(regiao_id), busca)
    return figuras, html

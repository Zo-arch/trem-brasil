"""Monta o atlas de uma região: figuras PNG numeradas + ``index.html`` interativo."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from trembr.atlas import base, cidades, protegidas, relevo, transporte
from trembr.atlas.web import CamadaWeb, montar_html
from trembr.paths import RESULTADOS, garantir
from trembr.regiao import carregar_regiao

CAMADAS = [
    base,
    relevo,
    cidades,
    transporte,
    protegidas,
]  # na ordem do atlas; cada camada nova da Fase 1 entra aqui


def montar_atlas(regiao_id: str = "sudeste", log: Callable = print) -> tuple[list[Path], Path]:
    regiao = carregar_regiao(regiao_id)
    pasta = garantir(RESULTADOS / "atlas" / regiao.id)
    figuras: list[Path] = []
    camadas_web: list[CamadaWeb] = []
    for i, camada in enumerate(CAMADAS, start=1):
        if not camada.disponivel(regiao):
            log(f"  – {camada.NOME}: sem dados; rode `pixi run {camada.COMANDO}`")
            continue
        log(f"  {i}. {camada.NOME}")
        figuras.append(camada.figura(regiao, pasta / f"{i:02d}_{camada.ID}.png"))
        camadas_web += camada.web(regiao)
    html = montar_html(regiao, camadas_web, pasta / "index.html")
    return figuras, html

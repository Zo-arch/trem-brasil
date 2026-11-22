"""Catálogo de fontes de dados (data/catalogo.yaml), validado."""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel

from trembr.paths import CATALOGO

Camada = Literal[
    "base",
    "terreno",
    "geologia",
    "hidrografia",
    "restricoes",
    "infraestrutura",
    "demanda",
    "custos",
    "validacao",
]


class Fonte(BaseModel):
    id: str
    nome: str
    camada: Camada
    provedor: str
    url: str
    licenca: str
    resolucao: str | None = None
    uso: str
    status: Literal["implementado", "planejado"]
    confirmado: bool  # URL/formato testados de verdade pelo projeto
    notas: str | None = None


def carregar_catalogo() -> list[Fonte]:
    with CATALOGO.open(encoding="utf-8") as f:
        return [Fonte(**item) for item in yaml.safe_load(f)["fontes"]]

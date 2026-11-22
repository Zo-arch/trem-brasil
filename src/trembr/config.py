"""Modelos de configuração validados (normas de projeto e custos).

Tudo que é premissa numérica do estudo vive em ``config/*.yaml`` com fonte, e é validado aqui.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from trembr.paths import CONFIG


class Norma(BaseModel):
    """Parâmetros geométricos de projeto de uma classe de ferrovia."""

    id: str
    nome: str
    status: Literal["referencia", "preliminar"]
    velocidade_projeto_kmh: float = Field(gt=0)
    raio_horizontal_min_m: float = Field(gt=0)
    rampa_max: float = Field(gt=0, lt=0.1)
    rampa_estacao_max: float = Field(ge=0, lt=0.1)
    raio_vertical_min_m: float = Field(gt=0)
    largura_plataforma_m: float = Field(gt=0)
    fontes: list[str]


class Precos(BaseModel):
    corte_m3: float = Field(ge=0)
    aterro_m3: float = Field(ge=0)
    viaduto_m: float = Field(ge=0)
    viaduto_m_por_m_altura: float = Field(ge=0)
    tunel_m: float = Field(ge=0)
    via_e_sistemas_m: float = Field(ge=0)


class Geotecnia(BaseModel):
    talude_corte_h_por_v: float = Field(ge=0)
    talude_aterro_h_por_v: float = Field(ge=0)


class Limites(BaseModel):
    aterro_altura_max_m: float = Field(gt=0)
    corte_profundidade_max_m: float = Field(gt=0)
    viaduto_altura_min_m: float = Field(ge=0)
    viaduto_altura_max_m: float = Field(gt=0)
    tunel_profundidade_min_m: float = Field(gt=0)

    @model_validator(mode="after")
    def _sem_lacunas(self) -> Limites:
        # Se houver uma faixa de altura/profundidade sem nenhuma estrutura possível, o
        # otimizador fica sem solução nesse intervalo. Isso é quase sempre erro de digitação.
        if self.viaduto_altura_min_m > self.aterro_altura_max_m:
            raise ValueError("viaduto_altura_min_m > aterro_altura_max_m deixa alturas sem solução")
        if self.tunel_profundidade_min_m > self.corte_profundidade_max_m:
            raise ValueError(
                "tunel_profundidade_min_m > corte_profundidade_max_m deixa profundidades sem solução"
            )
        if self.viaduto_altura_max_m < self.viaduto_altura_min_m:
            raise ValueError("viaduto_altura_max_m < viaduto_altura_min_m")
        return self


class ModeloCustos(BaseModel):
    id: str
    ano_base: int
    moeda: str
    status: Literal["placeholder", "calibrado"]
    precos: Precos
    geotecnia: Geotecnia
    limites: Limites
    fontes: list[str]


def _ler_yaml(caminho: Path) -> dict:
    if not caminho.exists():
        disponiveis = sorted(p.stem for p in caminho.parent.glob("*.yaml"))
        raise FileNotFoundError(f"{caminho} não existe. Disponíveis: {disponiveis}")
    with caminho.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def carregar_norma(nome: str = "as350") -> Norma:
    return Norma(id=nome, **_ler_yaml(CONFIG / "normas" / f"{nome}.yaml"))


def carregar_custos(nome: str = "referencia") -> ModeloCustos:
    return ModeloCustos(id=nome, **_ler_yaml(CONFIG / "custos" / f"{nome}.yaml"))

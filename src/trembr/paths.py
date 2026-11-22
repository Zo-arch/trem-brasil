"""Caminhos do projeto.

Os dados podem morar fora do repositório (ex.: um SSD externo) definindo a variável de ambiente
``TREMBR_DADOS``. O catálogo de fontes fica sempre versionado em ``data/catalogo.yaml``.
"""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "config"
CATALOGO = RAIZ / "data" / "catalogo.yaml"

DADOS = Path(os.environ.get("TREMBR_DADOS", RAIZ / "data"))
BRUTOS = DADOS / "raw"  # como veio da fonte; nunca editar à mão
INTERMEDIARIOS = DADOS / "interim"  # reprojeções, mosaicos, caches
PROCESSADOS = DADOS / "processed"  # tabelas e rasters prontos para os modelos

RESULTADOS = Path(os.environ.get("TREMBR_RESULTADOS", RAIZ / "resultados"))


def garantir(pasta: Path) -> Path:
    """Cria a pasta (e as mães) se não existir e devolve o próprio caminho."""
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta

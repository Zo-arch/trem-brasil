"""Registro de proveniência: todo arquivo baixado ganha um ``.proveniencia.json`` ao lado.

Isso permite responder, meses depois, "de onde veio este número?" com URL, data de acesso,
licença e hash do arquivo exato usado.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from trembr import __version__


def sha256(caminho: Path, bloco: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        while parte := f.read(bloco):
            h.update(parte)
    return h.hexdigest()


def caminho_proveniencia(arquivo: Path) -> Path:
    return arquivo.with_name(arquivo.name + ".proveniencia.json")


def registrar(
    arquivo: Path,
    *,
    fonte_id: str,
    urls: list[str],
    licenca: str,
    extra: dict | None = None,
) -> Path:
    meta = {
        "arquivo": arquivo.name,
        "fonte_id": fonte_id,
        "urls": urls,
        "licenca": licenca,
        "acessado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "sha256": sha256(arquivo),
        "bytes": arquivo.stat().st_size,
        "trembr_versao": __version__,
        **(extra or {}),
    }
    destino = caminho_proveniencia(arquivo)
    destino.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino

"""Download em streaming para arquivos grandes, com proveniência da URL final (após redirects)."""

from __future__ import annotations

import ssl
from pathlib import Path

import httpx
import truststore

from trembr import proveniencia


def contexto_tls() -> ssl.SSLContext:
    """TLS com o repositório de certificados do sistema operacional, que completa cadeias
    incompletas (o servidor de dados do MMA não envia o certificado intermediário)."""
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def baixar_grande(
    url: str,
    destino: Path,
    *,
    fonte_id: str,
    licenca: str,
    forcar: bool = False,
    agente: str = "trembr/0.1",
    log=print,
) -> Path:
    """Baixa ``url`` direto para o disco, em pedaços. Grava em ``.parcial`` e renomeia no fim.

    A proveniência guarda a URL pedida e a URL final: o Geofabrik, por exemplo, redireciona
    ``sudeste-latest.osm.pbf`` para o arquivo datado (``sudeste-261121.osm.pbf``). ``agente``
    é o User-Agent; alguns servidores públicos (GeoServer da FUNAI) recusam clientes sem
    cara de navegador.
    """
    if destino.exists() and not forcar:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    with (
        httpx.Client(
            timeout=120,
            follow_redirects=True,
            headers={"User-Agent": agente},
            verify=contexto_tls(),
        ) as c,
        c.stream("GET", url) as r,
    ):
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        final = str(r.url)
        feito, proximo_aviso = 0, 0.0
        with parcial.open("wb") as f:
            for pedaco in r.iter_bytes(1 << 20):
                f.write(pedaco)
                feito += len(pedaco)
                if total and feito / total >= proximo_aviso:
                    log(f"  {destino.name}: {feito / 1e6:,.0f} de {total / 1e6:,.0f} MB")
                    proximo_aviso += 0.25
    parcial.replace(destino)
    proveniencia.registrar(
        destino, fonte_id=fonte_id, urls=[url, final], licenca=licenca, extra={"url_final": final}
    )
    return destino

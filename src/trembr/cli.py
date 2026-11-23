"""Linha de comando: ``pixi run trembr --help``.

trembr dados tudo            baixa e prepara todas as camadas da região (Fase 1)
trembr dados <camada>        uma camada: base, relevo, cidades, transporte, protegidas
trembr atlas [--abrir]       figuras + mapa interativo da região
trembr mapa                  abre o mapa interativo (gera se ainda não existir)
trembr estudo rio-sp -v 2    roda uma versão do estudo Rio–SP
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    no_args_is_help=True, help="trem-brasil: estudo científico de uma malha de alta velocidade."
)
dados = typer.Typer(
    no_args_is_help=True, help="Baixar e preparar dados (com registro de proveniência)."
)
estudo = typer.Typer(no_args_is_help=True, help="Rodar estudos de caso.")
app.add_typer(dados, name="dados")
app.add_typer(estudo, name="estudo")
console = Console()

OPCAO_REGIAO = typer.Option("sudeste", help="Região em config/regioes.yaml")
OPCAO_FORCAR = typer.Option(False, help="Baixar de novo mesmo com cache")


# ----------------------------------------------------------------------------- dados
@dados.command("catalogo")
def catalogo(camada: str | None = typer.Option(None, help="Filtrar por camada")) -> None:
    """Lista as fontes de dados do estudo e o status de cada uma."""
    from trembr.fontes.catalogo import carregar_catalogo

    t = Table(title="Catálogo de fontes")
    for col in ("id", "camada", "nome", "status", "testada"):
        t.add_column(col)
    for f in carregar_catalogo():
        if camada and f.camada != camada:
            continue
        cor = "green" if f.status == "implementado" else "yellow"
        t.add_row(f.id, f.camada, f.nome, f"[{cor}]{f.status}[/]", "sim" if f.confirmado else "não")
    console.print(t)


@dados.command("base")
def base(forcar: bool = OPCAO_FORCAR) -> None:
    """Mapa base do IBGE: país, UFs e municípios (+ população do Censo 2022)."""
    import geopandas as gpd

    from trembr.fontes.ibge import preparar_base
    from trembr.visual import fmt_int

    arquivos = preparar_base(forcar=forcar)
    mun = gpd.read_parquet(arquivos["municipios"])
    console.print(
        f"[green]ok[/] {len(gpd.read_parquet(arquivos['ufs']))} UFs, {fmt_int(len(mun))} "
        f"municípios, {fmt_int(mun['populacao_2022'].sum())} habitantes"
    )


@dados.command("relevo")
def relevo(
    regiao: str = OPCAO_REGIAO,
    produto: str = typer.Option("glo90", help="glo90 (~90 m) ou glo30 (~30 m)"),
    forcar: bool = OPCAO_FORCAR,
) -> None:
    """Mosaico do Copernicus DEM para a região inteira (+ margem), por streaming."""
    from trembr.fontes import copernicus
    from trembr.regiao import carregar_regiao

    bbox = carregar_regiao(regiao).bbox()
    console.print(f"{regiao}: até {len(copernicus.tiles_bbox(bbox))} tiles {produto}…")
    console.print(f"[green]ok[/] {copernicus.ler_bbox(bbox, produto, forcar=forcar)}")


@dados.command("cidades")
def cidades(forcar: bool = OPCAO_FORCAR) -> None:
    """Sedes, PIB, hierarquia urbana (REGIC 2018) e áreas urbanizadas 2022 do IBGE."""
    import geopandas as gpd

    from trembr.fontes.cidades import preparar_cidades
    from trembr.visual import fmt_int

    arq = preparar_cidades(forcar=forcar)
    console.print(
        f"[green]ok[/] {fmt_int(len(gpd.read_parquet(arq['cidades'])))} municípios; "
        f"{fmt_int(len(gpd.read_parquet(arq['cidades_regic'])))} cidades do REGIC"
    )


@dados.command("transporte")
def transporte(regiao: str = OPCAO_REGIAO, forcar: bool = OPCAO_FORCAR) -> None:
    """Rodovias, ferrovias, estações e aeroportos do OpenStreetMap (extrato do Geofabrik)."""
    import geopandas as gpd

    from trembr.fontes.osm import preparar_transporte

    for tipo, arq in preparar_transporte(regiao, forcar=forcar, log=console.print).items():
        console.print(f"[green]ok[/] {tipo}: {len(gpd.read_parquet(arq)):,} feições")


@dados.command("protegidas")
def protegidas(forcar: bool = OPCAO_FORCAR) -> None:
    """Unidades de conservação (CNUC/MMA) e terras indígenas (FUNAI, arquivo local)."""
    import geopandas as gpd

    from trembr.fontes.protegidas import preparar_areas_protegidas

    for tipo, arq in preparar_areas_protegidas(forcar=forcar, log=console.print).items():
        console.print(f"[green]ok[/] {tipo}: {len(gpd.read_parquet(arq)):,} polígonos")


@dados.command("tudo")
def tudo(regiao: str = OPCAO_REGIAO, forcar: bool = OPCAO_FORCAR) -> None:
    """Todas as camadas da Fase 1, na ordem do atlas (o que já existe fica em cache)."""
    etapas = [
        ("mapa base", lambda: base(forcar)),
        ("relevo", lambda: relevo(regiao, "glo90", forcar)),
        ("cidades", lambda: cidades(forcar)),
        ("transporte", lambda: transporte(regiao, forcar)),
        ("áreas protegidas", lambda: protegidas(forcar)),
    ]
    for i, (nome, etapa) in enumerate(etapas, start=1):
        console.rule(f"{i}/{len(etapas)} {nome}")
        etapa()
    console.print("[green]pronto.[/] Próximo passo: [bold]pixi run atlas[/]")


@dados.command("dem")
def dem(
    bbox: str = typer.Option(
        ..., help='"oeste,sul,leste,norte" em graus, ex.: "-47,-23.9,-43,-22.2"'
    ),
    produto: str = typer.Option("glo90", help="glo90 ou glo30"),
) -> None:
    """Recorta o Copernicus DEM num bbox qualquer (streaming, sem baixar tiles inteiros)."""
    from trembr.fontes import copernicus

    valores = tuple(float(v) for v in bbox.split(","))
    if len(valores) != 4:
        raise typer.BadParameter("bbox precisa de 4 números")
    console.print(f"[green]ok[/] {copernicus.ler_bbox(valores, produto)}")


# ----------------------------------------------------------------------------- atlas
@app.command("atlas")
def atlas(
    regiao: str = OPCAO_REGIAO,
    abrir: bool = typer.Option(False, help="Abrir o mapa interativo no navegador ao final"),
) -> None:
    """Atlas: uma figura PNG por camada + mapa interativo (index.html)."""
    from trembr.atlas.montar import montar_atlas

    console.print(f"Atlas · {regiao}")
    figuras, html = montar_atlas(regiao, log=console.print)
    for f in figuras:
        console.print(f"[green]figura:[/] {f}")
    console.print(f"[green]mapa interativo:[/] {html}")
    if abrir:
        _abrir(html)


@app.command("mapa")
def mapa(regiao: str = OPCAO_REGIAO) -> None:
    """Abre o mapa interativo da região (gera o atlas antes, se ainda não existir)."""
    from trembr.atlas.montar import caminho_html, montar_atlas

    html = caminho_html(regiao)
    if not html.exists():
        console.print("O mapa ainda não existe; gerando o atlas (2 a 3 minutos)…")
        _, html = montar_atlas(regiao, log=console.print)
    console.print(f"Abrindo {html}")
    _abrir(html)


def _abrir(caminho) -> None:
    import webbrowser

    webbrowser.open(caminho.as_uri())


# ----------------------------------------------------------------------------- estudos
@estudo.command("rio-sp")
def rio_sp(
    versao: int = typer.Option(2, "--versao", "-v", help="1 = só relevo; 2 = relevo + cidades"),
    config: str = typer.Option("rio_sp", help="Arquivo em config/estudos"),
) -> None:
    """Estudo Rio–São Paulo, uma versão por vez (docs/roteiro.md, Fase 2)."""
    from trembr.estudos.rio_sp import rodar
    from trembr.visual import fmt_dec, fmt_int

    resumo, figura = rodar(versao, config, log=console.print)
    if versao == 1:
        t = Table(title="Rio–SP v1: só relevo", show_header=False)
        t.add_row("extensão", f"{fmt_dec(resumo['extensao_km'])} km")
        for nome, km in resumo["km_por_estrutura"].items():
            t.add_row(nome, f"{fmt_dec(km)} km ({fmt_dec(resumo['pct_por_estrutura'][nome])}%)")
        t.add_row("raio horizontal mín.", f"{fmt_int(resumo['raio_horizontal_min_m'])} m")
    else:
        t = Table(title="Rio–SP v2: rotas em destaque")
        for col in ("rota", "paradas", "pessoas", "km", "túnel", "custo (km-eq)"):
            t.add_column(col)
        for nome, r in resumo["destaques"].items():
            t.add_row(
                nome,
                ", ".join(p.rsplit("/", 1)[0] for p in r["paradas"]) or "—",
                f"{fmt_dec(r['populacao_atendida'] / 1e6, 2)} mi",
                fmt_int(r["extensao_km"]),
                f"{fmt_dec(r['pct_por_estrutura']['túnel'])}%",
                fmt_int(r["custo_corredor_km_eq"]),
            )
    console.print(t)
    console.print(f"[green]figura:[/] {figura}  ({resumo['tempo_execucao_s']} s)")


if __name__ == "__main__":
    app()

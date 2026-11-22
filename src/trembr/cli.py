"""Linha de comando: ``pixi run trembr --help``."""

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


@dados.command("dem")
def dem(
    bbox: str = typer.Option(
        ..., help='"oeste,sul,leste,norte" em graus, ex.: "-47,-23.9,-43,-22.2"'
    ),
    produto: str = typer.Option("glo90", help="glo90 ou glo30"),
) -> None:
    """Recorta o Copernicus DEM num bbox (streaming, sem baixar tiles inteiros)."""
    from trembr.fontes import copernicus

    valores = tuple(float(v) for v in bbox.split(","))
    if len(valores) != 4:
        raise typer.BadParameter("bbox precisa de 4 números")
    console.print(f"[green]ok[/] {copernicus.ler_bbox(valores, produto)}")


@dados.command("base")
def base(forcar: bool = typer.Option(False, help="Baixar de novo mesmo com cache")) -> None:
    """Mapa base do IBGE: país, UFs e municípios (+ população do Censo 2022) → GeoParquet."""
    import geopandas as gpd

    from trembr.atlas.estilo import fmt_int
    from trembr.fontes.ibge import preparar_base

    arquivos = preparar_base(forcar=forcar)
    mun = gpd.read_parquet(arquivos["municipios"])
    ufs = gpd.read_parquet(arquivos["ufs"])
    console.print(
        f"[green]ok[/] {len(ufs)} UFs, {fmt_int(len(mun))} municípios, "
        f"{fmt_int(mun['populacao_2022'].sum())} habitantes → {arquivos['ufs'].parent}"
    )


@dados.command("relevo")
def relevo(
    regiao: str = typer.Option("sudeste", help="Região em config/regioes.yaml"),
    produto: str = typer.Option("glo90", help="glo90 (~90 m) ou glo30 (~30 m)"),
    forcar: bool = typer.Option(False, help="Baixar de novo mesmo com cache"),
) -> None:
    """Mosaico do Copernicus DEM para a região inteira (+ margem), por streaming."""
    from trembr.fontes import copernicus
    from trembr.regiao import carregar_regiao

    bbox = carregar_regiao(regiao).bbox()
    n = len(copernicus.tiles_bbox(bbox))
    console.print(f"{regiao}: até {n} tiles {produto} (oceano não tem tile)…")
    console.print(f"[green]ok[/] {copernicus.ler_bbox(bbox, produto, forcar=forcar)}")


@app.command("atlas")
def atlas(
    regiao: str = typer.Option("sudeste", help="Região em config/regioes.yaml"),
    abrir: bool = typer.Option(False, help="Abrir o mapa interativo no navegador ao final"),
) -> None:
    """Atlas da Fase 1: uma figura PNG por camada + mapa interativo (index.html)."""
    from trembr.atlas.montar import montar_atlas

    console.print(f"Atlas · {regiao}")
    figuras, html = montar_atlas(regiao, log=console.print)
    for f in figuras:
        console.print(f"[green]figura:[/] {f}")
    console.print(f"[green]mapa interativo:[/] {html}")
    if abrir:
        import webbrowser

        webbrowser.open(html.as_uri())


@estudo.command("sp-rj")
def sp_rj(
    norma: str = typer.Option("as350", help="Arquivo em config/normas"),
    custos: str = typer.Option("referencia", help="Arquivo em config/custos"),
    passo: float = typer.Option(100.0, help="Espaçamento desejado das estacas (m)"),
) -> None:
    """Corredor + greide ótimo São Paulo ↔ Rio de Janeiro."""
    from trembr.estudos.sp_rj import rodar

    resumo, figura = rodar(norma, custos, passo, log=console.print)
    t = Table(title="Resumo SP–RJ", show_header=False)
    t.add_row(
        "extensão", f"{resumo['extensao_km']:.1f} km (reta: {resumo['distancia_reta_km']:.1f} km)"
    )
    for nome, km in resumo["km_por_estrutura"].items():
        t.add_row(nome, f"{km:.1f} km ({resumo['pct_por_estrutura'][nome]:.1f}%)")
    t.add_row("rampa máx. usada", f"{1000 * resumo['rampa_max_usada']:.1f}‰")
    t.add_row("raio horizontal mín.", f"{resumo['raio_horizontal_min_m']:.0f} m")
    t.add_row("custo (PLACEHOLDER)", f"R$ {resumo['custo_total_bilhoes']:.0f} bi — não citar")
    t.add_row("tempo", f"{resumo['tempo_execucao_s']} s")
    console.print(t)
    console.print(f"[green]figura:[/] {figura}")


if __name__ == "__main__":
    app()

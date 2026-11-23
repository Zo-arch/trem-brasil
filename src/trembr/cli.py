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


@dados.command("cidades")
def cidades(forcar: bool = typer.Option(False, help="Baixar de novo mesmo com cache")) -> None:
    """Sedes, PIB, hierarquia urbana (REGIC 2018) e áreas urbanizadas 2022 do IBGE."""
    import geopandas as gpd

    from trembr.atlas.estilo import fmt_int
    from trembr.fontes.cidades import preparar_cidades

    arq = preparar_cidades(forcar=forcar)
    cid, reg = gpd.read_parquet(arq["cidades"]), gpd.read_parquet(arq["cidades_regic"])
    console.print(
        f"[green]ok[/] {fmt_int(len(cid))} municípios com sede, PIB e REGIC; "
        f"{fmt_int(len(reg))} cidades do REGIC → {arq['cidades'].parent}"
    )


@dados.command("transporte")
def transporte(
    regiao: str = typer.Option("sudeste", help="Região em config/regioes.yaml"),
    forcar: bool = typer.Option(False, help="Baixar de novo mesmo com cache"),
) -> None:
    """Rodovias, ferrovias, estações e aeroportos do OpenStreetMap (extrato do Geofabrik)."""
    import geopandas as gpd

    from trembr.fontes.osm import preparar_transporte

    arquivos = preparar_transporte(regiao, forcar=forcar, log=console.print)
    for tipo, arq in arquivos.items():
        console.print(f"[green]ok[/] {tipo}: {len(gpd.read_parquet(arq)):,} feições → {arq.name}")


@dados.command("protegidas")
def protegidas(forcar: bool = typer.Option(False, help="Baixar de novo mesmo com cache")) -> None:
    """Unidades de conservação (CNUC/MMA) e terras indígenas (FUNAI, arquivo local)."""
    import geopandas as gpd

    from trembr.fontes.protegidas import preparar_areas_protegidas, resumo_ucs

    arquivos = preparar_areas_protegidas(forcar=forcar, log=console.print)
    console.print(resumo_ucs(gpd.read_parquet(arquivos["ucs"])))
    for tipo, arq in arquivos.items():
        console.print(f"[green]ok[/] {tipo}: {len(gpd.read_parquet(arq)):,} polígonos → {arq.name}")


@estudo.command("rio-sp-v2")
def rio_sp_v2(config: str = typer.Option("rio_sp", help="Arquivo em config/estudos")) -> None:
    """Rio–SP v2: relevo + cidades; o otimizador escolhe as paradas (fronteira de Pareto)."""
    from trembr.estudos.rio_sp import rodar

    resumo, figura = rodar(config, log=console.print)
    t = Table(title="Rio–SP v2: rotas em destaque")
    for col in ("rota", "paradas", "pessoas", "km", "túnel", "viaduto", "custo (km-eq)"):
        t.add_column(col)
    for nome, r in resumo["destaques"].items():
        t.add_row(
            nome,
            ", ".join(p.rsplit("/", 1)[0] for p in r["paradas"]) or "—",
            f"{r['populacao_atendida'] / 1e6:.2f} mi",
            f"{r['extensao_km']:.0f}",
            f"{r['pct_por_estrutura']['túnel']:.1f}%",
            f"{r['pct_por_estrutura']['viaduto']:.1f}%",
            f"{r['custo_corredor_km_eq']:.0f}",
        )
    console.print(t)
    console.print(f"[green]figura:[/] {figura}  ({resumo['tempo_execucao_s']} s)")


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

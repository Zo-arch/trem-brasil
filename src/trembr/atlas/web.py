"""Mapa interativo do atlas: um único HTML (MapLibre GL) com as camadas liga/desliga.

Os dados vão embutidos no arquivo (GeoJSON simplificado e imagens em data URI), então ele abre
direto do disco, sem servidor. Os rótulos de cidades são desenhados com os nossos dados.
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import geopandas as gpd
import numpy as np
import shapely
from affine import Affine
from pyproj import Transformer

from trembr.crs import BRASIL_POLICONICA
from trembr.regiao import Regiao

MAPLIBRE = "https://unpkg.com/maplibre-gl@4.7.1/dist"
# fontes dos rótulos (glifos do OpenMapTiles, públicos e sem chave)
GLIFOS = "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf"
ATRIBUICAO = (
    "IBGE · MMA · FUNAI · Copernicus DEM © DLR/Airbus · © colaboradores do OpenStreetMap (ODbL)"
)
WGS84 = "EPSG:4326"


@dataclass
class CamadaWeb:
    id: str
    nome: str  # rótulo no painel
    grupo: str  # título do bloco no painel (ex.: "Mapa base")
    tipo: Literal["fill", "line", "circle", "raster", "symbol"]
    pintura: dict  # propriedades "paint" do MapLibre
    cor: str  # amostra de cor no painel
    geojson: dict | None = None
    imagens: list[dict] | None = None  # [{"url": data URI, "cantos": [[lon, lat]] NO, NE, SE, SO}]
    visivel: bool = True
    popup: dict[str, str] = field(default_factory=dict)  # campo → rótulo
    titulo_popup: str | None = None  # campo usado como título do popup
    ordem: int = 20  # ordem de desenho: 0 terra, 10 rasters, 20–40 vetores, 50 divisas, 60 pontos
    no_painel: bool = True  # False = camada fixa, sem alternador
    contorno: dict | None = None  # "paint" de uma camada de linha extra (o fill-opacity apaga o
    # contorno nativo do MapLibre); liga e desliga junto com a camada
    legenda: list[list[str]] | None = None  # [[cor, rótulo]] mostrado sob o alternador
    gradiente: list[str] | None = None  # cores de uma escala contínua (ex.: altitude)
    gradiente_rotulos: list[str] | None = None  # [início, fim] da escala
    layout: dict | None = None  # propriedades "layout" extras (ex.: rótulos)
    minzoom: float = 0  # só aparece a partir deste zoom
    alterna_com: str | None = None  # id da camada cujo alternador também liga/desliga esta


def para_geojson(
    gdf: gpd.GeoDataFrame, campos: list[str], tolerancia_m: float = 0.0, casas: int = 5
) -> dict:
    """GeoJSON leve: só ``campos``, geometria simplificada (em metros) e coordenadas arredondadas."""
    g = gdf[[*campos, "geometry"]].copy()
    if tolerancia_m > 0:
        g = g.to_crs(BRASIL_POLICONICA)
        g["geometry"] = g.geometry.simplify(tolerancia_m, preserve_topology=True)
    g = g.to_crs(WGS84)
    g["geometry"] = shapely.set_precision(g.geometry.values, 10.0**-casas, mode="pointwise")
    g = g[~g.geometry.is_empty]
    for c in campos:
        if g[c].dtype.kind in "iu" or str(g[c].dtype) == "Int64":
            g[c] = g[c].astype("float").round().astype("Int64")
    return json.loads(g.to_json(drop_id=True))


def imagem_data_uri(rgb: np.ndarray, formato: Literal["JPEG", "PNG"] = "JPEG") -> str:
    """Array (linhas, colunas, 3 ou 4) uint8 → data URI."""
    from PIL import Image

    buf = io.BytesIO()
    img = Image.fromarray(rgb)
    if formato == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=85, optimize=True)
    else:
        img.save(buf, "PNG", optimize=True)
    return f"data:image/{formato.lower()};base64," + base64.b64encode(buf.getvalue()).decode()


def ladrilhos(
    imagem: np.ndarray,
    transform: Affine,
    formato: Literal["JPEG", "PNG"] = "PNG",
    max_px: int = 4096,
) -> list[dict]:
    """Corta uma imagem em EPSG:3857 em pedaços de até ``max_px`` (limite seguro de textura
    WebGL) e devolve as fontes de imagem do MapLibre. Pedaços 100% transparentes são pulados."""
    para_lonlat = Transformer.from_crs("EPSG:3857", WGS84, always_xy=True)
    h, w = imagem.shape[:2]
    ny, nx = -(-h // max_px), -(-w // max_px)
    saida = []
    for i in range(ny):
        for j in range(nx):
            r0, r1, c0, c1 = i * h // ny, (i + 1) * h // ny, j * w // nx, (j + 1) * w // nx
            bloco = imagem[r0:r1, c0:c1]
            if bloco.shape[-1] == 4 and not bloco[..., 3].any():
                continue
            x0, y0 = transform * (c0, r0)
            x1, y1 = transform * (c1, r1)
            cantos = [
                list(para_lonlat.transform(x, y))
                for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
            ]
            saida.append({"url": imagem_data_uri(bloco, formato), "cantos": cantos})
    return saida


def montar_html(
    regiao: Regiao, camadas: list[CamadaWeb], caminho: Path, busca: list[dict] | None = None
) -> Path:
    """Escreve o HTML autossuficiente. ``busca``: [{"n": nome, "c": [lon, lat], "d": texto}]
    para a caixa de busca de cidades."""
    oeste, sul, leste, norte = regiao.bbox()
    dados = json.dumps([asdict(c) for c in camadas], ensure_ascii=False, separators=(",", ":"))
    indice = json.dumps(busca or [], ensure_ascii=False, separators=(",", ":"))
    html = (
        _MODELO.replace("__TITULO__", f"Atlas · {regiao.nome}")
        .replace("__MAPLIBRE__", MAPLIBRE)
        .replace("__GLIFOS__", GLIFOS)
        .replace("__ATRIBUICAO__", ATRIBUICAO)
        .replace("__LIMITES__", json.dumps([[oeste, sul], [leste, norte]]))
        .replace("__BUSCA__", indice.replace("</", "<\\/"))
        .replace("__CAMADAS__", dados.replace("</", "<\\/"))
    )
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(html, encoding="utf-8")
    return caminho


_MODELO = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__</title>
<link rel="stylesheet" href="__MAPLIBRE__/maplibre-gl.css">
<script src="__MAPLIBRE__/maplibre-gl.js"></script>
<style>
  :root { --tinta: #2b2b29; --tinta2: #6b6a63; --linha: #e4e3de; --papel: #ffffff; }
  html, body, #mapa { margin: 0; height: 100%; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--tinta); }
  #painel { position: absolute; top: 12px; left: 12px; width: 300px; max-height: calc(100% - 48px);
    display: flex; flex-direction: column; background: var(--papel); border-radius: 10px;
    box-shadow: 0 2px 14px rgba(0, 0, 0, .18); font-size: 13px; }
  #cabecalho { padding: 12px 14px 10px; border-bottom: 1px solid var(--linha); }
  #cabecalho h1 { font-size: 15px; margin: 0; display: flex; justify-content: space-between;
    align-items: center; }
  #recolher { border: 0; background: none; font-size: 20px; line-height: 1; cursor: pointer;
    color: var(--tinta2); padding: 0 4px; }
  .sub { color: var(--tinta2); font-size: 12px; margin-top: 2px; }
  #busca { margin-top: 8px; width: 100%; box-sizing: border-box; padding: 7px 9px;
    border: 1px solid #c9c7bf; border-radius: 6px; font: inherit; }
  #ver-tudo { margin-top: 6px; width: 100%; font: inherit; font-size: 12px; padding: 5px;
    border: 1px solid #c9c7bf; background: #f6f5f2; border-radius: 6px; cursor: pointer; }
  #conteudo { overflow: auto; padding: 2px 14px 12px; }
  #painel.recolhido #conteudo, #painel.recolhido #busca, #painel.recolhido #ver-tudo,
  #painel.recolhido .sub { display: none; }
  .grupo { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
    color: var(--tinta2); margin: 12px 0 4px; }
  label { display: flex; align-items: center; gap: 8px; padding: 3px 0; cursor: pointer; }
  .cor { width: 14px; height: 14px; border-radius: 3px; flex: none;
    border: 1px solid rgba(0, 0, 0, .15); }
  .legenda { margin: 1px 0 6px 22px; font-size: 11.5px; color: var(--tinta2); }
  .legenda div { display: flex; align-items: center; gap: 6px; margin: 2px 0; }
  .legenda i { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .gradiente { height: 8px; border-radius: 4px; margin: 4px 0 1px; }
  .gradiente-rotulos { display: flex; justify-content: space-between; }
  .rodape { margin-top: 12px; color: var(--tinta2); font-size: 11px; line-height: 1.4; }
  .maplibregl-popup-content { font: 13px system-ui, sans-serif; padding: 10px 12px; }
  .popup { max-width: 300px; }
  .popup b { display: block; margin-bottom: 4px; font-size: 14px; }
  .popup td { padding: 1px 8px 1px 0; vertical-align: top; }
  .popup td + td { text-align: right; font-variant-numeric: tabular-nums; }
  @media (max-width: 600px) { #painel { width: auto; right: 12px; max-height: 55%; } }
</style>
</head>
<body>
<div id="mapa"></div>
<div id="painel">
  <div id="cabecalho">
    <h1>trem-brasil <button id="recolher" title="Recolher o painel"
      aria-label="Recolher o painel">–</button></h1>
    <div class="sub">__TITULO__</div>
    <input id="busca" list="lista-busca" placeholder="Buscar cidade (ex.: Taubaté)"
      autocomplete="off" aria-label="Buscar cidade">
    <datalist id="lista-busca"></datalist>
    <button id="ver-tudo">Ver a região inteira</button>
  </div>
  <div id="conteudo">
    <div id="camadas"></div>
    <div class="rodape">Clique num elemento para ver os dados. Fontes e licenças no
      <code>data/catalogo.yaml</code> do projeto.</div>
  </div>
</div>
<script>
window.__erros = [];
window.addEventListener("error", e => window.__erros.push(String(e.message)));
const CAMADAS = __CAMADAS__;
const BUSCA = __BUSCA__;
const LIMITES = __LIMITES__;
const map = new maplibregl.Map({
  container: "mapa",
  bounds: LIMITES,
  fitBoundsOptions: { padding: 24 },
  attributionControl: { compact: true, customAttribution: "__ATRIBUICAO__" },
  style: {
    version: 8,
    glyphs: "__GLIFOS__",
    sources: {},
    layers: [{ id: "fundo", type: "background", paint: { "background-color": "#dce9f5" } }],
  },
});
map.on("error", e => window.__erros.push(String(e.error?.message || e.error || e)));
map.addControl(new maplibregl.NavigationControl(), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

const fmt = v => typeof v === "number" ? v.toLocaleString("pt-BR") : (v ?? "—");
const semAcento = t => t.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase();

function legendaHtml(c) {
  let h = "";
  if (c.gradiente) {
    h += `<div class="gradiente" style="background:linear-gradient(90deg,${c.gradiente.join(",")})"></div>`
      + `<div class="gradiente-rotulos"><span>${c.gradiente_rotulos[0]}</span>`
      + `<span>${c.gradiente_rotulos[1]}</span></div>`;
  }
  for (const [cor, rotulo] of c.legenda || []) {
    h += `<div><i style="background:${cor}"></i>${rotulo}</div>`;
  }
  return h ? `<div class="legenda">${h}</div>` : "";
}

function alternador(ids, c, grupoEl) {
  const l = document.createElement("label");
  l.innerHTML = `<input type="checkbox" ${c.visivel ? "checked" : ""}>`
    + `<span class="cor" style="background:${c.cor}"></span>${c.nome}`;
  const leg = document.createElement("div");
  leg.innerHTML = legendaHtml(c);
  leg.style.display = c.visivel ? "" : "none";
  l.querySelector("input").addEventListener("change", e => {
    ids.forEach(id => map.setLayoutProperty(id, "visibility", e.target.checked ? "visible" : "none"));
    leg.style.display = e.target.checked ? "" : "none";
  });
  grupoEl.appendChild(l);
  grupoEl.appendChild(leg);
}

map.on("load", () => {
  const painel = document.getElementById("camadas");
  const grupos = {};
  const grupo = nome => {
    if (!grupos[nome]) {
      const t = document.createElement("div");
      t.className = "grupo";
      t.textContent = nome;
      painel.appendChild(t);
      grupos[nome] = document.createElement("div");
      painel.appendChild(grupos[nome]);
    }
    return grupos[nome];
  };
  for (const c of CAMADAS) if (c.no_painel) grupo(c.grupo);  // grupos na ordem do atlas
  const idsDe = {};

  for (const c of [...CAMADAS].sort((a, b) => a.ordem - b.ordem)) {
    const dono = CAMADAS.find(d => d.id === (c.alterna_com || c.id));
    const layout = { ...(c.layout || {}), visibility: dono.visivel ? "visible" : "none" };
    let ids = [c.id];
    if (c.tipo === "raster") {
      ids = c.imagens.map((img, i) => {
        const id = `${c.id}-${i}`;
        map.addSource(id, { type: "image", url: img.url, coordinates: img.cantos });
        map.addLayer({ id, type: "raster", source: id, paint: c.pintura, layout });
        return id;
      });
    } else {
      map.addSource(c.id, { type: "geojson", data: c.geojson });
      map.addLayer({ id: c.id, type: c.tipo, source: c.id, paint: c.pintura, layout,
        minzoom: c.minzoom });
      if (c.contorno) {
        map.addLayer({ id: c.id + "-contorno", type: "line", source: c.id, paint: c.contorno, layout });
        ids.push(c.id + "-contorno");
      }
    }
    if (Object.keys(c.popup).length) {
      map.on("click", c.id, e => {
        const p = e.features[0].properties;
        const linhas = Object.entries(c.popup)
          .map(([k, r]) => `<tr><td>${r}</td><td>${fmt(p[k])}</td></tr>`).join("");
        const titulo = c.titulo_popup ? `<b>${p[c.titulo_popup]}</b>` : "";
        new maplibregl.Popup().setLngLat(e.lngLat)
          .setHTML(`<div class="popup">${titulo}<table>${linhas}</table></div>`).addTo(map);
      });
      map.on("mouseenter", c.id, () => map.getCanvas().style.cursor = "pointer");
      map.on("mouseleave", c.id, () => map.getCanvas().style.cursor = "");
    }
    (idsDe[c.alterna_com || c.id] ||= []).push(...ids);
  }
  for (const c of CAMADAS) {
    if (c.no_painel && !c.alterna_com) alternador(idsDe[c.id], c, grupo(c.grupo));
  }
});

// busca de cidade
document.getElementById("lista-busca").innerHTML =
  BUSCA.map(b => `<option value="${b.n}">`).join("");
const indice = new Map(BUSCA.map(b => [semAcento(b.n), b]));
let realce;
document.getElementById("busca").addEventListener("change", e => {
  const q = semAcento(e.target.value.trim());
  if (!q) return;
  const alvo = indice.get(q) || BUSCA.find(b => semAcento(b.n).startsWith(q));
  if (!alvo) return;
  map.flyTo({ center: alvo.c, zoom: 10.5 });
  realce?.remove();
  realce = new maplibregl.Popup().setLngLat(alvo.c)
    .setHTML(`<div class="popup"><b>${alvo.n}</b>${alvo.d || ""}</div>`).addTo(map);
});
document.getElementById("ver-tudo").addEventListener("click",
  () => map.fitBounds(LIMITES, { padding: 24 }));
document.getElementById("recolher").addEventListener("click", e => {
  const p = document.getElementById("painel");
  p.classList.toggle("recolhido");
  e.target.textContent = p.classList.contains("recolhido") ? "+" : "–";
});
</script>
</body>
</html>
"""

"""Mapa interativo do atlas: um único HTML (MapLibre GL) com as camadas liga/desliga.

Os dados vão embutidos no arquivo (GeoJSON simplificado e imagens em data URI), então ele abre
direto do disco, sem servidor. O fundo opcional de ruas vem dos tiles públicos da CARTO.
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

from trembr.crs import BRASIL_POLICONICA
from trembr.regiao import Regiao

MAPLIBRE = "https://unpkg.com/maplibre-gl@4.7.1/dist"
WGS84 = "EPSG:4326"


@dataclass
class CamadaWeb:
    id: str
    nome: str  # rótulo no painel
    grupo: str  # título do bloco no painel (ex.: "Mapa base")
    tipo: Literal["fill", "line", "circle", "raster"]
    pintura: dict  # propriedades "paint" do MapLibre
    cor: str  # amostra de cor no painel
    geojson: dict | None = None
    imagem: str | None = None  # data URI
    cantos: list[list[float]] | None = None  # [[lon, lat]] NO, NE, SE, SO
    visivel: bool = True
    popup: dict[str, str] = field(default_factory=dict)  # campo → rótulo
    titulo_popup: str | None = None  # campo usado como título do popup
    ordem: int = 20  # ordem de desenho: 0 terra, 10 rasters, 20–40 vetores, 50 divisas, 60 pontos
    no_painel: bool = True  # False = camada fixa, sem alternador
    contorno: dict | None = None  # "paint" de uma camada de linha extra (o fill-opacity apaga o
    # contorno nativo do MapLibre); liga e desliga junto com a camada


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


def montar_html(regiao: Regiao, camadas: list[CamadaWeb], caminho: Path) -> Path:
    oeste, sul, leste, norte = regiao.bbox()
    dados = json.dumps([asdict(c) for c in camadas], ensure_ascii=False, separators=(",", ":"))
    html = (
        _MODELO.replace("__TITULO__", f"Atlas · {regiao.nome}")
        .replace("__MAPLIBRE__", MAPLIBRE)
        .replace("__LIMITES__", json.dumps([[oeste, sul], [leste, norte]]))
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
  html, body, #mapa { margin: 0; height: 100%; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: #2b2b29; }
  #painel { position: absolute; top: 12px; left: 12px; width: 260px; max-height: calc(100% - 60px);
    overflow: auto; background: #fff; border-radius: 10px; padding: 14px 16px; font-size: 13px;
    box-shadow: 0 2px 14px rgba(0, 0, 0, .18); }
  #painel h1 { font-size: 15px; margin: 0; }
  #painel .sub { color: #6b6a63; font-size: 12px; margin: 2px 0 6px; }
  .grupo { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #6b6a63;
    margin: 12px 0 4px; }
  label { display: flex; align-items: center; gap: 8px; padding: 3px 0; cursor: pointer; }
  .cor { width: 14px; height: 14px; border-radius: 3px; flex: none;
    border: 1px solid rgba(0, 0, 0, .15); }
  .rodape { margin-top: 12px; color: #6b6a63; font-size: 11px; line-height: 1.4; }
  .maplibregl-popup-content { font: 13px system-ui, sans-serif; padding: 10px 12px; }
  .popup b { display: block; margin-bottom: 4px; font-size: 14px; }
  .popup td { padding: 1px 8px 1px 0; } .popup td + td { text-align: right; font-variant-numeric: tabular-nums; }
  @media (max-width: 600px) { #painel { width: auto; right: 12px; max-height: 40%; } }
</style>
</head>
<body>
<div id="mapa"></div>
<div id="painel">
  <h1>trem-brasil</h1>
  <div class="sub">__TITULO__</div>
  <div id="camadas"></div>
  <div class="rodape">Clique num elemento para ver os dados.<br>
    Dados: IBGE e demais fontes do <code>data/catalogo.yaml</code>.
    Fundo de ruas © OpenStreetMap, © CARTO.</div>
</div>
<script>
window.__erros = [];
window.addEventListener("error", e => window.__erros.push(String(e.message)));
const CAMADAS = __CAMADAS__;
const map = new maplibregl.Map({
  container: "mapa",
  bounds: __LIMITES__,
  fitBoundsOptions: { padding: 24 },
  attributionControl: { compact: true },
  style: {
    version: 8,
    sources: {
      ruas: { type: "raster", tileSize: 256, attribution: "© OpenStreetMap © CARTO",
        tiles: ["a", "b", "c", "d"].map(s => `https://${s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png`) },
    },
    layers: [
      { id: "fundo", type: "background", paint: { "background-color": "#dce9f5" } },
      { id: "ruas", type: "raster", source: "ruas", layout: { visibility: "none" } },
    ],
  },
});
map.addControl(new maplibregl.NavigationControl(), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

const fmt = v => typeof v === "number" ? v.toLocaleString("pt-BR") : (v ?? "—");

function alternador(ids, nome, cor, visivel, grupoEl) {
  const l = document.createElement("label");
  l.innerHTML = `<input type="checkbox" ${visivel ? "checked" : ""}><span class="cor" style="background:${cor}"></span>${nome}`;
  l.querySelector("input").addEventListener("change", e => ids.forEach(id =>
    map.setLayoutProperty(id, "visibility", e.target.checked ? "visible" : "none")));
  grupoEl.appendChild(l);
}

map.on("load", () => {
  const painel = document.getElementById("camadas");
  const grupos = {};
  const grupo = nome => {
    if (!grupos[nome]) {
      const t = document.createElement("div"); t.className = "grupo"; t.textContent = nome;
      painel.appendChild(t);
      grupos[nome] = document.createElement("div"); painel.appendChild(grupos[nome]);
    }
    return grupos[nome];
  };
  alternador(["ruas"], "Ruas e nomes de lugares", "#e9e7e1", false, grupo("Fundo"));
  for (const c of CAMADAS) if (c.no_painel) grupo(c.grupo);  // grupos na ordem do atlas

  for (const c of [...CAMADAS].sort((a, b) => a.ordem - b.ordem)) {
    const layout = { visibility: c.visivel ? "visible" : "none" };
    if (c.tipo === "raster") {
      map.addSource(c.id, { type: "image", url: c.imagem, coordinates: c.cantos });
      map.addLayer({ id: c.id, type: "raster", source: c.id, paint: c.pintura, layout });
    } else {
      map.addSource(c.id, { type: "geojson", data: c.geojson });
      map.addLayer({ id: c.id, type: c.tipo, source: c.id, paint: c.pintura, layout });
      if (c.contorno) map.addLayer({ id: c.id + "-contorno", type: "line", source: c.id, paint: c.contorno, layout });
    }
    if (Object.keys(c.popup).length) {
      map.on("click", c.id, e => {
        const p = e.features[0].properties;
        const linhas = Object.entries(c.popup).map(([k, r]) => `<tr><td>${r}</td><td>${fmt(p[k])}</td></tr>`).join("");
        const titulo = c.titulo_popup ? `<b>${p[c.titulo_popup]}</b>` : "";
        new maplibregl.Popup().setLngLat(e.lngLat)
          .setHTML(`<div class="popup">${titulo}<table>${linhas}</table></div>`).addTo(map);
      });
      map.on("mouseenter", c.id, () => map.getCanvas().style.cursor = "pointer");
      map.on("mouseleave", c.id, () => map.getCanvas().style.cursor = "");
    }
    if (c.no_painel) alternador(c.contorno ? [c.id, c.id + "-contorno"] : [c.id], c.nome, c.cor, c.visivel, grupo(c.grupo));
  }
});
</script>
</body>
</html>
"""

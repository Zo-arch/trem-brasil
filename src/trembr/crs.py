"""Sistemas de referência.

Regra do projeto:
- armazenamento e troca: SIRGAS 2000 geográfico (EPSG:4674), ou o CRS nativo da fonte;
- mapas nacionais: SIRGAS 2000 / Brazil Polyconic (EPSG:5880);
- cálculos de traçado (distâncias, rampas, áreas): SIRGAS 2000 / UTM do fuso do corredor.
"""

from __future__ import annotations

SIRGAS2000 = "EPSG:4674"
BRASIL_POLICONICA = "EPSG:5880"


def fuso_utm(lon: float) -> int:
    return int((lon + 180.0) // 6.0) + 1


def epsg_utm_sirgas(lon: float, lat: float) -> str:
    """EPSG do SIRGAS 2000 / UTM para o ponto. Brasil vai do fuso 18 ao 25."""
    fuso = fuso_utm(lon)
    if not 18 <= fuso <= 25:
        raise ValueError(f"Longitude {lon} está no fuso {fuso}, fora do Brasil (18–25)")
    if lat >= 0:
        if fuso > 22:
            raise ValueError(f"Fuso {fuso}N não tem EPSG SIRGAS 2000 definido")
        return f"EPSG:{31954 + fuso}"  # 18N = 31972 … 22N = 31976
    return f"EPSG:{31960 + fuso}"  # 18S = 31978 … 25S = 31985

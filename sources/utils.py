"""Utilidades compartidas por las fuentes: normalización de precio y deep-link."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlencode


def normalizar_precio(valor) -> Optional[float]:
    """
    Convierte un precio en texto ("$1,234", "US$ 1.234,56", "1 234") a float.

    Maneja separadores de miles/decimales tanto en formato US como europeo.
    Devuelve None si no se puede interpretar.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)

    s = re.sub(r"[^\d.,]", "", str(valor))  # deja solo dígitos, coma y punto
    if not s:
        return None

    tiene_coma = "," in s
    tiene_punto = "." in s

    if tiene_coma and tiene_punto:
        # El separador que aparece más a la derecha es el decimal.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # europeo: 1.234,56
        else:
            s = s.replace(",", "")                     # US: 1,234.56
    elif tiene_coma:
        # Coma sola: decimal si quedan 1-2 dígitos al final, si no, miles.
        if re.search(r",\d{1,2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif tiene_punto:
        # Punto solo. Los precios tienen 0 o 2 decimales: si hay varios puntos
        # (1.234.567) o uno seguido de exactamente 3 dígitos (1.234), es
        # separador de miles. Con 1-2 dígitos al final (12.34) es decimal.
        if s.count(".") > 1 or re.search(r"\.\d{3}$", s):
            s = s.replace(".", "")

    try:
        return float(s)
    except ValueError:
        return None


def google_flights_url(
    origen: str,
    destino: str,
    fecha_salida: str,
    fecha_regreso: str,
) -> str:
    """
    Link de búsqueda a Google Flights para reservar rápido.

    Usa la forma `?q=...` que Google interpreta y prellena la búsqueda
    (origen, destino, fechas de ida y vuelta).
    """
    q = (
        f"Flights from {origen} to {destino} "
        f"on {fecha_salida} returning {fecha_regreso} 1 adult economy round trip"
    )
    return "https://www.google.com/travel/flights?" + urlencode({"q": q})

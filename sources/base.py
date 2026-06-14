"""
Interfaz común de fuentes de precios.

Cada fuente (fast-flights, SerpApi, cache para dry-run) implementa `buscar`
y devuelve un `FlightResult` normalizado, de modo que el resto del sistema
(storage, alertas, main) no sabe ni le importa de dónde salió el precio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FlightResult:
    """Resultado normalizado de una búsqueda round-trip para una ruta+regreso."""

    ruta: str
    origen: str
    destino: str
    fecha_salida: str
    fecha_regreso: str
    precio: Optional[float]          # numérico, ya normalizado (None si no se obtuvo)
    moneda: str
    nivel_precio: Optional[str]      # "low" | "typical" | "high" | None
    source: str                      # nombre de la fuente que lo produjo
    booking_url: str                 # link directo a Google Flights


class FlightSource:
    """Contrato que toda fuente debe cumplir."""

    name: str = "base"

    def disponible(self) -> bool:
        """¿Está configurada/utilizable esta fuente? (p.ej. SerpApi necesita key)."""
        return True

    def buscar(
        self,
        origen: str,
        destino: str,
        fecha_salida: str,
        fecha_regreso: str,
    ) -> FlightResult:
        raise NotImplementedError

"""
Fuente de fallback OPCIONAL: SerpApi (engine=google_flights).

Solo se activa si la variable de entorno SERPAPI_KEY está presente. Implementa
la misma interfaz que la fuente principal, así main.py la usa de forma
transparente si fast-flights falla.

Docs: https://serpapi.com/google-flights-api
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

import config
from .base import FlightResult, FlightSource
from .utils import google_flights_url, normalizar_precio

log = logging.getLogger(__name__)

# Mapeo a los códigos que espera SerpApi.
_TRAVEL_CLASS = {"economy": 1, "premium-economy": 2, "business": 3, "first": 4}


class SerpApiSource(FlightSource):
    name = "serpapi"
    ENDPOINT = "https://serpapi.com/search.json"

    def __init__(self) -> None:
        self.api_key = os.getenv("SERPAPI_KEY")

    def disponible(self) -> bool:
        return bool(self.api_key)

    def buscar(
        self,
        origen: str,
        destino: str,
        fecha_salida: str,
        fecha_regreso: str,
    ) -> FlightResult:
        params = {
            "engine": "google_flights",
            "departure_id": origen,
            "arrival_id": destino,
            "outbound_date": fecha_salida,
            "return_date": fecha_regreso,
            "type": 1,  # 1 = round trip
            "travel_class": _TRAVEL_CLASS.get(config.SEAT, 1),
            "adults": config.ADULTOS,
            "currency": config.MONEDA,
            "hl": "en",
            "api_key": self.api_key,
        }

        log.info("[serpapi] %s-%s ida %s vuelta %s", origen, destino, fecha_salida, fecha_regreso)

        resp = requests.get(self.ENDPOINT, params=params, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("error"):
            raise RuntimeError(f"SerpApi error: {data['error']}")

        precios = []
        for clave in ("best_flights", "other_flights"):
            for itinerario in (data.get(clave) or []):
                p = normalizar_precio(itinerario.get("price"))
                if p is not None:
                    precios.append(p)

        insights = data.get("price_insights") or {}
        lowest = normalizar_precio(insights.get("lowest_price"))
        if lowest is not None:
            precios.append(lowest)

        precio = min(precios) if precios else None
        nivel: Optional[str] = insights.get("price_level")  # "low" | "typical" | "high"

        return FlightResult(
            ruta=config.etiqueta_ruta(origen, destino),
            origen=origen,
            destino=destino,
            fecha_salida=fecha_salida,
            fecha_regreso=fecha_regreso,
            precio=precio,
            moneda=config.MONEDA,
            nivel_precio=nivel,
            source=self.name,
            booking_url=google_flights_url(origen, destino, fecha_salida, fecha_regreso),
        )

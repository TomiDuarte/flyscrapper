"""
Fuente principal: librería `fast-flights` (gratis, sin API key).

Para round-trip pasamos AMBOS tramos como FlightData (ida y regreso) con
trip="round-trip". Leemos result.current_price (low/typical/high) y el precio
más barato de result.flights, normalizado a numérico.

Pineamos fast-flights==2.2: esa versión expone la API clásica
(FlightData / Passengers / get_flights / fetch_mode). La 3.0 (jun-2026)
migró a create_query y rompe esta interfaz.
"""

from __future__ import annotations

import logging
from typing import Optional

import config
from .base import FlightResult, FlightSource
from .utils import google_flights_url, normalizar_precio

log = logging.getLogger(__name__)


class FastFlightsSource(FlightSource):
    name = "fast-flights"

    def buscar(
        self,
        origen: str,
        destino: str,
        fecha_salida: str,
        fecha_regreso: str,
    ) -> FlightResult:
        # Import perezoso: así --dry-run o el fallback a SerpApi no exigen tener
        # fast-flights/Playwright instalados.
        from fast_flights import FlightData, Passengers, get_flights

        flight_data = [
            FlightData(date=fecha_salida, from_airport=origen, to_airport=destino),
            FlightData(date=fecha_regreso, from_airport=destino, to_airport=origen),
        ]

        log.info(
            "[fast-flights] %s-%s ida %s vuelta %s (fetch_mode=%s)",
            origen, destino, fecha_salida, fecha_regreso, config.FETCH_MODE,
        )

        result = get_flights(
            flight_data=flight_data,
            trip=config.TRIP,
            seat=config.SEAT,
            passengers=Passengers(
                adults=config.ADULTOS,
                children=0,
                infants_in_seat=0,
                infants_on_lap=0,
            ),
            fetch_mode=config.FETCH_MODE,
        )

        nivel: Optional[str] = getattr(result, "current_price", None)

        precios = []
        for vuelo in (getattr(result, "flights", None) or []):
            p = normalizar_precio(getattr(vuelo, "price", None))
            if p is not None:
                precios.append(p)

        precio = min(precios) if precios else None

        if precio is None:
            log.warning(
                "[fast-flights] sin precios parseables para %s-%s/%s (nivel=%s)",
                origen, destino, fecha_regreso, nivel,
            )

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

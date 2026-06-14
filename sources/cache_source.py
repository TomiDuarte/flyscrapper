"""
Fuente de cache para --dry-run.

Lee una respuesta cacheada en disco (JSON) para desarrollar sin pegarle a la
red. Si falta la entrada para una ruta/fecha, genera un precio determinístico
(estable entre corridas) para que el pipeline completo se pueda ejercitar.

Formato del JSON (ver data/cache_dryrun.json):
    {
      "ASU-FRA|2027-03-01": {"precio": 1320.0, "nivel_precio": "typical"},
      ...
    }
"""

from __future__ import annotations

import json
import logging
import zlib
from pathlib import Path
from typing import Optional

import config
from .base import FlightResult, FlightSource
from .utils import google_flights_url, normalizar_precio

log = logging.getLogger(__name__)


class CacheSource(FlightSource):
    name = "cache"

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path or config.CACHE_PATH)
        self._data = self._cargar()

    def _cargar(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                log.warning("Cache %s inválido (%s); se usa precio sintético", self.path, exc)
        else:
            log.warning("Cache %s no existe; se usan precios sintéticos", self.path)
        return {}

    @staticmethod
    def _clave(ruta: str, fecha_regreso: str) -> str:
        return f"{ruta}|{fecha_regreso}"

    def _precio_sintetico(self, clave: str) -> float:
        # Determinístico: misma clave -> mismo precio entre corridas.
        base = 1100 + (zlib.crc32(clave.encode()) % 900)  # 1100..1999
        return float(base)

    def buscar(
        self,
        origen: str,
        destino: str,
        fecha_salida: str,
        fecha_regreso: str,
    ) -> FlightResult:
        ruta = config.etiqueta_ruta(origen, destino)
        clave = self._clave(ruta, fecha_regreso)
        entrada = self._data.get(clave, {})

        precio = normalizar_precio(entrada.get("precio"))
        if precio is None:
            precio = self._precio_sintetico(clave)
        nivel = entrada.get("nivel_precio", "typical")

        log.info("[cache] %s/%s -> %.0f %s (%s)", ruta, fecha_regreso, precio, config.MONEDA, nivel)

        return FlightResult(
            ruta=ruta,
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

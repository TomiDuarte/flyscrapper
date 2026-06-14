"""
Tracker de precios de vuelos round-trip.

Hace UNA barrida sobre todas las rutas x fechas de regreso y termina (pensado
para dispararse por cron en GitHub Actions). Por cada combinación:

  1. Busca el precio (fast-flights -> fallback SerpApi, con reintentos+backoff).
  2. Lo persiste en SQLite y recalcula el mínimo histórico.
  3. Alerta si rompió el piso histórico, si es el primer registro, o si Google
     marca el precio como "low" (con dedupe para no repetir la misma oferta).

Flags:
  --dry-run   Usa la cache en disco, no toca la red (desarrollo).
  --reset     Borra el piso histórico para reiniciar el seguimiento.

try/except por ruta: si una falla, se loguea y se sigue; la barrida nunca muere.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from typing import Optional

import config
from alerts.notifier import enviar_alerta
from sources.base import FlightResult, FlightSource
from sources.cache_source import CacheSource
from sources.fast_flights_source import FastFlightsSource
from sources.serpapi_source import SerpApiSource
from storage import db
from storage.db import ResultadoUpsert

log = logging.getLogger("flyscrapper")


# --------------------------------------------------------------------------- #
# Construcción de fuentes
# --------------------------------------------------------------------------- #
def construir_fuentes(dry_run: bool) -> list[FlightSource]:
    if dry_run:
        log.info("Modo --dry-run: usando cache %s (sin red)", config.CACHE_PATH)
        return [CacheSource()]

    fuentes: list[FlightSource] = [FastFlightsSource()]

    serp = SerpApiSource()
    if serp.disponible():
        log.info("SerpApi habilitado como fallback (SERPAPI_KEY presente)")
        fuentes.append(serp)

    return fuentes


# --------------------------------------------------------------------------- #
# Búsqueda con reintentos + backoff + fallback entre fuentes
# --------------------------------------------------------------------------- #
def buscar_con_reintentos(
    fuentes: list[FlightSource],
    origen: str,
    destino: str,
    fecha_salida: str,
    fecha_regreso: str,
) -> Optional[FlightResult]:
    ultimo_error: Optional[Exception] = None

    for fuente in fuentes:
        for intento in range(1, config.MAX_REINTENTOS + 1):
            try:
                res = fuente.buscar(origen, destino, fecha_salida, fecha_regreso)
                if res.precio is not None:
                    return res
                # Respuesta sin precio: no reintentamos esta fuente, probamos la próxima.
                log.warning(
                    "[%s] sin precio para %s-%s/%s; paso a la siguiente fuente",
                    fuente.name, origen, destino, fecha_regreso,
                )
                break
            except Exception as exc:  # noqa: BLE001
                ultimo_error = exc
                if intento < config.MAX_REINTENTOS:
                    espera = config.BACKOFF_BASE * (2 ** (intento - 1)) + random.uniform(0, 1)
                    log.warning(
                        "[%s] intento %d/%d falló (%s); backoff %.1fs",
                        fuente.name, intento, config.MAX_REINTENTOS, exc, espera,
                    )
                    time.sleep(espera)
                else:
                    log.warning(
                        "[%s] agotados los reintentos para %s-%s/%s (%s)",
                        fuente.name, origen, destino, fecha_regreso, exc,
                    )

    if ultimo_error is not None:
        raise ultimo_error
    return None


# --------------------------------------------------------------------------- #
# Mensaje de alerta
# --------------------------------------------------------------------------- #
_ETIQUETAS_MOTIVO = {
    "nuevo": "Primer registro",
    "baja": "Nuevo mínimo histórico",
    "low": "Google lo marca como precio LOW",
}


def construir_mensaje(res: FlightResult, estado: ResultadoUpsert, motivos: list[str]) -> str:
    min_ant = estado.min_anterior
    if min_ant and res.precio is not None and min_ant > 0:
        pct = (min_ant - res.precio) / min_ant * 100
        pct_txt = f"-{pct:.1f}%"
        min_txt = f"{min_ant:.0f} {res.moneda}"
    else:
        pct_txt = "N/A"
        min_txt = "—"

    razon = ", ".join(_ETIQUETAS_MOTIVO.get(m, m) for m in motivos)

    return "\n".join(
        [
            f"✈️ Oferta de vuelo — {razon}",
            f"Ruta: {res.ruta} (ida y vuelta)",
            f"Salida: {res.fecha_salida}  |  Regreso: {res.fecha_regreso}",
            f"Precio: {res.precio:.0f} {res.moneda}",
            f"Mínimo anterior: {min_txt}",
            f"Baja vs. mínimo: {pct_txt}",
            f"Reservar: {res.booking_url}",
        ]
    )


# --------------------------------------------------------------------------- #
# Evaluación de alerta + dedupe
# --------------------------------------------------------------------------- #
def evaluar_y_alertar(conn, res: FlightResult, estado: ResultadoUpsert) -> None:
    motivos: list[str] = []

    if estado.es_nuevo:
        motivos.append("nuevo")           # primer registro -> "no hay registro previo"
    elif estado.es_baja:
        motivos.append("baja")            # rompió el piso histórico

    if config.ALERTAR_SI_LOW and (res.nivel_precio or "").lower() == "low":
        motivos.append("low")

    if not motivos:
        return

    motivo_key = "+".join(motivos)
    if db.ya_alertado(conn, res.ruta, res.fecha_regreso, res.precio, motivo_key):
        log.info(
            "Alerta duplicada omitida (%s/%s @ %.0f, %s)",
            res.ruta, res.fecha_regreso, res.precio, motivo_key,
        )
        return

    texto = construir_mensaje(res, estado, motivos)
    if enviar_alerta(texto):
        db.marcar_alerta(conn, res.ruta, res.fecha_regreso, res.precio, motivo_key)


# --------------------------------------------------------------------------- #
# Barrida principal
# --------------------------------------------------------------------------- #
def correr(dry_run: bool = False, reset: bool = False) -> int:
    conn = db.get_conn(config.DB_PATH)
    db.init_db(conn)

    if reset:
        db.reset_pisos(conn)

    fuentes = construir_fuentes(dry_run)
    rutas = config.generar_rutas()

    total = len(rutas) * len(config.FECHAS_REGRESO)
    ok = 0
    fallos = 0

    log.info("Iniciando barrida: %d combinaciones (%d rutas x %d fechas)",
             total, len(rutas), len(config.FECHAS_REGRESO))

    for origen, destino in rutas:
        for fecha_regreso in config.FECHAS_REGRESO:
            try:
                res = buscar_con_reintentos(
                    fuentes, origen, destino, config.FECHA_SALIDA, fecha_regreso
                )
                if res is None or res.precio is None:
                    fallos += 1
                    log.warning("Sin precio para %s-%s/%s", origen, destino, fecha_regreso)
                    continue

                estado = db.upsert_precio(conn, res)
                log.info(
                    "%s/%s: actual=%.0f %s | min=%.0f | nuevo=%s baja=%s nivel=%s [%s]",
                    res.ruta, fecha_regreso, res.precio, res.moneda,
                    estado.min_nuevo or 0, estado.es_nuevo, estado.es_baja,
                    res.nivel_precio, res.source,
                )
                evaluar_y_alertar(conn, res, estado)
                ok += 1
            except Exception as exc:  # noqa: BLE001 - aislamos cada ruta
                fallos += 1
                log.error(
                    "Fallo no recuperable en %s-%s/%s: %s",
                    origen, destino, fecha_regreso, exc,
                )
            finally:
                # Cortesía entre consultas reales (no aplica en dry-run).
                if not dry_run:
                    time.sleep(config.SLEEP_ENTRE_RUTAS)

    conn.close()
    log.info("Barrida finalizada: %d OK, %d con problemas (de %d)", ok, fallos, total)
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tracker de precios de vuelos round-trip.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Usa la cache en disco; no pega a la red.",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Borra el piso histórico para reiniciar el seguimiento.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return correr(dry_run=args.dry_run, reset=args.reset)


if __name__ == "__main__":
    sys.exit(main())

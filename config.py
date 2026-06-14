"""
Configuración central del tracker de precios de vuelos.

Nada está hardcodeado en el resto del código: todos los parámetros (rutas,
fechas, moneda, reintentos, paths, etc.) viven acá o se sobreescriben por
variables de entorno. Para desarrollo local se puede usar un archivo .env
(ver .env.example); en GitHub Actions los valores llegan por secrets/env.
"""

import os

# Carga opcional de un .env para desarrollo local (no falla si no está dotenv).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv es opcional
    pass


def _env_str(nombre: str, default: str) -> str:
    val = os.getenv(nombre)
    return val if val not in (None, "") else default


def _env_int(nombre: str, default: int) -> int:
    try:
        return int(os.getenv(nombre, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(nombre: str, default: float) -> float:
    try:
        return float(os.getenv(nombre, str(default)))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Rutas (round-trip, misma ciudad europea de entrada y salida)
# --------------------------------------------------------------------------- #
ORIGENES = ["ASU", "EZE", "IGU"]
DESTINOS = ["FRA", "MAD"]


def generar_rutas() -> list[tuple[str, str]]:
    """Producto cartesiano orígenes x destinos -> 6 rutas (origen, destino)."""
    return [(origen, destino) for origen in ORIGENES for destino in DESTINOS]


def etiqueta_ruta(origen: str, destino: str) -> str:
    return f"{origen}-{destino}"


# --------------------------------------------------------------------------- #
# Fechas
# --------------------------------------------------------------------------- #
FECHA_SALIDA = "2026-12-18"  # salida fija para todas las rutas
FECHAS_REGRESO = ["2027-03-01", "2027-03-10"]  # candidatas (configurables)


# --------------------------------------------------------------------------- #
# Parámetros de búsqueda
# --------------------------------------------------------------------------- #
MONEDA = _env_str("MONEDA", "USD")
ADULTOS = _env_int("ADULTOS", 1)
SEAT = _env_str("SEAT", "economy")  # economy | premium-economy | business | first
TRIP = "round-trip"

# fast-flights fetch_mode: common | fallback | force-fallback | local
# "local" usa Playwright propio (lo más robusto en CI/headless). En entorno
# local sin navegadores instalados, usá "fallback".
FETCH_MODE = _env_str("FETCH_MODE", "fallback")


# --------------------------------------------------------------------------- #
# Red: reintentos, backoff y cortesía entre rutas
# --------------------------------------------------------------------------- #
MAX_REINTENTOS = _env_int("MAX_REINTENTOS", 3)
BACKOFF_BASE = _env_float("BACKOFF_BASE", 3.0)  # segundos, crece exponencial
SLEEP_ENTRE_RUTAS = _env_float("SLEEP_ENTRE_RUTAS", 6.0)
HTTP_TIMEOUT = _env_int("HTTP_TIMEOUT", 60)


# --------------------------------------------------------------------------- #
# Almacenamiento
# --------------------------------------------------------------------------- #
DB_PATH = _env_str("DB_PATH", "data/precios.db")
CACHE_PATH = _env_str("CACHE_PATH", "data/cache_dryrun.json")


# --------------------------------------------------------------------------- #
# Lógica de alerta
# --------------------------------------------------------------------------- #
# Si Google marca el precio actual como "low" también alertamos, aunque no
# rompa el piso histórico.
ALERTAR_SI_LOW = _env_str("ALERTAR_SI_LOW", "1") not in ("0", "false", "False")


# --------------------------------------------------------------------------- #
# Alertas (backend de notificación)
# --------------------------------------------------------------------------- #
# "callmebot" (WhatsApp) por defecto; "telegram" disponible para cambiar fácil.
ALERT_BACKEND = _env_str("ALERT_BACKEND", "callmebot").lower()


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOG_LEVEL = _env_str("LOG_LEVEL", "INFO").upper()

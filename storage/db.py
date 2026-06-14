"""
Persistencia en SQLite.

Tabla `precios`: una fila por combinación (ruta, fecha_regreso) que mantiene el
precio actual y el mínimo histórico. Se crea sola en la primera corrida con
CREATE TABLE IF NOT EXISTS. Tabla `alertas_enviadas`: dedupe simple para no
repetir la misma oferta.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sources.base import FlightResult

log = logging.getLogger(__name__)


@dataclass
class ResultadoUpsert:
    es_nuevo: bool                 # no había registro previo para ruta+regreso
    es_baja: bool                  # el precio actual rompió el mínimo histórico
    min_anterior: Optional[float]  # mínimo antes de esta corrida
    min_nuevo: Optional[float]     # mínimo después de esta corrida


# --------------------------------------------------------------------------- #
# Conexión / esquema
# --------------------------------------------------------------------------- #
def get_conn(db_path: str) -> sqlite3.Connection:
    carpeta = os.path.dirname(db_path)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS precios (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            ruta                      TEXT    NOT NULL,
            fecha_salida              TEXT    NOT NULL,
            fecha_regreso             TEXT    NOT NULL,
            fecha_busqueda            TEXT    NOT NULL,
            precio_actual             REAL,
            precio_historico_mas_bajo REAL,
            moneda                    TEXT    NOT NULL,
            UNIQUE (ruta, fecha_regreso)
        );

        CREATE INDEX IF NOT EXISTS idx_precios_ruta_regreso
            ON precios (ruta, fecha_regreso);

        CREATE TABLE IF NOT EXISTS alertas_enviadas (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ruta          TEXT,
            fecha_regreso TEXT,
            precio        REAL,
            motivo        TEXT,
            enviada_en    TEXT,
            UNIQUE (ruta, fecha_regreso, precio, motivo)
        );
        """
    )
    conn.commit()


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Registro de precios + cálculo de mínimo histórico
# --------------------------------------------------------------------------- #
def upsert_precio(conn: sqlite3.Connection, res: FlightResult) -> ResultadoUpsert:
    """
    Inserta/actualiza la fila de (ruta, fecha_regreso) y recalcula el mínimo
    histórico. Devuelve un ResultadoUpsert con el contexto para decidir alertas.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT precio_historico_mas_bajo FROM precios WHERE ruta = ? AND fecha_regreso = ?",
        (res.ruta, res.fecha_regreso),
    )
    fila = cur.fetchone()

    es_nuevo = fila is None
    min_anterior = fila["precio_historico_mas_bajo"] if (fila and fila[0] is not None) else None

    # Nuevo mínimo histórico.
    if res.precio is None:
        min_nuevo = min_anterior
    elif min_anterior is None:
        min_nuevo = res.precio
    else:
        min_nuevo = min(min_anterior, res.precio)

    es_baja = (
        res.precio is not None
        and (min_anterior is None or res.precio < min_anterior)
    )

    ahora = _ahora_iso()
    if es_nuevo:
        cur.execute(
            """
            INSERT INTO precios
                (ruta, fecha_salida, fecha_regreso, fecha_busqueda,
                 precio_actual, precio_historico_mas_bajo, moneda)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                res.ruta, res.fecha_salida, res.fecha_regreso, ahora,
                res.precio, min_nuevo, res.moneda,
            ),
        )
    else:
        cur.execute(
            """
            UPDATE precios
               SET fecha_salida = ?,
                   fecha_busqueda = ?,
                   precio_actual = ?,
                   precio_historico_mas_bajo = ?,
                   moneda = ?
             WHERE ruta = ? AND fecha_regreso = ?
            """,
            (
                res.fecha_salida, ahora, res.precio, min_nuevo, res.moneda,
                res.ruta, res.fecha_regreso,
            ),
        )
    conn.commit()

    return ResultadoUpsert(
        es_nuevo=es_nuevo,
        es_baja=es_baja,
        min_anterior=min_anterior,
        min_nuevo=min_nuevo,
    )


# --------------------------------------------------------------------------- #
# Dedupe de alertas
# --------------------------------------------------------------------------- #
def ya_alertado(
    conn: sqlite3.Connection,
    ruta: str,
    fecha_regreso: str,
    precio: float,
    motivo: str,
) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM alertas_enviadas
         WHERE ruta = ? AND fecha_regreso = ? AND precio = ? AND motivo = ?
        """,
        (ruta, fecha_regreso, precio, motivo),
    )
    return cur.fetchone() is not None


def marcar_alerta(
    conn: sqlite3.Connection,
    ruta: str,
    fecha_regreso: str,
    precio: float,
    motivo: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO alertas_enviadas
            (ruta, fecha_regreso, precio, motivo, enviada_en)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ruta, fecha_regreso, precio, motivo, _ahora_iso()),
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Reset del piso histórico
# --------------------------------------------------------------------------- #
def reset_pisos(conn: sqlite3.Connection) -> None:
    """Borra el seguimiento para reiniciar de cero (pisos + dedupe de alertas)."""
    conn.executescript(
        """
        DELETE FROM precios;
        DELETE FROM alertas_enviadas;
        """
    )
    conn.commit()
    log.info("Pisos históricos y dedupe de alertas reseteados.")

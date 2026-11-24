"""Persistencia en SQLite para evitar duplicados al re-ejecutar."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .extractor import RegistroCorreo


def conectar(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registros (
            message_id TEXT PRIMARY KEY,
            fecha TEXT NOT NULL,
            remitente TEXT NOT NULL,
            asunto TEXT NOT NULL,
            numero_documento TEXT NOT NULL,
            nit_fiscal TEXT NOT NULL,
            monto REAL,
            moneda TEXT NOT NULL,
            adjuntos_pdf TEXT NOT NULL,
            resumen TEXT NOT NULL,
            procesado_en REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def ya_procesado(conn: sqlite3.Connection, message_id: str) -> bool:
    if not message_id:
        return False
    return conn.execute("SELECT 1 FROM registros WHERE message_id = ?", (message_id,)).fetchone() is not None


def guardar_si_nuevo(conn: sqlite3.Connection, reg: RegistroCorreo) -> bool:
    """Inserta el registro; devuelve True si es nuevo o False si ya existía."""
    if not reg.message_id:
        return False
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO registros
        (message_id, fecha, remitente, asunto, numero_documento, nit_fiscal, monto, moneda, adjuntos_pdf, resumen, procesado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reg.message_id,
            reg.fecha,
            reg.remitente,
            reg.asunto,
            reg.numero_documento,
            reg.nit_fiscal,
            reg.monto,
            reg.moneda,
            reg.adjuntos_pdf,
            reg.resumen,
            time.time(),
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def listar_todos(conn: sqlite3.Connection) -> list[dict]:
    filas = conn.execute(
        """
        SELECT fecha, remitente, asunto, numero_documento, nit_fiscal, monto, moneda, adjuntos_pdf, resumen, message_id
        FROM registros
        ORDER BY fecha DESC, procesado_en DESC
        """
    ).fetchall()
    return [dict(f) for f in filas]

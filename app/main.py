"""CLI principal: lee correos de archivos .eml locales o IMAP y los exporta a Excel/CSV."""
from __future__ import annotations

import argparse
import hashlib
import imaplib
import os
from pathlib import Path

from dotenv import load_dotenv

from . import exporter, extractor, storage


def procesar_eml_dir(carpeta: str | Path, db_path: str | Path, out_prefix: str | Path) -> tuple[int, Path, Path]:
    carpeta_p = Path(carpeta)
    if not carpeta_p.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de correos: {carpeta_p}")
    with storage.conectar(db_path) as conn:
        nuevos = 0
        for archivo in sorted(carpeta_p.glob("*.eml")):
            crudo = archivo.read_bytes()
            fallback = f"eml:{hashlib.sha1(crudo).hexdigest()[:16]}"
            reg = extractor.parsear_mensaje(crudo, fallback_id=fallback)
            if storage.guardar_si_nuevo(conn, reg):
                nuevos += 1
        todos = storage.listar_todos(conn)
    xlsx_path, csv_path = exporter.exportar(todos, out_prefix)
    return nuevos, xlsx_path, csv_path


def procesar_imap(db_path: str | Path, out_prefix: str | Path, limit: int = 50) -> tuple[int, Path, Path]:
    if limit < 1:
        raise ValueError("--limit debe ser mayor que cero")
    host = os.environ.get("IMAP_HOST", "").strip()
    user = os.environ.get("IMAP_USER", "").strip()
    password = os.environ.get("IMAP_PASS", "").strip()
    port = int(os.environ.get("IMAP_PORT", "993"))
    folder = os.environ.get("IMAP_FOLDER", "INBOX")
    unseen_only = os.environ.get("IMAP_UNSEEN_ONLY", "1") == "1"

    if not (host and user and password):
        raise RuntimeError("Faltan IMAP_HOST, IMAP_USER o IMAP_PASS en .env")

    with storage.conectar(db_path) as conn:
        nuevos = 0
        imap = imaplib.IMAP4_SSL(host, port)
        try:
            imap.login(user, password)
            status, _ = imap.select(folder, readonly=True)
            if status != "OK":
                raise RuntimeError(f"No se pudo abrir la carpeta IMAP: {folder}")
            criterio = "UNSEEN" if unseen_only else "ALL"
            status, datos = imap.search(None, criterio)
            if status != "OK":
                raise RuntimeError(f"Falló la búsqueda IMAP: {criterio}")
            uids = (datos[0] or b"").split()[-limit:]
            for uid in uids:
                status, fetched = imap.fetch(uid, "(BODY.PEEK[])")
                if status != "OK":
                    raise RuntimeError(f"Falló la lectura del correo IMAP {uid!r}")
                if not fetched or not fetched[0]:
                    continue
                crudo = fetched[0][1]
                fallback = f"imap:{uid.decode()}:{hashlib.sha1(crudo).hexdigest()[:12]}"
                reg = extractor.parsear_mensaje(crudo, fallback_id=fallback)
                if storage.guardar_si_nuevo(conn, reg):
                    nuevos += 1
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        todos = storage.listar_todos(conn)
    xlsx_path, csv_path = exporter.exportar(todos, out_prefix)
    return nuevos, xlsx_path, csv_path


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Exporta correos y facturas PDF a Excel/CSV")
    ap.add_argument("--eml-dir", help="Carpeta con archivos .eml locales (modo demo/offline)")
    ap.add_argument("--imap", action="store_true", help="Leer correos desde servidor IMAP (.env)")
    ap.add_argument("--limit", type=int, default=50, help="Máximo de correos a consultar en IMAP")
    ap.add_argument("--db", default=os.environ.get("DB_PATH", "correos_excel.db"))
    ap.add_argument("--out", default=os.environ.get("OUT_PREFIX", "salida/facturas"))
    args = ap.parse_args()

    if args.eml_dir:
        nuevos, xlsx, csv = procesar_eml_dir(args.eml_dir, args.db, args.out)
    elif args.imap:
        nuevos, xlsx, csv = procesar_imap(args.db, args.out, limit=args.limit)
    else:
        ap.error("Especifica --eml-dir <carpeta> o --imap")
        return

    print(f"Nuevos procesados: {nuevos} -> {xlsx} / {csv}")


if __name__ == "__main__":
    main()

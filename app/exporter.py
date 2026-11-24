"""Exportador seguro a Excel (.xlsx) y CSV (.csv)."""
from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

COLUMNAS = [
    ("fecha", "Fecha"),
    ("remitente", "Remitente"),
    ("asunto", "Asunto"),
    ("numero_documento", "N° Documento"),
    ("nit_fiscal", "NIT / ID Fiscal"),
    ("monto", "Monto"),
    ("moneda", "Moneda"),
    ("adjuntos_pdf", "Adjuntos PDF"),
    ("resumen", "Resumen"),
    ("message_id", "Message-ID"),
]


def sanitizar_celda(valor: object) -> object:
    """Evita inyección de fórmulas en Excel cuando una cadena empieza por =, +, - o @."""
    if isinstance(valor, str) and valor and valor[0] in ("=", "+", "-", "@"):
        return "'" + valor
    return valor


def exportar(registros: list[dict], out_prefix: str | Path) -> tuple[Path, Path]:
    prefix = Path(out_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    xlsx_path = prefix.with_suffix(".xlsx")
    csv_path = prefix.with_suffix(".csv")

    wb = Workbook()
    ws = wb.active
    ws.title = "Correos"
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    ws.append([titulo for _, titulo in COLUMNAS])
    for col_idx in range(1, len(COLUMNAS) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font

    for reg in registros:
        fila = [sanitizar_celda(reg.get(clave, "")) for clave, _ in COLUMNAS]
        ws.append(fila)

    for col in ws.columns:
        letra = col[0].column_letter
        largo = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[letra].width = min(max(largo + 3, 12), 48)

    ws.auto_filter.ref = f"A1:{chr(64 + len(COLUMNAS))}{max(1, len(registros) + 1)}"
    wb.save(xlsx_path)

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([titulo for _, titulo in COLUMNAS])
        for reg in registros:
            writer.writerow([sanitizar_celda(reg.get(clave, "")) for clave, _ in COLUMNAS])

    return xlsx_path, csv_path

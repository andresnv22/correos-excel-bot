"""Pruebas completas de extracción, PDF, deduplicación y exportación a Excel/CSV."""
import csv
from email.message import EmailMessage

import pytest

from openpyxl import load_workbook

from app import exporter, extractor, main


def _crear_pdf_minimo(texto: str) -> bytes:
    """Genera un PDF válido mínimo con texto legible para pypdf."""
    escapado = texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 50 750 Td ({escapado}) Tj ET".encode("latin-1")
    objetos = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream)} >> stream\n".encode() + stream + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for obj in objetos:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer << /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode())
    return bytes(out)


def _crear_eml_con_pdf(msg_id: str, asunto: str, cuerpo: str, pdf_texto: str) -> bytes:
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["Subject"] = asunto
    msg["From"] = "facturacion@proveedor.com"
    msg["Date"] = "Tue, 24 Nov 2026 10:15:00 -0500"
    msg.set_content(cuerpo)
    msg.add_attachment(_crear_pdf_minimo(pdf_texto), maintype="application", subtype="pdf", filename="factura_1045.pdf")
    return msg.as_bytes()


def test_parseo_eml_y_pdf():
    crudo = _crear_eml_con_pdf(
        "<fac-1@test>",
        "Factura #FAC-1045",
        "Adjuntamos comprobante de servicio.",
        "Factura No. FAC-1045 NIT: 900123456-7 Total USD 1,250.50",
    )
    reg = extractor.parsear_mensaje(crudo)
    assert reg.numero_documento == "FAC-1045"
    assert reg.nit_fiscal == "900123456-7"
    assert reg.monto == 1250.50
    assert reg.moneda == "USD"
    assert reg.adjuntos_pdf == "factura_1045.pdf"


def test_sanitizacion_formulas_excel():
    assert exporter.sanitizar_celda("=CMD()") == "'=CMD()"
    assert exporter.sanitizar_celda("+123") == "'+123"
    assert exporter.sanitizar_celda("@SUM") == "'@SUM"
    assert exporter.sanitizar_celda("Normal") == "Normal"


def test_deduplicacion_y_exportacion_xlsx_csv(tmp_path):
    eml_dir = tmp_path / "correos"
    eml_dir.mkdir()
    eml_bytes = _crear_eml_con_pdf(
        "<fac-99@test>",
        "=Alerta Factura #ORD-99",
        "Pago recibido COP 450.000",
        "Orden ORD-99 Total COP 450.000",
    )
    (eml_dir / "uno.eml").write_bytes(eml_bytes)
    (eml_dir / "copia.eml").write_bytes(eml_bytes)

    db_path = tmp_path / "test.db"
    out_prefix = tmp_path / "out" / "reporte"

    nuevos1, xlsx, csv_p = main.procesar_eml_dir(eml_dir, db_path, out_prefix)
    nuevos2, _, _ = main.procesar_eml_dir(eml_dir, db_path, out_prefix)

    assert nuevos1 == 1
    assert nuevos2 == 0
    assert xlsx.exists() and csv_p.exists()

    wb = load_workbook(xlsx)
    ws = wb.active
    assert ws.max_row == 2
    assert ws.cell(row=2, column=3).value == "'=Alerta Factura #ORD-99"
    assert ws.cell(row=2, column=6).value == 450000.0

    with csv_p.open(encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2


def test_carpeta_inexistente_no_genera_reporte_vacio(tmp_path):
    with pytest.raises(FileNotFoundError, match="No existe la carpeta"):
        main.procesar_eml_dir(tmp_path / "faltante", tmp_path / "test.db", tmp_path / "out")
    assert not (tmp_path / "out.xlsx").exists()


def test_limite_imap_invalido_falla_antes_de_conectar(tmp_path):
    with pytest.raises(ValueError, match="--limit"):
        main.procesar_imap(tmp_path / "test.db", tmp_path / "out", limit=0)

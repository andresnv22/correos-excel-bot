"""Extracción limpia de datos de correos (.eml / IMAP) y adjuntos PDF."""
from __future__ import annotations

import email
import html
import io
import re
from dataclasses import dataclass, asdict
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime

from pypdf import PdfReader

RE_MONTO = re.compile(
    r"(?:USD|US\$|COP|EUR|MXN|\$)\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?|[0-9]+(?:[.,][0-9]{1,2})?)",
    re.I,
)
RE_MONEDA = re.compile(r"\b(USD|COP|EUR|MXN)\b", re.I)
RE_FACTURA = re.compile(
    r"(?:factura|invoice|orden|order|recibo|comprobante)\s*(?:no\.?|n[°ºo]\.?|#|:)?\s*([A-Z0-9][A-Z0-9\-]{2,24})",
    re.I,
)
RE_NIT = re.compile(r"(?:NIT|RFC|RUC|ID\s*Fiscal)\s*[:#]?\s*([0-9A-Z\-]{6,18})", re.I)


@dataclass
class RegistroCorreo:
    message_id: str
    fecha: str
    remitente: str
    asunto: str
    numero_documento: str
    nit_fiscal: str
    monto: float | None
    moneda: str
    adjuntos_pdf: str
    resumen: str

    def to_dict(self) -> dict:
        return asdict(self)


def decodificar_cabecera(valor: str | None) -> str:
    if not valor:
        return ""
    partes = []
    for texto, enc in decode_header(valor):
        if isinstance(texto, bytes):
            partes.append(texto.decode(enc or "utf-8", errors="replace"))
        else:
            partes.append(str(texto))
    return "".join(partes).strip()


def _limpiar_html(crudo: str) -> str:
    sin_style = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", crudo, flags=re.S | re.I)
    sin_tags = re.sub(r"<[^>]+>", " ", sin_style)
    return re.sub(r"\s+", " ", html.unescape(sin_tags)).strip()


def extraer_texto_pdf(datos: bytes) -> str:
    if not datos:
        return ""
    try:
        reader = PdfReader(io.BytesIO(datos))
        paginas = [(page.extract_text() or "") for page in reader.pages[:10]]
        return "\n".join(paginas).strip()
    except Exception:
        return ""


def _parsear_monto(raw: str) -> float | None:
    if not raw:
        return None
    s = raw.strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parte_final = s.split(",")[-1]
        if len(parte_final) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s and len(s.split(".")[-1]) == 3 and s.count(".") >= 1:
        s = s.replace(".", "")
    try:
        val = float(s)
        return val if val >= 0 else None
    except ValueError:
        return None


def _fecha_iso(fecha_raw: str | None) -> str:
    if not fecha_raw:
        return ""
    try:
        return parsedate_to_datetime(fecha_raw).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return fecha_raw.strip()[:32]


def parsear_mensaje(crudo: bytes, fallback_id: str = "") -> RegistroCorreo:
    msg: Message = email.message_from_bytes(crudo)
    message_id = (msg.get("Message-ID") or fallback_id or "").strip()
    asunto = decodificar_cabecera(msg.get("Subject"))
    remitente = decodificar_cabecera(msg.get("From"))
    fecha = _fecha_iso(msg.get("Date"))

    texto_plano: list[str] = []
    texto_html: list[str] = []
    pdfs_nombres: list[str] = []
    pdfs_texto: list[str] = []

    partes = list(msg.walk()) if msg.is_multipart() else [msg]
    for parte in partes:
        ct = (parte.get_content_type() or "").lower()
        nombre = decodificar_cabecera(parte.get_filename())
        payload = parte.get_payload(decode=True)
        if not payload:
            continue
        if ct == "application/pdf" or nombre.lower().endswith(".pdf"):
            pdfs_nombres.append(nombre or "adjunto.pdf")
            t_pdf = extraer_texto_pdf(payload)
            if t_pdf:
                pdfs_texto.append(t_pdf)
        elif ct == "text/plain" and "attachment" not in (parte.get("Content-Disposition") or "").lower():
            cs = parte.get_content_charset() or "utf-8"
            texto_plano.append(payload.decode(cs, errors="replace"))
        elif ct == "text/html" and "attachment" not in (parte.get("Content-Disposition") or "").lower():
            cs = parte.get_content_charset() or "utf-8"
            texto_html.append(_limpiar_html(payload.decode(cs, errors="replace")))

    cuerpo = "\n".join(texto_plano).strip() or "\n".join(texto_html).strip()
    texto_total = "\n".join(p for p in (asunto, cuerpo, "\n".join(pdfs_texto)) if p)

    doc_match = RE_FACTURA.search(texto_total)
    nit_match = RE_NIT.search(texto_total)
    montos = [_parsear_monto(m.group(1)) for m in RE_MONTO.finditer(texto_total)]
    montos_validos = [m for m in montos if m is not None]
    monto = max(montos_validos) if montos_validos else None

    moneda_match = RE_MONEDA.search(texto_total)
    moneda = moneda_match.group(1).upper() if moneda_match else ("USD" if "$" in texto_total else "")

    resumen = re.sub(r"\s+", " ", cuerpo or "\n".join(pdfs_texto)).strip()[:240]

    return RegistroCorreo(
        message_id=message_id,
        fecha=fecha,
        remitente=remitente,
        asunto=asunto,
        numero_documento=doc_match.group(1) if doc_match else "",
        nit_fiscal=nit_match.group(1) if nit_match else "",
        monto=monto,
        moneda=moneda,
        adjuntos_pdf=", ".join(pdfs_nombres),
        resumen=resumen,
    )

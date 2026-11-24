# Bot de Correos & PDFs → Excel / CSV

Automatización en Python que lee correos (desde archivos `.eml` locales o vía IMAP en modo solo lectura), extrae texto de facturas adjuntas en PDF, detecta número de documento, NIT/ID fiscal y monto, evita duplicados en SQLite y genera archivos `.xlsx` y `.csv` listos para contabilidad.

## Uso rápido
```bash
uv sync
uv run pytest -v
uv run python -m app.main --eml-dir muestras --out salida/facturas
```

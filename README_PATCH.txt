Patch comercial (Opción D) - Locutorio Facturación

Archivos incluidos:
- app.py: UI con tabs Venta / Comprobantes día / Comprobantes rango, F4 facturar, doble-click reimprimir, export Excel.
- db.py: agrega app_settings, ticket_templates y license + helpers (ensure_defaults, validate_license, etc.).
- ticket_format.py: arma ticket desde templates en DB (todo string personalizable).
- printer.py: modo escpos/gdi (PDF) con escalado decente en GDI (ImageWin.Dib).
- qr_afip.py: QR ARCA con base64 URL-safe y URL-encode (incluye CAE).
- qr_debug.py: log a qr.log

Uso:
1) Copiá estos archivos encima de tu proyecto.
2) Ejecutá la app una vez. Se crean tablas nuevas y se cargan defaults desde settings.json.
3) Para imprimir en casa: en DB setting print.mode = 'gdi' y print.printer_name_contains que matchee tu impresora (ej 'Microsoft Print to PDF').
   (por ahora se setea editando DB con SQLite; luego hacemos pantalla de Config.)

Licencia (opción D):
- Tabla license (id=1): enabled=1, owner, valid_until (YYYY-MM-DD), license_key.
- Primer run: fija fingerprint al equipo si estaba vacío.
- license_key esperada se calcula desde fingerprint+owner+valid_until.

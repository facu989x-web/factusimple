# Instalador/bundle kiosco (fuera de `app.py`)

Este flujo empaqueta la app para usuarios no técnicos, incluyendo OpenSSL embebido.

## 1) Construir bundle

```bash
python installer/build_bundle.py \
  --repo-root . \
  --out-dir dist/factusimple_bundle \
  --openssl-dir "C:\\Program Files (x86)\\OpenSSL-Win32\\bin"
```

Salida:
- `dist/factusimple_bundle/` con archivos de app.
- `dist/factusimple_bundle/runtime/openssl/` con `openssl.exe` + DLLs.
- `bundle_manifest.json` para auditoría.

## 2) Post-instalación (seteo automático)

```bash
python installer/post_install_config.py \
  --install-dir "C:\\Program Files (x86)\\FacturaSimple" \
  --db-path "data/locutorio.sqlite" \
  --print-mode gdi
```

Esto configura en DB:
- `openssl_path`
- `printer_name_contains`
- `print_mode`

## 3) Inno Setup

Usar `installer/factusimple.iss` como plantilla.

> Nota: ajustar `app.exe`/runtime Python según cómo empaquetes el ejecutable principal (PyInstaller/cx_Freeze, etc).

## 4) QA mínimo antes de distribución

1. Abrir app en una máquina limpia.
2. Verificar que no pida instalar OpenSSL externo.
3. Cargar `.crt` + `.key`.
4. Ejecutar prueba WSAA/WSFE.
5. Probar impresión en modo GDI (PDF) y/o ESCPOS.

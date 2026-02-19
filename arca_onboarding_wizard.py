from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class OpenSSLResult:
    ok: bool
    output: str


def run_cmd(cmd: list[str]) -> OpenSSLResult:
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return OpenSSLResult(ok=(p.returncode == 0), output=out.strip())


def build_subject(*, cuit: str, razon_social: str, cn: str) -> str:
    return f"/C=AR/O={razon_social}/CN={cn}/serialNumber=CUIT {cuit}"


def normalize_name(s: str) -> str:
    return " ".join((s or "").strip().split())


def generate_key_and_csr(*, openssl: str, out_dir: Path, key_name: str, csr_name: str, subject: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    key_path = out_dir / key_name
    csr_path = out_dir / csr_name

    key_cmd = [openssl, "genrsa", "-out", str(key_path), "2048"]
    key_res = run_cmd(key_cmd)
    if not key_res.ok:
        raise RuntimeError(f"Error generando key:\n{key_res.output}")

    csr_cmd = [openssl, "req", "-new", "-key", str(key_path), "-subj", subject, "-out", str(csr_path)]
    csr_res = run_cmd(csr_cmd)
    if not csr_res.ok:
        raise RuntimeError(f"Error generando CSR:\n{csr_res.output}")

    return {"key_path": str(key_path), "csr_path": str(csr_path)}


def _extract_modulus_hash(*, openssl: str, typ: str, path: Path) -> str:
    if typ == "crt":
        cmd = [openssl, "x509", "-in", str(path), "-noout", "-modulus"]
    elif typ == "key":
        cmd = [openssl, "rsa", "-in", str(path), "-noout", "-modulus"]
    else:
        raise ValueError("typ inválido")

    res = run_cmd(cmd)
    if not res.ok:
        raise RuntimeError(res.output)

    line = res.output.strip().splitlines()[-1]
    if "=" in line:
        line = line.split("=", 1)[1]
    return hashlib.md5(line.encode("utf-8")).hexdigest()


def verify_cert_key_pair(*, openssl: str, crt_path: Path, key_path: Path) -> bool:
    crt = _extract_modulus_hash(openssl=openssl, typ="crt", path=crt_path)
    key = _extract_modulus_hash(openssl=openssl, typ="key", path=key_path)
    return crt == key


def write_manual_checklist(*, out_path: Path, cuit: str, pv: str, cn: str, cert_path: str, key_path: str) -> None:
    txt = f"""# Checklist onboarding ARCA/WSFE

Generado: {datetime.now().isoformat(timespec='seconds')}

## 1) Certificado
- [ ] Generar key + CSR con este CN: `{cn}`
- [ ] Subir CSR al Administrador de Certificados Digitales (ARCA)
- [ ] Descargar CRT emitido
- [ ] Verificar que CRT y KEY sean pareja
  - `openssl x509 -in {cert_path} -noout -modulus | openssl md5`
  - `openssl rsa  -in {key_path} -noout -modulus | openssl md5`

## 2) Relación en Clave Fiscal (Nivel >= 3)
- [ ] Autorizante/Representado: CUIT {cuit}
- [ ] Servicio: Facturación Electrónica (Web Services)
- [ ] Representante: Computador Fiscal (ej.: `{cn}`)
- [ ] Confirmar relación activa

## 3) Punto de venta
- [ ] Alta de PV para Factura Electrónica Web Services
- [ ] PV en app = `{pv}`

## 4) Configuración app
- [ ] modo = PROD
- [ ] cuit_emisor = {cuit}
- [ ] punto_venta = {pv}
- [ ] cert_crt_path = {cert_path}
- [ ] private_key_path = {key_path}
- [ ] taxpayer_type = MONO o RI según corresponda

## 5) Prueba de login WSAA
- [ ] Ejecutar `python wsaatest.py` (o flujo de emisión mínimo)
- [ ] Si falla "computador no autorizado": revisar relación activa + propagación ARCA
"""
    out_path.write_text(txt, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Asistente de onboarding ARCA/WSFE (certificado + checklist)")
    ap.add_argument("--openssl", default="openssl")
    ap.add_argument("--cuit", required=True)
    ap.add_argument("--razon-social", required=True)
    ap.add_argument("--cn", default="FACTURASIMPLE")
    ap.add_argument("--pv", default="4")
    ap.add_argument("--out-dir", default="certs")
    ap.add_argument("--key-name", default="clave.key")
    ap.add_argument("--csr-name", default="certificado.csr")
    ap.add_argument("--check-crt", default="")
    ap.add_argument("--write-checklist", default="onboarding_arca_checklist.md")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    rs = normalize_name(args.razon_social)
    subject = build_subject(cuit=args.cuit, razon_social=rs, cn=args.cn)

    generated = generate_key_and_csr(
        openssl=args.openssl,
        out_dir=out_dir,
        key_name=args.key_name,
        csr_name=args.csr_name,
        subject=subject,
    )

    key_path = Path(generated["key_path"])
    csr_path = Path(generated["csr_path"])

    pair_ok: bool | None = None
    if args.check_crt:
        pair_ok = verify_cert_key_pair(openssl=args.openssl, crt_path=Path(args.check_crt), key_path=key_path)

    checklist = Path(args.write_checklist)
    write_manual_checklist(
        out_path=checklist,
        cuit=args.cuit,
        pv=args.pv,
        cn=args.cn,
        cert_path=(args.check_crt or "<completar_ruta_crt>"),
        key_path=str(key_path),
    )

    data = {
        "subject": subject,
        "generated": generated,
        "check_cert_key_pair": pair_ok,
        "checklist": str(checklist),
    }
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("[OK] Key:", generated["key_path"])
        print("[OK] CSR:", generated["csr_path"])
        if pair_ok is not None:
            print("[OK] CRT/KEY match:", "SI" if pair_ok else "NO")
        print("[OK] Checklist:", checklist)
        print("Subject:", subject)


if __name__ == "__main__":
    main()

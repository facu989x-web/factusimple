from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

APP_FILES = [
    "app.py",
    "afip_service.py",
    "db.py",
    "ticket_format.py",
    "qr_afip.py",
    "qr_render.py",
    "qr_debug.py",
    "printer.py",
    "arca_onboarding_wizard.py",
    "requirements.txt",
    "settings.json",
]

RUNTIME_OPENSSL_TARGET = Path("runtime/openssl")


def copy_app_files(*, repo_root: Path, out_dir: Path) -> list[str]:
    copied: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel in APP_FILES:
        src = repo_root / rel
        if not src.exists():
            raise FileNotFoundError(f"Falta archivo requerido: {src}")
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    return copied


def copy_openssl_runtime(*, openssl_dir: Path, out_dir: Path) -> list[str]:
    if not openssl_dir.exists():
        raise FileNotFoundError(f"No existe runtime OpenSSL: {openssl_dir}")

    required = ["openssl.exe"]
    for req in required:
        if not (openssl_dir / req).exists():
            raise FileNotFoundError(f"No se encontró {req} en {openssl_dir}")

    target = out_dir / RUNTIME_OPENSSL_TARGET
    target.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for p in openssl_dir.iterdir():
        if p.is_file() and p.suffix.lower() in (".exe", ".dll", ".cnf"):
            dst = target / p.name
            shutil.copy2(p, dst)
            copied.append(str((RUNTIME_OPENSSL_TARGET / p.name).as_posix()))
    return copied


def write_manifest(*, out_dir: Path, files: list[str], openssl_files: list[str]) -> Path:
    manifest = {
        "files": sorted(files),
        "openssl_runtime_files": sorted(openssl_files),
    }
    path = out_dir / "bundle_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Construye bundle deployable para kioscos")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--out-dir", default="dist/factusimple_bundle")
    ap.add_argument("--openssl-dir", default="", help="Carpeta con openssl.exe + dlls")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out_dir).resolve()

    if out_dir.exists():
        shutil.rmtree(out_dir)

    files = copy_app_files(repo_root=repo_root, out_dir=out_dir)

    openssl_files: list[str] = []
    if args.openssl_dir:
        openssl_files = copy_openssl_runtime(openssl_dir=Path(args.openssl_dir).resolve(), out_dir=out_dir)

    manifest = write_manifest(out_dir=out_dir, files=files, openssl_files=openssl_files)

    print("[OK] Bundle creado:", out_dir)
    print("[OK] Manifest:", manifest)
    if openssl_files:
        print("[OK] Runtime OpenSSL copiado:", len(openssl_files), "archivos")
    else:
        print("[WARN] Bundle sin runtime OpenSSL embebido (--openssl-dir no informado)")


if __name__ == "__main__":
    main()

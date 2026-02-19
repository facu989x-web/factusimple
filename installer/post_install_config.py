from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, set_setting


def main() -> None:
    ap = argparse.ArgumentParser(description="Post-instalación: setea rutas y defaults kiosco")
    ap.add_argument("--db-path", default="data/locutorio.sqlite")
    ap.add_argument("--install-dir", required=True)
    ap.add_argument("--openssl-rel", default=r"runtime\openssl\openssl.exe")
    ap.add_argument("--printer-name-contains", default="")
    ap.add_argument("--print-mode", default="gdi", choices=["escpos", "gdi"])
    args = ap.parse_args()

    db_path = Path(args.db_path)
    init_db(str(db_path))

    install_dir = Path(args.install_dir)
    openssl_path = install_dir / Path(args.openssl_rel)

    set_setting(str(db_path), "openssl_path", str(openssl_path))
    set_setting(str(db_path), "printer_name_contains", args.printer_name_contains)
    set_setting(str(db_path), "print_mode", args.print_mode)

    print("[OK] DB configurada:", db_path)
    print("[OK] openssl_path:", openssl_path)


if __name__ == "__main__":
    main()

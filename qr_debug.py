from __future__ import annotations

import json
from datetime import datetime

def log_qr(*, path: str = "qr.log", url: str, payload: dict) -> None:
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n" + "="*60 + "\n")
            f.write(f"{ts}\n")
            f.write(url + "\n")
            f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        # nunca romper la facturación por el logger
        pass

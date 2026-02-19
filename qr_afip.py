from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

def build_afip_qr_payload(
    *,
    fecha_emision: datetime,
    cuit_emisor: int,
    pto_vta: int,
    tipo_cmp: int,
    nro_cmp: int,
    importe: float,
    moneda: str = "PES",
    ctz: float = 1.0,
    tipo_cod_aut: str = "E",
    cod_aut: str = "",
    tipo_doc_rec: int | None = None,
    nro_doc_rec: str | None = None,
    ver: int = 1,
) -> dict:
    # AFIP/ARCA pide fecha YYYY-MM-DD
    if fecha_emision.tzinfo is None:
        # asumimos hora local; convertimos a date string
        fecha_str = fecha_emision.strftime("%Y-%m-%d")
    else:
        fecha_str = fecha_emision.astimezone(timezone.utc).strftime("%Y-%m-%d")

    payload = {
        "ver": ver,
        "fecha": fecha_str,
        "cuit": int(cuit_emisor),
        "ptoVta": int(pto_vta),
        "tipoCmp": int(tipo_cmp),
        "nroCmp": int(nro_cmp),
        "importe": round(float(importe), 2),
        "moneda": str(moneda),
        "ctz": float(ctz),
        "tipoCodAut": str(tipo_cod_aut),
        "codAut": str(cod_aut),
    }
    if tipo_doc_rec is not None and nro_doc_rec is not None:
        payload["tipoDocRec"] = int(tipo_doc_rec)
        payload["nroDocRec"] = int(nro_doc_rec) if str(nro_doc_rec).isdigit() else str(nro_doc_rec)
    return payload

def build_afip_qr_url(**kwargs) -> str:
    payload = build_afip_qr_payload(**kwargs)
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return "https://www.afip.gob.ar/fe/qr/?p=" + b64

from __future__ import annotations

from datetime import datetime

from db import get_all_settings, get_ticket_lines

def _fmt_fecha(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def _items_block(items: list[dict], *, width: int = 32) -> str:
    """
    Bloque de ítems pensado para 58mm: 32 chars aprox.
    Header ("Cant./Precio Unit.") se deja en template.
    """
    lines: list[str] = []
    for it in items:
        name = str(it.get("name","")).strip()
        qty = float(it.get("qty", 0))
        price = float(it.get("price", 0))
        subtotal = float(it.get("subtotal", 0))

        # 1) Descripción (cortada)
        if name:
            lines.append(name[:width])

        # 2) Cant x PUnit = Subt (compacto)
        line2 = f"{qty:g} x {price:.2f} = {subtotal:.2f}"
        lines.append(line2[:width])

    return "\n".join(lines)

def build_ticket_text(
    *,
    db_path: str,
    cbte_tipo_label: str,
    pv: int,
    cbte_nro: int,
    fecha: datetime,
    items: list[dict],
    total: float,
    cae: str,
    cae_vto_yyyymmdd: str,
    cliente_label: str,
) -> str:
    """
    Mandamiento #1: todo string sale de DB (ticket_template + app_settings).
    """
    settings = get_all_settings(db_path)
    template_lines = get_ticket_lines(db_path)

    cae_vto_fmt = cae_vto_yyyymmdd
    if cae_vto_yyyymmdd and len(cae_vto_yyyymmdd) == 8:
        cae_vto_fmt = f"{cae_vto_yyyymmdd[0:4]}-{cae_vto_yyyymmdd[4:6]}-{cae_vto_yyyymmdd[6:8]}"

    ctx = {
        **settings,
        "cbte_tipo_label": cbte_tipo_label,
        "pv": int(pv),
        "cbte_nro": int(cbte_nro),
        "fecha": _fmt_fecha(fecha),
        "cliente_label": cliente_label,
        "total": float(total),
        "cae": str(cae),
        "cae_vto_yyyymmdd": str(cae_vto_yyyymmdd),
        "cae_vto_fmt": cae_vto_fmt,
        "items_block": _items_block(items),
    }

    out_lines: list[str] = []
    for ln in template_lines:
        try:
            out_lines.append(str(ln).format(**ctx))
        except Exception:
            # si el usuario puso un placeholder mal, imprimimos la línea literal
            out_lines.append(str(ln))
    return "\n".join(out_lines).rstrip() + "\n"

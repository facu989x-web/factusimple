
from __future__ import annotations
from datetime import datetime
from db import get_setting, get_template

def _clip(s: str, cols: int) -> str:
    s = (s or "")
    return s if len(s) <= cols else s[:cols]

def _center(s: str, cols: int) -> str:
    s = (s or "").strip()
    if len(s) >= cols:
        return s[:cols]
    pad = (cols - len(s)) // 2
    return (" " * pad) + s

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
    cols = int(get_setting(db_path, "ticket.max_cols", "32") or "32")

    fantasy = get_template(db_path, "fantasy_name", "Comercio")
    rs = get_template(db_path, "razon_social_line", "")
    cuit = get_template(db_path, "cuit_line", "")
    iva = get_template(db_path, "condicion_iva_line", "")
    inicio = get_template(db_path, "start_activities_line", "")
    addr = get_template(db_path, "address_line", "")
    city = get_template(db_path, "cp_city_line", "")
    defensa = get_template(db_path, "consumer_protection_line", "")
    h1 = get_template(db_path, "items_header_1", "Cant./Precio Unit.")
    h2 = get_template(db_path, "items_header_2", "DESCRIPCION (%IVA)")
    thanks = get_template(db_path, "footer_thanks", "")

    lines: list[str] = []

    def add(s: str = ""):
        lines.append(_clip(s, cols))

    add(_center(fantasy, cols))
    if rs: add(_center(rs, cols))
    if cuit: add(_center(cuit, cols))
    if iva: add(_center(iva, cols))
    if inicio: add(_center(inicio, cols))
    if addr: add(_center(addr, cols))
    if city: add(_center(city, cols))
    if defensa: add(_center(defensa, cols))

    add("-" * cols)
    add(_center(cbte_tipo_label, cols))
    add(_clip(f"PV {pv:04d}  NRO {cbte_nro:08d}", cols))
    add(_clip(f"Fecha: {fecha.strftime('%d/%m/%Y %H:%M')}", cols))
    add(_clip(f"Cliente: {cliente_label}", cols))
    add("-" * cols)
    add(_clip(h1, cols))
    add(_clip(h2, cols))
    add("-" * cols)

    for it in items:
        name = (it.get("name") or "").strip()
        qty = float(it.get("qty") or 0)
        price = float(it.get("price") or 0)
        subtotal = float(it.get("subtotal") or (qty * price))

        add(_clip(f"{qty:g} x {price:.2f} = {subtotal:.2f}", cols))
        while name:
            add(_clip(name, cols))
            name = name[cols:]

    add("-" * cols)
    add(_clip(f"TOTAL: {float(total):.2f}", cols))
    add(_clip(f"CAE: {cae}", cols))
    add(_clip(f"Vto CAE: {cae_vto_yyyymmdd}", cols))
    add("-" * cols)
    if thanks:
        add(_center(thanks, cols))
    add("")
    return "\n".join(lines)

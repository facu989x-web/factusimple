from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any

CBTE_TIPO_FACTURA_B = 6
CBTE_TIPO_FACTURA_C = 11

def normalize_taxpayer_type(value: str | None) -> str:
  v = (value or "MONO").strip().upper()
  return v if v in ("MONO", "RI") else "MONO"

def is_cbte_allowed_for_taxpayer(*, taxpayer_type: str | None, cbte_tipo: int) -> bool:
  t = normalize_taxpayer_type(taxpayer_type)
  if t == "MONO":
    return int(cbte_tipo) == CBTE_TIPO_FACTURA_C
  return int(cbte_tipo) == CBTE_TIPO_FACTURA_B

def allowed_cbte_types_for_taxpayer(taxpayer_type: str | None) -> list[int]:
  t = normalize_taxpayer_type(taxpayer_type)
  if t == "MONO":
    return [CBTE_TIPO_FACTURA_C]
  return [CBTE_TIPO_FACTURA_B]

def default_cbte_for_taxpayer(taxpayer_type: str | None) -> int:
  return allowed_cbte_types_for_taxpayer(taxpayer_type)[0]

def taxpayer_type_label(taxpayer_type: str | None) -> str:
  t = normalize_taxpayer_type(taxpayer_type)
  return "Monotributo" if t == "MONO" else "Responsable Inscripto"

def taxpayer_type_lock_text(taxpayer_type: str | None) -> str:
  t = normalize_taxpayer_type(taxpayer_type)
  if t == "MONO":
    return "Régimen MONOTRIBUTO: solo se permite Factura C."
  return "Régimen RESPONSABLE INSCRIPTO: solo se permite Factura B."

def taxpayer_blocked_cbte_message(taxpayer_type: str | None, cbte_tipo: int) -> str:
  t = normalize_taxpayer_type(taxpayer_type)
  cbte = "Factura B" if int(cbte_tipo) == CBTE_TIPO_FACTURA_B else "Factura C"
  allowed = "Factura C" if t == "MONO" else "Factura B"
  return f"{cbte} no está permitido para {taxpayer_type_label(t)}. Usá {allowed}. Podés cambiarlo en Configuración > Régimen fiscal."

# ---------------- Schema ----------------

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  pv INTEGER NOT NULL,
  cbte_tipo INTEGER NOT NULL,
  cbte_nro INTEGER NOT NULL,
  doc_tipo INTEGER NOT NULL,
  doc_nro TEXT NOT NULL,
  imp_total REAL NOT NULL,
  cae TEXT NOT NULL,
  cae_vto TEXT NOT NULL,
  modo TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL,
  item_name TEXT NOT NULL,
  qty REAL NOT NULL,
  price REAL NOT NULL,
  subtotal REAL NOT NULL,
  FOREIGN KEY(invoice_id) REFERENCES invoices(id)
);

CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at);
CREATE INDEX IF NOT EXISTS idx_invoices_cbte ON invoices(pv, cbte_tipo, cbte_nro);

-- Settings (todo string configurable)
CREATE TABLE IF NOT EXISTS app_settings (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);

-- Ticket template: lista de líneas (ordenadas)
CREATE TABLE IF NOT EXISTS ticket_template (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  line_no INTEGER NOT NULL,
  text TEXT NOT NULL
);

-- Licencia (opción D) - por defecto enabled=0 (no bloquea)
CREATE TABLE IF NOT EXISTS license (
  id INTEGER PRIMARY KEY CHECK (id=1),
  enabled INTEGER NOT NULL DEFAULT 0,
  owner TEXT DEFAULT '',
  valid_until TEXT DEFAULT '',
  fingerprint TEXT DEFAULT '',
  license_key TEXT DEFAULT ''
);

INSERT OR IGNORE INTO license(id, enabled) VALUES (1, 0);
"""

DEFAULT_SETTINGS: dict[str, str] = {
  "app_name": "FacturaSimple",
  "modo": "PROD",
  "punto_venta": "14",
  "cuit_emisor": "0",
  "razon_social": "FacturaSimple",
  "printer_name_contains": "",
  "print_mode": "escpos",  # escpos|gdi
  "openssl_path": "",
  "cert_crt_path": "",
  "private_key_path": "",
  "private_key_password": "",
  "setup_completed": "0",
  "taxpayer_type": "MONO",  # MONO|RI
}

DEFAULT_TICKET_LINES = [
  "{app_name}",
  "",
  "RAZON SOCIAL",
  "CUIT: {cuit_emisor}",
  "",
  "{cbte_tipo_label}",
  "",
  "-------------------------------",
  "Fecha inicio actividades: 00/00/0000",
  "DIRECCION C.P 0000 - CABA",
  "TEL 147 CABA PROTECCION",
  "AL CONSUMIDOR",
  "-------------------------------",
  "{cbte_tipo_label}",
  "{fecha}",
  "",
  "PV {pv:04d} NRO {cbte_nro:08d}",
  "",
  "Cliente: {cliente_label}",
  "-------------------------------",
  "Cant./Precio Unit.",
  "{items_block}",
  "-------------------------------",
  "TOTAL: $ {total:.2f}",
  "",
  "CAE: {cae}",
  "VTO CAE: {cae_vto_fmt}",
  "-------------------------------",
  "Gracias!",
]

def _connect(db_path: str) -> sqlite3.Connection:
  con = sqlite3.connect(db_path)
  con.row_factory = sqlite3.Row
  return con

def init_db(db_path: str) -> None:
  Path(db_path).parent.mkdir(parents=True, exist_ok=True)
  con = _connect(db_path)
  try:
    con.executescript(SCHEMA)
    con.commit()

    # settings defaults
    cur = con.cursor()
    for k, v in DEFAULT_SETTINGS.items():
      cur.execute("INSERT OR IGNORE INTO app_settings(k,v) VALUES(?,?)", (k, str(v)))
    con.commit()

    # ticket defaults
    cur.execute("SELECT COUNT(*) AS n FROM ticket_template")
    if int(cur.fetchone()["n"]) == 0:
      for i, ln in enumerate(DEFAULT_TICKET_LINES, start=1):
        cur.execute("INSERT INTO ticket_template(line_no,text) VALUES(?,?)", (i, ln))
      con.commit()
  finally:
    con.close()

# ---------------- Settings ----------------

def get_setting(db_path: str, key: str, default: str = "") -> str:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("SELECT v FROM app_settings WHERE k=?", (key,))
    r = cur.fetchone()
    return (r["v"] if r else default) or default
  finally:
    con.close()

def set_setting(db_path: str, key: str, value: str) -> None:
  con = _connect(db_path)
  try:
    con.execute("INSERT INTO app_settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))
    con.commit()
  finally:
    con.close()

def get_all_settings(db_path: str) -> dict[str, str]:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("SELECT k,v FROM app_settings")
    return {r["k"]: r["v"] for r in cur.fetchall()}
  finally:
    con.close()

# ---------------- Ticket template ----------------

def get_ticket_lines(db_path: str) -> list[str]:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("SELECT text FROM ticket_template ORDER BY line_no ASC, id ASC")
    return [str(r["text"]) for r in cur.fetchall()]
  finally:
    con.close()

def save_ticket_lines(db_path: str, text: str) -> None:
    lines = _normalize_template_text(text)

    con = _connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM ticket_template")

        for i, ln in enumerate(lines, start=1):
            cur.execute(
                "INSERT INTO ticket_template(line_no,text) VALUES(?,?)",
                (i, ln)
            )

        con.commit()
    finally:
        con.close()


def _normalize_template_text(text: str) -> list[str]:
  raw = text or ""

  # caso normal: usuario edita multilinea en QTextEdit
  if "\n" in raw or "\r" in raw:
    return raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")

  # caso copy/paste desde string con saltos escapados ("\\n")
  if "\\n" in raw:
    return raw.split("\\n")

  return [raw]

# ---------------- Invoices ----------------

def insert_invoice(db_path: str, *, pv: int, cbte_tipo: int, cbte_nro: int,
                   doc_tipo: int, doc_nro: str, imp_total: float,
                   cae: str, cae_vto: str, modo: str, items: list[dict]) -> int:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    created_at = datetime.now().isoformat(timespec="seconds").replace("T", " ")
    cur.execute(
      """INSERT INTO invoices(created_at,pv,cbte_tipo,cbte_nro,doc_tipo,doc_nro,imp_total,cae,cae_vto,modo)
         VALUES(?,?,?,?,?,?,?,?,?,?)""",
      (created_at, pv, cbte_tipo, cbte_nro, doc_tipo, doc_nro, float(imp_total), cae, cae_vto, modo)
    )
    invoice_id = int(cur.lastrowid)
    for it in items:
      cur.execute(
        """INSERT INTO invoice_items(invoice_id,item_name,qty,price,subtotal)
           VALUES(?,?,?,?,?)""",
        (invoice_id, it["name"], float(it["qty"]), float(it["price"]), float(it["subtotal"]))
      )
    con.commit()
    return invoice_id
  finally:
    con.close()

def list_invoices(db_path: str, *, date_yyyy_mm_dd: str | None = None,
                  from_yyyy_mm_dd: str | None = None, to_yyyy_mm_dd: str | None = None,
                  limit: int = 500) -> list[dict]:
  con = _connect(db_path)
  try:
    cur = con.cursor()

    where = []
    params: list[Any] = []
    if date_yyyy_mm_dd:
      where.append("created_at >= ? AND created_at <= ?")
      params.extend([f"{date_yyyy_mm_dd} 00:00:00", f"{date_yyyy_mm_dd} 23:59:59"])
    if from_yyyy_mm_dd and to_yyyy_mm_dd:
      where.append("created_at >= ? AND created_at <= ?")
      params.extend([f"{from_yyyy_mm_dd} 00:00:00", f"{to_yyyy_mm_dd} 23:59:59"])

    sql = """
      SELECT id, created_at, pv, cbte_tipo, cbte_nro, doc_tipo, doc_nro,
             imp_total, cae, cae_vto, modo
      FROM invoices
    """
    if where:
      sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]
  finally:
    con.close()

def daily_summary(db_path: str, *, date_yyyy_mm_dd: str) -> dict:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    d0 = f"{date_yyyy_mm_dd} 00:00:00"
    d1 = f"{date_yyyy_mm_dd} 23:59:59"
    cur.execute(
      """
      SELECT COUNT(*) as cant, COALESCE(SUM(imp_total), 0) as total
      FROM invoices
      WHERE created_at >= ? AND created_at <= ?
      """,
      (d0, d1),
    )
    row = cur.fetchone()
    return {"cant": int(row["cant"]), "total": float(row["total"])}
  finally:
    con.close()

def range_summary(db_path: str, *, from_yyyy_mm_dd: str, to_yyyy_mm_dd: str) -> dict:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    d0 = f"{from_yyyy_mm_dd} 00:00:00"
    d1 = f"{to_yyyy_mm_dd} 23:59:59"
    cur.execute(
      """
      SELECT COUNT(*) as cant, COALESCE(SUM(imp_total), 0) as total
      FROM invoices
      WHERE created_at >= ? AND created_at <= ?
      """,
      (d0, d1),
    )
    row = cur.fetchone()
    return {"cant": int(row["cant"]), "total": float(row["total"])}
  finally:
    con.close()

def get_invoice_with_items(db_path: str, invoice_id: int) -> dict:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("SELECT * FROM invoices WHERE id=?", (int(invoice_id),))
    inv = cur.fetchone()
    if not inv:
      raise RuntimeError("No existe el comprobante.")
    cur.execute("SELECT item_name, qty, price, subtotal FROM invoice_items WHERE invoice_id=? ORDER BY id ASC", (int(invoice_id),))
    items = [dict(r) for r in cur.fetchall()]
    return {"invoice": dict(inv), "items": items}
  finally:
    con.close()

# ---------------- License (opción D) ----------------

def machine_fingerprint() -> str:
  base = "|".join([
    platform.system(),
    platform.release(),
    platform.version(),
    platform.machine(),
    os.environ.get("COMPUTERNAME", ""),
  ]).encode("utf-8", errors="ignore")
  return hashlib.sha256(base).hexdigest()

def _normalize_license_key(s: str) -> str:
  return "".join(ch for ch in (s or "") if ch.isalnum()).upper()

def _calc_expected_key(fp: str, owner: str, valid_until: str) -> str:
  raw = f"{fp}|{owner}|{valid_until}".encode("utf-8")
  return hashlib.sha256(raw).hexdigest().upper()[:32]

def ensure_license_row(db_path: str) -> None:
  con = _connect(db_path)
  try:
    con.execute("INSERT OR IGNORE INTO license(id, enabled) VALUES(1, 0)")
    con.commit()
  finally:
    con.close()

def validate_license(db_path: str) -> None:
  """
  Si enabled=0 -> no bloquea (modo libre / desarrollo).
  Si enabled=1 -> valida vencimiento + fingerprint + key.
  """
  ensure_license_row(db_path)
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("SELECT license_key, owner, valid_until, fingerprint, enabled FROM license WHERE id=1")
    row = cur.fetchone()
    if not row:
      return

    if int(row["enabled"]) == 0:
      return

    owner = (row["owner"] or "").strip()
    valid_until = (row["valid_until"] or "").strip()
    lic = (row["license_key"] or "").strip()
    fp_db = (row["fingerprint"] or "").strip()

    fp_now = machine_fingerprint()

    if not valid_until:
      raise RuntimeError("Licencia inválida: falta fecha de vencimiento.")
    try:
      vto = datetime.strptime(valid_until, "%Y-%m-%d").date()
    except Exception:
      raise RuntimeError("Licencia inválida: formato de vencimiento debe ser YYYY-MM-DD.")

    today = datetime.now().date()
    if vto < today:
      raise RuntimeError(f"Licencia vencida el {valid_until}.")

    if not fp_db:
      cur.execute("UPDATE license SET fingerprint=? WHERE id=1", (fp_now,))
      con.commit()
      fp_db = fp_now

    if fp_db != fp_now:
      raise RuntimeError("Licencia inválida: el equipo no coincide (fingerprint distinto).")

    expected = _calc_expected_key(fp_db, owner, valid_until)
    if _normalize_license_key(lic) != _normalize_license_key(expected):
      raise RuntimeError("Licencia inválida: clave incorrecta.")
  finally:
    con.close()


import sqlite3
from pathlib import Path
from datetime import datetime

# -------------------- SCHEMA --------------------
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

-- Configuración comercial (DB manda)
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_templates (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

"""

def _connect(db_path: str) -> sqlite3.Connection:
  con = sqlite3.connect(db_path)
  con.row_factory = sqlite3.Row
  return con

def init_db(db_path: str) -> None:
  Path(db_path).parent.mkdir(parents=True, exist_ok=True)
  con = sqlite3.connect(db_path)
  try:
    con.executescript(SCHEMA)
    con.commit()
  finally:
    con.close()

# -------------------- Invoices --------------------
def insert_invoice(db_path: str, *, pv: int, cbte_tipo: int, cbte_nro: int,
                   doc_tipo: int, doc_nro: str, imp_total: float,
                   cae: str, cae_vto: str, modo: str, items: list[dict]) -> int:
  con = sqlite3.connect(db_path)
  try:
    cur = con.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
      """INSERT INTO invoices(created_at,pv,cbte_tipo,cbte_nro,doc_tipo,doc_nro,imp_total,cae,cae_vto,modo)
         VALUES(?,?,?,?,?,?,?,?,?,?)""",
      (created_at, pv, cbte_tipo, cbte_nro, doc_tipo, doc_nro, float(imp_total), cae, cae_vto, modo)
    )
    invoice_id = cur.lastrowid
    for it in items:
      cur.execute(
        """INSERT INTO invoice_items(invoice_id,item_name,qty,price,subtotal)
           VALUES(?,?,?,?,?)""",
        (invoice_id, it["name"], float(it["qty"]), float(it["price"]), float(it["subtotal"]))
      )
    con.commit()
    return int(invoice_id)
  finally:
    con.close()

def list_invoices(db_path: str, *, date_yyyy_mm_dd: str | None = None, date_to_yyyy_mm_dd: str | None = None, limit: int = 500):
  con = _connect(db_path)
  try:
    cur = con.cursor()
    if date_yyyy_mm_dd and not date_to_yyyy_mm_dd:
      d0 = date_yyyy_mm_dd + "T00:00:00"
      d1 = date_yyyy_mm_dd + "T23:59:59"
      cur.execute(
        """
        SELECT id, created_at, pv, cbte_tipo, cbte_nro, doc_tipo, doc_nro, imp_total, cae, cae_vto, modo
        FROM invoices
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (d0, d1, limit),
      )
    elif date_yyyy_mm_dd and date_to_yyyy_mm_dd:
      d0 = date_yyyy_mm_dd + "T00:00:00"
      d1 = date_to_yyyy_mm_dd + "T23:59:59"
      cur.execute(
        """
        SELECT id, created_at, pv, cbte_tipo, cbte_nro, doc_tipo, doc_nro, imp_total, cae, cae_vto, modo
        FROM invoices
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (d0, d1, limit),
      )
    else:
      cur.execute(
        """
        SELECT id, created_at, pv, cbte_tipo, cbte_nro, doc_tipo, doc_nro, imp_total, cae, cae_vto, modo
        FROM invoices
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
      )
    return [dict(r) for r in cur.fetchall()]
  finally:
    con.close()

def daily_summary(db_path: str, *, date_yyyy_mm_dd: str):
  con = _connect(db_path)
  try:
    cur = con.cursor()
    d0 = date_yyyy_mm_dd + "T00:00:00"
    d1 = date_yyyy_mm_dd + "T23:59:59"
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

def range_summary(db_path: str, *, date_from_yyyy_mm_dd: str, date_to_yyyy_mm_dd: str):
  con = _connect(db_path)
  try:
    cur = con.cursor()
    d0 = date_from_yyyy_mm_dd + "T00:00:00"
    d1 = date_to_yyyy_mm_dd + "T23:59:59"
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

# -------------------- Settings / Templates (DB manda) --------------------
def get_setting(db_path: str, key: str, default: str | None = None) -> str | None:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row["value"] if row else default
  finally:
    con.close()

def set_setting(db_path: str, key: str, value: str) -> None:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)", (key, value))
    con.commit()
  finally:
    con.close()

def get_template(db_path: str, key: str, default: str = "") -> str:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("SELECT value FROM ticket_templates WHERE key=?", (key,))
    row = cur.fetchone()
    return row["value"] if row else default
  finally:
    con.close()

def set_template(db_path: str, key: str, value: str) -> None:
  con = _connect(db_path)
  try:
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO ticket_templates(key,value) VALUES(?,?)", (key, value))
    con.commit()
  finally:
    con.close()

def ensure_defaults(db_path: str, seed: dict) -> None:
  """
  Sembrado inicial (solo si no existen keys).
  seed: settings.json (para tomar defaults técnicos).
  """
  # app_settings defaults
  defaults = {
    "setup.done": "0",
    "security.admin_pin_hash": "",
    "print.mode": seed.get("print_mode", "escpos"),
    "print.printer_name_contains": seed.get("printer_name_contains", ""),
    "print.gdi_target_mm": str(seed.get("gdi_target_mm", 58)),
    "print.gdi_margin_mm": str(seed.get("gdi_margin_mm", 5)),
    "ticket.max_cols": str(seed.get("ticket_max_cols", 32)),
  }
  for k, v in defaults.items():
    if get_setting(db_path, k, None) is None:
      set_setting(db_path, k, str(v))

  # ticket templates defaults (mandamiento #1)
  tdef = {
    "fantasy_name": seed.get("fantasy_name", "FacturaSimple"),
    "razon_social_line": seed.get("razon_social", ""),
    "cuit_line": f"CUIT {seed.get('cuit_emisor','')}".strip(),
    "condicion_iva_line": seed.get("condicion_iva", "RESP. MONOTRIBUTO"),
    "start_activities_line": seed.get("start_activities_line", "Inicio actividades: 01/09/2009"),
    "address_line": seed.get("address_line", "Av. Directorio 2015"),
    "cp_city_line": seed.get("cp_city_line", "C.P. 1406 - CABA"),
    "consumer_protection_line": seed.get("consumer_protection_line", "TEL 147 CABA PROTECCION AL CONSUMIDOR"),
    "items_header_1": seed.get("items_header_1", "Cant./Precio Unit."),
    "items_header_2": seed.get("items_header_2", "DESCRIPCION (%IVA)"),
    "footer_thanks": seed.get("footer_thanks", "Gracias por su compra"),
  }
  for k, v in tdef.items():
    if get_template(db_path, k, None) is None:
      set_template(db_path, k, str(v))


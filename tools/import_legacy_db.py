from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from db import init_db


def _connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    cur = con.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def import_invoices(*, src_db: str, dst_db: str) -> dict:
    init_db(dst_db)

    src = _connect(src_db)
    dst = _connect(dst_db)

    imported = 0
    skipped = 0

    try:
        s = src.cursor()
        d = dst.cursor()

        s.execute(
            """
            SELECT id, created_at, pv, cbte_tipo, cbte_nro, doc_tipo, doc_nro,
                   imp_total, cae, cae_vto, modo
            FROM invoices
            ORDER BY id ASC
            """
        )

        for inv in s.fetchall():
            d.execute(
                "SELECT id FROM invoices WHERE pv=? AND cbte_tipo=? AND cbte_nro=?",
                (inv["pv"], inv["cbte_tipo"], inv["cbte_nro"]),
            )
            existing = d.fetchone()
            if existing:
                skipped += 1
                continue

            d.execute(
                """
                INSERT INTO invoices(created_at,pv,cbte_tipo,cbte_nro,doc_tipo,doc_nro,imp_total,cae,cae_vto,modo)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    inv["created_at"],
                    inv["pv"],
                    inv["cbte_tipo"],
                    inv["cbte_nro"],
                    inv["doc_tipo"],
                    inv["doc_nro"],
                    inv["imp_total"],
                    inv["cae"],
                    inv["cae_vto"],
                    inv["modo"],
                ),
            )
            new_id = int(d.lastrowid)

            s.execute(
                "SELECT item_name, qty, price, subtotal FROM invoice_items WHERE invoice_id=? ORDER BY id ASC",
                (inv["id"],),
            )
            for it in s.fetchall():
                d.execute(
                    "INSERT INTO invoice_items(invoice_id,item_name,qty,price,subtotal) VALUES(?,?,?,?,?)",
                    (new_id, it["item_name"], it["qty"], it["price"], it["subtotal"]),
                )

            imported += 1

        dst.commit()
    finally:
        src.close()
        dst.close()

    return {"imported": imported, "skipped": skipped}


def import_settings_best_effort(*, src_db: str, dst_db: str) -> int:
    src = _connect(src_db)
    dst = _connect(dst_db)
    moved = 0

    try:
        s = src.cursor()
        d = dst.cursor()

        if _table_exists(src, "app_settings"):
            # schema viejo: key/value ; schema nuevo: k/v
            cols = [r[1] for r in s.execute("PRAGMA table_info(app_settings)").fetchall()]
            if "k" in cols and "v" in cols:
                s.execute("SELECT k, v FROM app_settings")
                rows = [(r["k"], r["v"]) for r in s.fetchall()]
            elif "key" in cols and "value" in cols:
                s.execute("SELECT key, value FROM app_settings")
                rows = [(r["key"], r["value"]) for r in s.fetchall()]
            else:
                rows = []

            for k, v in rows:
                d.execute(
                    "INSERT INTO app_settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    (str(k), str(v)),
                )
                moved += 1

        dst.commit()
    finally:
        src.close()
        dst.close()

    return moved


def main() -> None:
    ap = argparse.ArgumentParser(description="Importa comprobantes desde ventas.db legacy a DB actual")
    ap.add_argument("--src-db", required=True, help="DB origen (legacy)")
    ap.add_argument("--dst-db", required=True, help="DB destino (actual)")
    ap.add_argument("--import-settings", action="store_true", help="Importar settings también")
    args = ap.parse_args()

    src = Path(args.src_db)
    dst = Path(args.dst_db)

    if not src.exists():
        raise SystemExit(f"No existe DB origen: {src}")

    result = import_invoices(src_db=str(src), dst_db=str(dst))
    print(f"[OK] Comprobantes importados: {result['imported']}")
    print(f"[OK] Comprobantes omitidos (duplicados): {result['skipped']}")

    if args.import_settings:
        moved = import_settings_best_effort(src_db=str(src), dst_db=str(dst))
        print(f"[OK] Settings importados/actualizados: {moved}")


if __name__ == "__main__":
    main()

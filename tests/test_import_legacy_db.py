import tempfile
import unittest
from pathlib import Path

from db import init_db, list_invoices, daily_summary, range_summary
from tools.import_legacy_db import import_invoices
import sqlite3


class ImportLegacyDbTest(unittest.TestCase):
    def _make_legacy(self, path: Path):
        con = sqlite3.connect(path)
        cur = con.cursor()
        cur.executescript(
            """
            CREATE TABLE invoices (
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
            CREATE TABLE invoice_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              invoice_id INTEGER NOT NULL,
              item_name TEXT NOT NULL,
              qty REAL NOT NULL,
              price REAL NOT NULL,
              subtotal REAL NOT NULL
            );
            """
        )
        cur.execute(
            "INSERT INTO invoices(created_at,pv,cbte_tipo,cbte_nro,doc_tipo,doc_nro,imp_total,cae,cae_vto,modo) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("2026-01-01 10:00:00", 4, 11, 1, 99, "0", 100.0, "123", "20260131", "PROD"),
        )
        inv_id = cur.lastrowid
        cur.execute(
            "INSERT INTO invoice_items(invoice_id,item_name,qty,price,subtotal) VALUES(?,?,?,?,?)",
            (inv_id, "ITEM", 1, 100, 100),
        )
        con.commit()
        con.close()

    def test_import_invoices(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "ventas.db"
            dst = Path(td) / "facturasimple.sqlite"
            self._make_legacy(src)
            init_db(str(dst))

            res = import_invoices(src_db=str(src), dst_db=str(dst))
            self.assertEqual(res["imported"], 1)
            self.assertEqual(res["skipped"], 0)

            # segunda corrida no duplica
            res2 = import_invoices(src_db=str(src), dst_db=str(dst))
            self.assertEqual(res2["imported"], 0)
            self.assertEqual(res2["skipped"], 1)

    def test_legacy_date_format_shows_in_listings(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "ventas.db"
            dst = Path(td) / "facturasimple.sqlite"
            self._make_legacy(src)

            # Simula formato viejo no-ISO: DD/MM/YYYY HH:MM:SS
            con = sqlite3.connect(src)
            con.execute("UPDATE invoices SET created_at=?", ("01/01/2026 10:00:00",))
            con.commit()
            con.close()

            init_db(str(dst))
            import_invoices(src_db=str(src), dst_db=str(dst))

            rows_day = list_invoices(str(dst), date_yyyy_mm_dd="2026-01-01", limit=100)
            rows_range = list_invoices(str(dst), from_yyyy_mm_dd="2026-01-01", to_yyyy_mm_dd="2026-01-31", limit=100)
            self.assertEqual(len(rows_day), 1)
            self.assertEqual(len(rows_range), 1)

            day_sum = daily_summary(str(dst), date_yyyy_mm_dd="2026-01-01")
            range_sum = range_summary(str(dst), from_yyyy_mm_dd="2026-01-01", to_yyyy_mm_dd="2026-01-31")
            self.assertEqual(day_sum["cant"], 1)
            self.assertEqual(range_sum["cant"], 1)


if __name__ == "__main__":
    unittest.main()

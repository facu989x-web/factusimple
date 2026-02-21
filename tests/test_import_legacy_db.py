import tempfile
import unittest
from pathlib import Path

from db import init_db
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


if __name__ == "__main__":
    unittest.main()

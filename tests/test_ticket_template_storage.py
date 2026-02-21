import tempfile
import unittest
from pathlib import Path

from db import init_db, save_ticket_lines, get_ticket_lines


class TicketTemplateStorageTest(unittest.TestCase):
    def test_save_ticket_lines_with_escaped_newlines(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "test.sqlite")
            init_db(db_path)

            save_ticket_lines(db_path, "A\\nB\\nC")
            lines = get_ticket_lines(db_path)

            self.assertEqual(lines, ["A", "B", "C"])

    def test_save_ticket_lines_with_real_newlines(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "test.sqlite")
            init_db(db_path)

            save_ticket_lines(db_path, "A\nB\nC")
            lines = get_ticket_lines(db_path)

            self.assertEqual(lines, ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()

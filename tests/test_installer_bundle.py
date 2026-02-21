import json
import tempfile
import unittest
from pathlib import Path

from installer.build_bundle import write_manifest


class InstallerBundleTest(unittest.TestCase):
    def test_write_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            p = write_manifest(
                out_dir=out,
                files=["app.py", "db.py"],
                openssl_files=["runtime/openssl/openssl.exe"],
            )
            self.assertTrue(p.exists())
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["files"], ["app.py", "db.py"])
            self.assertEqual(data["openssl_runtime_files"], ["runtime/openssl/openssl.exe"])


if __name__ == "__main__":
    unittest.main()

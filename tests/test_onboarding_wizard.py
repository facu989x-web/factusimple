import tempfile
import unittest
from pathlib import Path

from arca_onboarding_wizard import (
    build_subject,
    normalize_name,
    write_manual_checklist,
)


class OnboardingWizardHelpersTest(unittest.TestCase):
    def test_build_subject(self):
        s = build_subject(cuit="20353951972", razon_social="BARU FACUNDO DANIEL", cn="FACTURASIMPLE")
        self.assertEqual(
            s,
            "/C=AR/O=BARU FACUNDO DANIEL/CN=FACTURASIMPLE/serialNumber=CUIT 20353951972",
        )

    def test_normalize_name(self):
        self.assertEqual(normalize_name("  BARU   FACUNDO   DANIEL  "), "BARU FACUNDO DANIEL")

    def test_write_manual_checklist(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "checklist.md"
            write_manual_checklist(
                out_path=p,
                cuit="20353951972",
                pv="4",
                cn="FACTURASIMPLE",
                cert_path="certs/monotributo.crt",
                key_path="certs/clave.key",
            )
            txt = p.read_text(encoding="utf-8")
            self.assertIn("Checklist onboarding ARCA/WSFE", txt)
            self.assertIn("CUIT 20353951972", txt)
            self.assertIn("PV en app = `4`", txt)


if __name__ == "__main__":
    unittest.main()

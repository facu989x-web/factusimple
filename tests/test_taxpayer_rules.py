import unittest

from db import (
    CBTE_TIPO_FACTURA_B,
    CBTE_TIPO_FACTURA_C,
    normalize_taxpayer_type,
    is_cbte_allowed_for_taxpayer,
    allowed_cbte_types_for_taxpayer,
    default_cbte_for_taxpayer,
    taxpayer_type_lock_text,
    taxpayer_blocked_cbte_message,
)


class TaxpayerRulesTest(unittest.TestCase):
    def test_normalize_taxpayer_type(self):
        self.assertEqual(normalize_taxpayer_type("mono"), "MONO")
        self.assertEqual(normalize_taxpayer_type("RI"), "RI")
        self.assertEqual(normalize_taxpayer_type(""), "MONO")
        self.assertEqual(normalize_taxpayer_type(None), "MONO")
        self.assertEqual(normalize_taxpayer_type("UNKNOWN"), "MONO")

    def test_mono_allows_only_factura_c(self):
        self.assertTrue(is_cbte_allowed_for_taxpayer(taxpayer_type="MONO", cbte_tipo=CBTE_TIPO_FACTURA_C))
        self.assertFalse(is_cbte_allowed_for_taxpayer(taxpayer_type="MONO", cbte_tipo=CBTE_TIPO_FACTURA_B))
        self.assertEqual(allowed_cbte_types_for_taxpayer("MONO"), [CBTE_TIPO_FACTURA_C])

    def test_ri_allows_only_factura_b(self):
        self.assertTrue(is_cbte_allowed_for_taxpayer(taxpayer_type="RI", cbte_tipo=CBTE_TIPO_FACTURA_B))
        self.assertFalse(is_cbte_allowed_for_taxpayer(taxpayer_type="RI", cbte_tipo=CBTE_TIPO_FACTURA_C))
        self.assertEqual(allowed_cbte_types_for_taxpayer("RI"), [CBTE_TIPO_FACTURA_B])

    def test_default_cbte_for_taxpayer(self):
        self.assertEqual(default_cbte_for_taxpayer("MONO"), CBTE_TIPO_FACTURA_C)
        self.assertEqual(default_cbte_for_taxpayer("RI"), CBTE_TIPO_FACTURA_B)
        self.assertEqual(default_cbte_for_taxpayer("X"), CBTE_TIPO_FACTURA_C)

    def test_taxpayer_messages(self):
        self.assertIn("solo se permite Factura C", taxpayer_type_lock_text("MONO"))
        self.assertIn("solo se permite Factura B", taxpayer_type_lock_text("RI"))
        m = taxpayer_blocked_cbte_message("MONO", CBTE_TIPO_FACTURA_B)
        self.assertIn("Factura B", m)
        self.assertIn("Monotributo", m)
        self.assertIn("Configuración > Régimen fiscal", m)


if __name__ == "__main__":
    unittest.main()

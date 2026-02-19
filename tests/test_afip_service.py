import sys
import types
import unittest
from unittest.mock import patch

# Stub mínimo de requests/urllib3 para poder importar el módulo sin deps externas.
requests_stub = types.ModuleType("requests")

class _Session:
    def mount(self, *args, **kwargs):
        return None

requests_stub.Session = _Session
requests_stub.post = lambda *args, **kwargs: None

adapters_stub = types.ModuleType("requests.adapters")
class HTTPAdapter:
    def __init__(self, *args, **kwargs):
        pass
adapters_stub.HTTPAdapter = HTTPAdapter

urllib3_pool_stub = types.ModuleType("urllib3.poolmanager")
class PoolManager:
    def __init__(self, *args, **kwargs):
        pass
urllib3_pool_stub.PoolManager = PoolManager

sys.modules.setdefault("requests", requests_stub)
sys.modules.setdefault("requests.adapters", adapters_stub)
sys.modules.setdefault("urllib3.poolmanager", urllib3_pool_stub)

from afip_service import AfipService


class AfipServiceFacturaCTest(unittest.TestCase):
    def test_emitir_factura_c_parsea_cae(self):
        svc = AfipService(
            modo="HOMO",
            pv=1,
            cuit=20123456789,
            cert_crt_path="certs/monotributo.crt",
            private_key_path="certs/clave.key",
        )

        response_xml = """
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <FECAESolicitarResponse xmlns="http://ar.gov.afip.dif.FEV1/">
      <FECAESolicitarResult>
        <FeDetResp>
          <FECAEDetResponse>
            <Resultado>A</Resultado>
            <CAE>12345678901234</CAE>
            <CAEFchVto>20301231</CAEFchVto>
          </FECAEDetResponse>
        </FeDetResp>
      </FECAESolicitarResult>
    </FECAESolicitarResponse>
  </soap:Body>
</soap:Envelope>
""".strip()

        with patch.object(svc, "_auth_xml", return_value="<Auth></Auth>"), \
             patch.object(svc, "get_next_cbte_nro", return_value=55), \
             patch.object(svc, "_soap_post_wsfe", return_value=response_xml):
            res = svc.emitir_factura_c(doc_tipo=99, doc_nro="0", total=1.0, items=[])

        self.assertEqual(res.cbte_nro, 55)
        self.assertEqual(res.cae, "12345678901234")
        self.assertEqual(res.cae_vto, "20301231")


if __name__ == "__main__":
    unittest.main()

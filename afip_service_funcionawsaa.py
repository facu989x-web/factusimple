from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import base64
import uuid
import xml.etree.ElementTree as ET
import requests

from zeep import Client
from zeep.transports import Transport

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography import x509

# Factura C (Monotributo)
CBTE_TIPO_FACTURA_C = 11

@dataclass
class AfipResult:
  cbte_nro: int
  cae: str
  cae_vto: str  # yyyymmdd

class AfipService:
  def __init__(self, *, modo: str, pv: int, cuit: int,
               cert_crt_path: str, private_key_path: str, private_key_password: str | None,
               openssl_path: str | None = None):

    self.modo = modo.upper()  # 'PROD' o 'HOMO'
    self.pv = int(pv)
    self.cuit = int(cuit)
    self.openssl_path = openssl_path    
    self.cert_crt_path = cert_crt_path
    self.private_key_path = private_key_path
    self.private_key_password = private_key_password

    if self.modo == "PROD":
      self.wsaa_url = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
      self.wsfe_wsdl = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
    else:
      self.wsaa_url = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
      self.wsfe_wsdl = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"

    # Cache TA: (token, sign, expiry_utc)
    self._ta_cache: tuple[str, str, datetime] | None = None

  # ---------------- WSAA ----------------
  def _build_ltr(self, service: str) -> bytes:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    gen = now - timedelta(minutes=5)
    exp = now + timedelta(hours=12)
    unique = int(now.timestamp())

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{unique}</uniqueId>
    <generationTime>{gen.strftime("%Y-%m-%dT%H:%M:%SZ")}</generationTime>
    <expirationTime>{exp.strftime("%Y-%m-%dT%H:%M:%SZ")}</expirationTime>
  </header>
  <service>{service}</service>
</loginTicketRequest>
"""
    return xml.encode("utf-8")

  def _load_cert_and_key(self):
    cert_pem = open(self.cert_crt_path, "rb").read()
    key_pem = open(self.private_key_path, "rb").read()

    cert = x509.load_pem_x509_certificate(cert_pem)

    password = self.private_key_password.encode("utf-8") if self.private_key_password else None
    key = serialization.load_pem_private_key(key_pem, password=password)
    return cert, key

  def _sign_cms(self, data: bytes) -> bytes:
    import subprocess, tempfile, os, shutil

    openssl = self.openssl_path or shutil.which("openssl")
    print("OPENSSL USED:", openssl)

    if not openssl:
      raise RuntimeError("No encuentro openssl. Definí openssl_path en settings.json.")

    with tempfile.TemporaryDirectory() as td:
      in_xml = os.path.join(td, "ltr.xml")
      out_der = os.path.join(td, "cms.der")
      with open(in_xml, "wb") as f:
        f.write(data)

      cmd = [
        openssl, "cms", "-sign",
        "-in", in_xml,
        "-signer", self.cert_crt_path,
        "-inkey", self.private_key_path,
        "-outform", "DER",
        "-out", out_der,
        "-nodetach",
        "-binary",
      ]

      p = subprocess.run(cmd, capture_output=True, text=True)
      if p.returncode != 0:
        raise RuntimeError("OpenSSL cms -sign falló:\n" + (p.stderr or p.stdout))

      return open(out_der, "rb").read()


  def _login_wsaa(self, service: str = "wsfe") -> tuple[str, str, datetime]:
    import html

    ltr = self._build_ltr(service)
    cms = self._sign_cms(ltr)

    cms_b64 = base64.b64encode(cms).decode("ascii")
    # wrap 76 EXACTO como el tester
    cms_b64 = "\n".join([cms_b64[i:i+76] for i in range(0, len(cms_b64), 76)])

    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
  <soapenv:Header/>
  <soapenv:Body>
    <wsaa:loginCms>
      <wsaa:in0>{cms_b64}</wsaa:in0>
    </wsaa:loginCms>
  </soapenv:Body>
</soapenv:Envelope>
"""

    headers = {"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": ""}

    r = requests.post(self.wsaa_url, data=soap.encode("utf-8"), headers=headers, timeout=30)

    # Si WSAA devuelve 500, igual queremos ver body (a veces trae fault)
    if r.status_code >= 400:
      raise RuntimeError(f"WSAA HTTP {r.status_code}\n{r.text[:2000]}")

    tree = ET.fromstring(r.content)

    ta_escaped = None
    for el in tree.iter():
      if el.tag.endswith("loginCmsReturn"):
        ta_escaped = el.text
        break
    if not ta_escaped:
      raise RuntimeError("WSAA: No pude obtener loginCmsReturn (TA)")

    ta_xml = html.unescape(ta_escaped)
    ta = ET.fromstring(ta_xml.encode("utf-8"))

    token = ta.findtext(".//token")
    sign = ta.findtext(".//sign")
    exp = ta.findtext(".//expirationTime")
    if not token or not sign or not exp:
      raise RuntimeError("WSAA: TA incompleto (token/sign/expirationTime)")

    expiry = datetime.strptime(exp[:19], "%Y-%m-%dT%H:%M:%S")
    return token, sign, expiry

  def _get_auth(self) -> dict:
    now = datetime.utcnow()
    if self._ta_cache:
      token, sign, exp = self._ta_cache
      if exp - now > timedelta(minutes=10):
        return {"Token": token, "Sign": sign, "Cuit": self.cuit}

    token, sign, exp = self._login_wsaa("wsfe")
    self._ta_cache = (token, sign, exp)
    return {"Token": token, "Sign": sign, "Cuit": self.cuit}

  # ---------------- WSFEv1 ----------------
  def _wsfe_client(self) -> Client:
    import ssl
    from urllib3.poolmanager import PoolManager
    from requests.adapters import HTTPAdapter

    class SSLAdapter(HTTPAdapter):
      def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()
        # Forzamos mínimo TLS 1.2
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        # Evita ciphers DHE débiles que disparan DH_KEY_TOO_SMALL
        # (dejamos ciphers fuertes por defecto; solo deshabilitamos DH legacy)
        try:
          ctx.set_ciphers("DEFAULT:!DH:!DHE")
        except Exception:
          pass

        self.poolmanager = PoolManager(
          num_pools=connections,
          maxsize=maxsize,
          block=block,
          ssl_context=ctx,
          **pool_kwargs
        )

    session = requests.Session()
    session.mount("https://", SSLAdapter())
    transport = Transport(session=session, timeout=30)
    return Client(wsdl=self.wsfe_wsdl, transport=transport)


  def get_next_cbte_nro(self, cbte_tipo: int = CBTE_TIPO_FACTURA_C) -> int:
    client = self._wsfe_client()
    auth = self._get_auth()
    last = client.service.FECompUltimoAutorizado(auth, self.pv, cbte_tipo)
    return int(last) + 1

  def emitir_factura_c(self, *, doc_tipo: int, doc_nro: str, total: float, items: list[dict]) -> AfipResult:
    client = self._wsfe_client()
    auth = self._get_auth()

    cbte_nro = self.get_next_cbte_nro(CBTE_TIPO_FACTURA_C)
    cbte_fch = datetime.now().strftime("%Y%m%d")

    imp_total = round(float(total), 2)

    fe_cab_req = {
      "CantReg": 1,
      "PtoVta": self.pv,
      "CbteTipo": CBTE_TIPO_FACTURA_C
    }

    # Concepto=1 (productos). Si quisieras servicios, Concepto=2 y fechas de servicio.
    fe_det = {
      "Concepto": 1,
      "DocTipo": int(doc_tipo),
      "DocNro": int(doc_nro),
      "CbteDesde": cbte_nro,
      "CbteHasta": cbte_nro,
      "CbteFch": cbte_fch,
      "ImpTotal": imp_total,
      "ImpTotConc": 0.0,
      "ImpNeto": imp_total,
      "ImpOpEx": 0.0,
      "ImpTrib": 0.0,
      "ImpIVA": 0.0,
      "MonId": "PES",
      "MonCotiz": 1.0
      # Importante: para Factura C NO informar AlicIva.
    }

    req = {
      "FeCabReq": fe_cab_req,
      "FeDetReq": {"FECAEDetRequest": [fe_det]}
    }

    resp = client.service.FECAESolicitar(auth, req)
    det_resp = resp.FeDetResp.FECAEDetResponse[0]

    if det_resp.Resultado != "A":
      obs = []
      if getattr(det_resp, "Observaciones", None) and getattr(det_resp.Observaciones, "Obs", None):
        for o in det_resp.Observaciones.Obs:
          obs.append(f"{o.Code}: {o.Msg}")
      raise RuntimeError(f"AFIP/ARCA rechazó: Resultado={det_resp.Resultado}. " + " | ".join(obs))

    cae = str(det_resp.CAE)
    cae_vto = str(det_resp.CAEFchVto)  # yyyymmdd
    return AfipResult(cbte_nro=cbte_nro, cae=cae, cae_vto=cae_vto)

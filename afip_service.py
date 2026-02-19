from __future__ import annotations

import base64
import ssl
import subprocess
import tempfile
import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

# Factura C (Monotributo)
CBTE_TIPO_FACTURA_C = 11
CBTE_TIPO_FACTURA_B = 6

@dataclass
class AfipResult:
    cbte_nro: int
    cae: str
    cae_vto: str  # yyyymmdd

class AfipLowSecSSLAdapter(HTTPAdapter):
    """
    Baja el security level a 1 para permitir DH viejo del servidor WSFE (OpenSSL 3.x lo bloquea en SECLEVEL>=2).
    Se usa SOLO montado en el session de WSFE.
    """
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx,
            **pool_kwargs
        )

class AfipService:
    def __init__(
        self,
        *,
        modo: str,
        pv: int,
        cuit: int,
        cert_crt_path: str,
        private_key_path: str,
        private_key_password: str | None = None,
        openssl_path: str | None = None,
    ):
        self.modo = (modo or "PROD").upper()  # 'PROD' o 'HOMO'
        self.pv = int(pv)
        self.cuit = int(cuit)

        self.cert_crt_path = cert_crt_path
        self.private_key_path = private_key_path
        self.private_key_password = private_key_password
        self.openssl_path = openssl_path

        if self.modo == "PROD":
            self.wsaa_url = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
        else:
            self.wsaa_url = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"

        self._ta_cache: tuple[str, str, datetime] | None = None

        # Session dedicada a WSFE con SSL "menos estricto" (solo acá)
        self._wsfe_session = requests.Session()
        self._wsfe_session.mount("https://", AfipLowSecSSLAdapter())

    # ---------------- WSAA ----------------
    def _build_ltr(self, service: str) -> bytes:
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

    def _sign_cms(self, data: bytes) -> bytes:
        openssl = self.openssl_path or shutil.which("openssl")
        if not openssl:
            raise RuntimeError(
                "No encuentro 'openssl' en PATH. Instalá OpenSSL y/o poné 'openssl_path' en settings."
            )

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
            # password de key (si aplica) -> -passin
            if self.private_key_password:
                cmd.extend(["-passin", f"pass:{self.private_key_password}"])

            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError("OpenSSL cms -sign falló:\n" + (p.stderr or p.stdout))

            return open(out_der, "rb").read()

    def _login_wsaa(self, service: str = "wsfe") -> tuple[str, str, datetime]:
        import html

        ltr = self._build_ltr(service)
        cms = self._sign_cms(ltr)
        cms_b64 = base64.b64encode(cms).decode("ascii")
        # wrap 76 (Axis viejo lo agradece)
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

    # ---------------- WSFEv1 (SOAP manual) ----------------
    def _wsfe_url(self) -> str:
        if self.modo == "PROD":
            return "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
        else:
            return "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"

    def _soap_post_wsfe(self, action: str, body_xml: str) -> str:
        url = self._wsfe_url()
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    {body_xml}
  </soap:Body>
</soap:Envelope>
"""
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": action,
        }
        r = self._wsfe_session.post(url, data=envelope.encode("utf-8"), headers=headers, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"WSFE HTTP {r.status_code}\n{r.text[:2000]}")
        return r.text

    def _auth_xml(self) -> str:
        auth = self._get_auth()
        return f"""
<Auth>
  <Token>{auth['Token']}</Token>
  <Sign>{auth['Sign']}</Sign>
  <Cuit>{auth['Cuit']}</Cuit>
</Auth>
""".strip()

    def get_next_cbte_nro(self, cbte_tipo: int = CBTE_TIPO_FACTURA_C) -> int:
        auth_xml = self._auth_xml()
        body = f"""
<FECompUltimoAutorizado xmlns="http://ar.gov.afip.dif.FEV1/">
  {auth_xml}
  <PtoVta>{self.pv}</PtoVta>
  <CbteTipo>{int(cbte_tipo)}</CbteTipo>
</FECompUltimoAutorizado>
""".strip()

        resp_xml = self._soap_post_wsfe("http://ar.gov.afip.dif.FEV1/FECompUltimoAutorizado", body)
        tree = ET.fromstring(resp_xml.encode("utf-8"))

        last = None
        for el in tree.iter():
            if el.tag.endswith("CbteNro"):
                # ojo: hay varios CbteNro en otras respuestas; en este método es el correcto
                last = el.text
        if last is None:
            raise RuntimeError("WSFE: no encontré CbteNro en respuesta (FECompUltimoAutorizado).")
        return int(last) + 1
    def emitir_comprobante(self, *, cbte_tipo: int, doc_tipo: int, doc_nro: str,
                         total: float, items: list[dict]) -> AfipResult:
        auth_xml = self._auth_xml()

        cbte_tipo = int(cbte_tipo)
        cbte_nro = self.get_next_cbte_nro(cbte_tipo)
        cbte_fch = datetime.now().strftime("%Y%m%d")
        imp_total = round(float(total), 2)

        # Concepto 1 = Productos/Servicios (en retail suele ir 1)
        concepto = 1

        # Factura C: sin IVA
        if cbte_tipo == CBTE_TIPO_FACTURA_C:
          imp_neto = imp_total
          imp_iva = 0.00
          iva_block = ""  # no enviar AlicIva

        # Factura B: IVA incluido (21% fijo)
        elif cbte_tipo == CBTE_TIPO_FACTURA_B:
          rate = 0.21
          imp_neto = round(imp_total / (1.0 + rate), 2)
          imp_iva = round(imp_total - imp_neto, 2)

          # Ajuste por redondeo para que imp_neto + imp_iva == imp_total
          diff = round(imp_total - (imp_neto + imp_iva), 2)
          if diff != 0:
            imp_neto = round(imp_neto + diff, 2)

          # Id IVA 21% = 5
          iva_block = f"""
        <Iva>
        <AlicIva>
        <Id>5</Id>
        <BaseImp>{imp_neto:.2f}</BaseImp>
        <Importe>{imp_iva:.2f}</Importe>
        </AlicIva>
        </Iva>
        """.strip()

        else:
          raise RuntimeError(f"CbteTipo no soportado en este fork: {cbte_tipo}")

        body = f"""
        <FECAESolicitar xmlns="http://ar.gov.afip.dif.FEV1/">
        {auth_xml}
        <FeCAEReq>
        <FeCabReq>
          <CantReg>1</CantReg>
          <PtoVta>{self.pv}</PtoVta>
          <CbteTipo>{cbte_tipo}</CbteTipo>
        </FeCabReq>
        <FeDetReq>
          <FECAEDetRequest>
            <Concepto>{concepto}</Concepto>
            <DocTipo>{int(doc_tipo)}</DocTipo>
            <DocNro>{int(doc_nro)}</DocNro>
            <CbteDesde>{cbte_nro}</CbteDesde>
            <CbteHasta>{cbte_nro}</CbteHasta>
            <CbteFch>{cbte_fch}</CbteFch>

            <ImpTotal>{imp_total:.2f}</ImpTotal>
            <ImpTotConc>0.00</ImpTotConc>
            <ImpNeto>{imp_neto:.2f}</ImpNeto>
            <ImpOpEx>0.00</ImpOpEx>
            <ImpIVA>{imp_iva:.2f}</ImpIVA>
            <ImpTrib>0.00</ImpTrib>

            <MonId>PES</MonId>
            <MonCotiz>1.0000</MonCotiz>

            {iva_block}
          </FECAEDetRequest>
        </FeDetReq>
        </FeCAEReq>
        </FECAESolicitar>
        """.strip()

        resp_xml = self._soap_post_wsfe("http://ar.gov.afip.dif.FEV1/FECAESolicitar", body)

        # parse de respuesta (tu código actual)
        tree = ET.fromstring(resp_xml.encode("utf-8"))

        resultado = None
        cae = None
        cae_vto = None
        obs_msgs = []

        for el in tree.iter():
          if el.tag.endswith("Resultado") and resultado is None:
            resultado = (el.text or "").strip()
          if el.tag.endswith("CAE") and cae is None:
            cae = (el.text or "").strip()
          if el.tag.endswith("CAEFchVto") and cae_vto is None:
            cae_vto = (el.text or "").strip()

        code = None
        msg = None
        for el in tree.iter():
          if el.tag.endswith("Code"):
            code = (el.text or "").strip()
          if el.tag.endswith("Msg"):
            msg = (el.text or "").strip()
            if code or msg:
              obs_msgs.append(f"{code}: {msg}".strip(": "))

        if resultado != "A":
          extra = " | ".join(obs_msgs) if obs_msgs else resp_xml[:800]
          raise RuntimeError(f"WSFE rechazó. Resultado={resultado}. {extra}")

        if not cae or not cae_vto:
          raise RuntimeError("WSFE aprobó pero no encontré CAE/CAEFchVto.")

        return AfipResult(cbte_nro=cbte_nro, cae=cae, cae_vto=cae_vto)

    def emitir_factura_c(self, *, doc_tipo: int, doc_nro: str, total: float, items: list[dict]) -> AfipResult:
        auth_xml = self._auth_xml()

        cbte_nro = self.get_next_cbte_nro(CBTE_TIPO_FACTURA_C)
        cbte_fch = datetime.now().strftime("%Y%m%d")
        imp_total = round(float(total), 2)

        body = f"""
<FECAESolicitar xmlns="http://ar.gov.afip.dif.FEV1/">
  {auth_xml}
  <FeCAEReq>
    <FeCabReq>
      <CantReg>1</CantReg>
      <PtoVta>{self.pv}</PtoVta>
      <CbteTipo>{CBTE_TIPO_FACTURA_C}</CbteTipo>
    </FeCabReq>
    <FeDetReq>
      <FECAEDetRequest>
        <Concepto>1</Concepto>
        <DocTipo>{int(doc_tipo)}</DocTipo>
        <DocNro>{int(doc_nro)}</DocNro>
        <CbteDesde>{cbte_nro}</CbteDesde>
        <CbteHasta>{cbte_nro}</CbteHasta>
        <CbteFch>{cbte_fch}</CbteFch>

        <ImpTotal>{imp_total:.2f}</ImpTotal>
        <ImpTotConc>0.00</ImpTotConc>
        <ImpNeto>{imp_total:.2f}</ImpNeto>
        <ImpOpEx>0.00</ImpOpEx>
        <ImpIVA>0.00</ImpIVA>
        <ImpTrib>0.00</ImpTrib>

        <MonId>PES</MonId>
        <MonCotiz>1.0000</MonCotiz>
      </FECAEDetRequest>
    </FeDetReq>
  </FeCAEReq>
</FECAESolicitar>
""".strip()

        resp_xml = self._soap_post_wsfe("http://ar.gov.afip.dif.FEV1/FECAESolicitar", body)
        tree = ET.fromstring(resp_xml.encode("utf-8"))

        resultado = None
        cae = None
        cae_vto = None
        obs_msgs = []

        for el in tree.iter():
            if el.tag.endswith("Resultado") and resultado is None:
                resultado = (el.text or "").strip()
            if el.tag.endswith("CAE") and cae is None:
                cae = (el.text or "").strip()
            if el.tag.endswith("CAEFchVto") and cae_vto is None:
                cae_vto = (el.text or "").strip()

        code = None
        msg = None
        for el in tree.iter():
            if el.tag.endswith("Code"):
                code = (el.text or "").strip()
            if el.tag.endswith("Msg"):
                msg = (el.text or "").strip()
                if code or msg:
                    obs_msgs.append(f"{code}: {msg}".strip(": "))

        if resultado != "A":
            extra = " | ".join(obs_msgs) if obs_msgs else resp_xml[:800]
            raise RuntimeError(f"WSFE rechazó. Resultado={resultado}. {extra}")

        if not cae or not cae_vto:
            raise RuntimeError("WSFE aprobó pero no encontré CAE/CAEFchVto en respuesta.")

        return AfipResult(cbte_nro=cbte_nro, cae=cae, cae_vto=cae_vto)

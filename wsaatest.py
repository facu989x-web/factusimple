import base64
import os
import subprocess
import tempfile
import textwrap
from datetime import datetime, timedelta, timezone

import requests

WSAA_PROD = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
WSAA_HOMO = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"

def build_ltr(service: str) -> bytes:
    # UTC explícito con Z
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

def sign_cms_openssl(ltr_xml: bytes, cert_path: str, key_path: str) -> bytes:
    # CMS attached DER, igual a manual de AFIP/ARCA (openssl cms -sign -nodetach -binary -outform DER)
    with tempfile.TemporaryDirectory() as td:
        in_xml = os.path.join(td, "ltr.xml")
        out_der = os.path.join(td, "cms.der")
        with open(in_xml, "wb") as f:
            f.write(ltr_xml)

        cmd = [
            "openssl", "cms", "-sign",
            "-in", in_xml,
            "-signer", cert_path,
            "-inkey", key_path,
            "-outform", "DER",
            "-out", out_der,
            "-nodetach",
            "-binary",
        ]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("OpenSSL falló:\n" + (p.stderr or p.stdout))
        return open(out_der, "rb").read()

def wrap_b64(s: str, width: int = 76) -> str:
    # A Axis le cae bien con saltos de línea “tipo PEM”
    return "\n".join(textwrap.wrap(s, width))

def post_wsaa(url: str, cms_b64: str, variant: str):
    # SOAP envelope EXACTO al manual (namespace wsaa.view... y tag wsaa:in0)
    soap_11 = f"""<?xml version="1.0" encoding="UTF-8"?>
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

    # SOAP 1.2 (por si tu infra/requests negocia mejor así)
    soap_12 = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope"
                 xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
  <soap12:Header/>
  <soap12:Body>
    <wsaa:loginCms>
      <wsaa:in0>{cms_b64}</wsaa:in0>
    </wsaa:loginCms>
  </soap12:Body>
</soap12:Envelope>
"""

    if variant == "soap11_action_empty":
        headers = {"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": ""}
        data = soap_11.encode("utf-8")
    elif variant == "soap11_action_urn":
        # el manual muestra urn:LoginCms
        headers = {"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": "urn:LoginCms"}
        data = soap_11.encode("utf-8")
    elif variant == "soap12":
        # en WSDL el soapAction está vacío (binding Axis), en SOAP 1.2 va como action opcional
        headers = {"Content-Type": 'application/soap+xml; charset=UTF-8; action="loginCms"'}
        data = soap_12.encode("utf-8")
    else:
        raise ValueError("variant inválida")

    r = requests.post(url, data=data, headers=headers, timeout=30)
    return r.status_code, r.text

def main():
    cert = r"C:\facturasimple\certs\monotributo.crt"
    key  = r"C:\facturasimple\certs\clave.key"

    # Cambiá esto si querés probar HOMO (ojo: cert de PROD en HOMO suele fallar)
    url = WSAA_PROD
    service = "wsfe"

    # Check rápido de hora local/UTC
    now_local = datetime.now()
    now_utc = datetime.now(timezone.utc)
    print("Hora local:", now_local.isoformat(timespec="seconds"))
    print("Hora UTC  :", now_utc.isoformat(timespec="seconds"))

    ltr = build_ltr(service)
    cms_der = sign_cms_openssl(ltr, cert, key)
    cms_b64 = base64.b64encode(cms_der).decode("ascii")
    cms_b64_wrapped = wrap_b64(cms_b64, 76)

    for variant in ["soap11_action_empty", "soap11_action_urn", "soap12"]:
        print("\n==============================")
        print("VARIANT:", variant)
        try:
            code, body = post_wsaa(url, cms_b64_wrapped, variant)
            print("HTTP:", code)
            print(body[:1500])
        except Exception as e:
            print("EXC:", repr(e))

if __name__ == "__main__":
    main()

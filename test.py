import json
from afip_service import AfipService

cfg = json.load(open("settings.json", "r", encoding="utf-8"))

svc = AfipService(
    modo=cfg["modo"],
    pv=cfg["punto_venta"],
    cuit=int(cfg["cuit_emisor"]),
    cert_crt_path=cfg["cert_crt_path"],
    private_key_path=cfg["private_key_path"],
    private_key_password=cfg.get("private_key_password"),
    openssl_path=cfg.get("openssl_path"),
)

print("Probando WSAA...")
token, sign, exp = svc._login_wsaa("wsfe")
print("OK WSAA")
print("Token len:", len(token))
print("Sign len :", len(sign))
print("Exp      :", exp)

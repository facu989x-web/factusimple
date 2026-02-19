import json
from afip_service import AfipService

cfg = json.load(open("settings.json","r",encoding="utf-8"))

svc = AfipService(
    modo=cfg["modo"],
    pv=cfg["punto_venta"],
    cuit=int(cfg["cuit_emisor"]),
    cert_crt_path=cfg["cert_crt_path"],
    private_key_path=cfg["private_key_path"],
    private_key_password=cfg.get("private_key_password"),
    openssl_path=cfg.get("openssl_path"),
)

print("WSAA OK -> probando WSFE...")
nxt = svc.get_next_cbte_nro()
print("Siguiente comprobante:", nxt)

print("Pidiendo CAE por $1...")
res = svc.emitir_factura_c(
    doc_tipo=99,
    doc_nro="0",
    total=1.00,
    items=[{"name":"PRUEBA","qty":1,"price":1,"subtotal":1}],
)
print("APROBADO:", res.cbte_nro, res.cae, res.cae_vto)

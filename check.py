# check_cert_key.py
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import sys
from pathlib import Path

def load_cert(cert_path: Path) -> x509.Certificate:
    data = cert_path.read_bytes()
    try:
        return x509.load_pem_x509_certificate(data)
    except ValueError:
        # a veces viene DER
        return x509.load_der_x509_certificate(data)

def load_key(key_path: Path, password: str | None):
    data = key_path.read_bytes()
    pw = password.encode("utf-8") if password else None
    try:
        return serialization.load_pem_private_key(data, password=pw)
    except ValueError:
        # a veces viene DER
        return serialization.load_der_private_key(data, password=pw)

def pubkey_fingerprint(pub) -> str:
    # fingerprint estable de la public key (DER) para comparar
    der = pub.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    h = hashes.Hash(hashes.SHA256())
    h.update(der)
    return h.finalize().hex()

def main():
    if len(sys.argv) < 3:
        print("Uso: py check_cert_key.py certs/certificado.crt certs/privada.key [password_opcional]")
        sys.exit(1)

    cert_path = Path(sys.argv[1])
    key_path = Path(sys.argv[2])
    password = sys.argv[3] if len(sys.argv) >= 4 else None

    print(f"Cert: {cert_path.resolve()}")
    print(f"Key : {key_path.resolve()}")

    # Cargar cert
    try:
        cert = load_cert(cert_path)
    except Exception as e:
        print("\n[ERROR] No pude cargar el certificado (.crt).")
        print(e)
        sys.exit(2)

    # Cargar key
    try:
        key = load_key(key_path, password)
    except TypeError:
        print("\n[ERROR] La key está encriptada y no pasaste password.")
        sys.exit(3)
    except Exception as e:
        print("\n[ERROR] No pude cargar la private key (.key).")
        print(e)
        sys.exit(4)

    # Info cert
    print("\n--- CERT INFO ---")
    print("Subject :", cert.subject.rfc4514_string())
    print("Issuer  :", cert.issuer.rfc4514_string())
    print("NotBefore:", cert.not_valid_before)
    print("NotAfter :", cert.not_valid_after)
    print("Serial  :", hex(cert.serial_number))
    print("SHA1 FP :", cert.fingerprint(hashes.SHA1()).hex())
    print("SHA256FP:", cert.fingerprint(hashes.SHA256()).hex())

    # Comparar public keys
    cert_pub = cert.public_key()
    key_pub = key.public_key()

    cert_fp = pubkey_fingerprint(cert_pub)
    key_fp = pubkey_fingerprint(key_pub)

    print("\n--- KEY INFO ---")
    if isinstance(key_pub, rsa.RSAPublicKey):
        print("Key type: RSA")
        print("Key size:", key_pub.key_size)
    elif isinstance(key_pub, ec.EllipticCurvePublicKey):
        print("Key type: EC")
        print("Curve   :", key_pub.curve.name)
    else:
        print("Key type:", type(key_pub))

    print("\n--- MATCH CHECK ---")
    print("Cert pubkey SHA256:", cert_fp)
    print("Key  pubkey SHA256:", key_fp)

    if cert_fp == key_fp:
        print("\n✅ OK: El .crt y el .key SON pareja (misma clave pública).")
    else:
        print("\n❌ MAL: El .crt y el .key NO coinciden (no son pareja).")

if __name__ == "__main__":
    main()

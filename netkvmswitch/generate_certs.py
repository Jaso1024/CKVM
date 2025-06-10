from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import datetime
import os

# Define paths
CERTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'certs')

# Ensure certs directory exists
if not os.path.exists(CERTS_DIR):
    os.makedirs(CERTS_DIR)

# Helper function to generate a private key
def generate_private_key(filename):
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    with open(os.path.join(CERTS_DIR, filename), "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    return key

# Helper function to generate a self-signed CA certificate
def generate_ca_certificate(key, filename, common_name="CKVM_CA"):
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, key_encipherment=False, data_encipherment=False, key_agreement=False, content_commitment=False, encipher_only=False, decipher_only=False), critical=True
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
    )
    certificate = builder.sign(key, hashes.SHA256())
    with open(os.path.join(CERTS_DIR, filename), "wb") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM))
    return certificate

# Helper function to generate a certificate signed by a CA
def generate_signed_certificate(subject_common_name, filename_key, filename_crt, ca_key, ca_cert):
    key = generate_private_key(filename_key)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, subject_common_name),
    ])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject) # Issuer is the CA
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
             x509.KeyUsage(digital_signature=True, key_encipherment=True, data_encipherment=False, key_agreement=False, content_commitment=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()), critical=False
        )
        # Add Subject Alternative Name (SAN) for server if needed, e.g., for hostname verification
        # .add_extension(
        #    x509.SubjectAlternativeName([x509.DNSName(u"localhost")]), critical=False
        # )
    )
    certificate = builder.sign(ca_key, hashes.SHA256())
    with open(os.path.join(CERTS_DIR, filename_crt), "wb") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM))
    return key, certificate

if __name__ == "__main__":
    print("Generating CA certificate...")
    ca_key = generate_private_key("ca.key")
    ca_cert = generate_ca_certificate(ca_key, "ca.crt")
    print(f"CA Key: {os.path.join(CERTS_DIR, 'ca.key')}")
    print(f"CA Cert: {os.path.join(CERTS_DIR, 'ca.crt')}")

    print("\nGenerating Server certificate...")
    server_key, server_cert = generate_signed_certificate(
        "NetKVMSwitch Server", "server.key", "server.crt", ca_key, ca_cert
    )
    print(f"Server Key: {os.path.join(CERTS_DIR, 'server.key')}")
    print(f"Server Cert: {os.path.join(CERTS_DIR, 'server.crt')}")

    print("\nGenerating Client certificate...")
    client_key, client_cert = generate_signed_certificate(
        "NetKVMSwitch Client", "client.key", "client.crt", ca_key, ca_cert
    )
    print(f"Client Key: {os.path.join(CERTS_DIR, 'client.key')}")
    print(f"Client Cert: {os.path.join(CERTS_DIR, 'client.crt')}")

    print("\nCertificate generation complete.")
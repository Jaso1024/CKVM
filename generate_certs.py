#!/usr/bin/env python3
"""
Generate self-signed certificates for NetKVMSwitch testing
"""

import os
import sys
import ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime

def generate_ca():
    """Generate CA certificate and key"""
    # Generate private key
    ca_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    # Generate certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Test"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NetKVMSwitch"),
        x509.NameAttribute(NameOID.COMMON_NAME, "NetKVMSwitch-CA"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        ca_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        datetime.datetime.utcnow() + datetime.timedelta(days=365)
    ).add_extension(
        x509.BasicConstraints(ca=True, path_length=None),
        critical=True,
    ).sign(ca_key, hashes.SHA256())
    
    return ca_key, cert

def generate_server_cert(ca_key, ca_cert):
    """Generate server certificate signed by CA"""
    # Generate private key
    server_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    # Generate certificate
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Test"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NetKVMSwitch"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        ca_cert.subject
    ).public_key(
        server_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        datetime.datetime.utcnow() + datetime.timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]),
        critical=False,
    ).sign(ca_key, hashes.SHA256())
    
    return server_key, cert

def generate_client_cert(ca_key, ca_cert):
    """Generate client certificate signed by CA"""
    # Generate private key
    client_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    # Generate certificate
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Test"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NetKVMSwitch"),
        x509.NameAttribute(NameOID.COMMON_NAME, "client"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        ca_cert.subject
    ).public_key(
        client_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        datetime.datetime.utcnow() + datetime.timedelta(days=365)
    ).sign(ca_key, hashes.SHA256())
    
    return client_key, cert

def main():
    
    # Create certs directory if it doesn't exist
    os.makedirs('certs', exist_ok=True)
    
    print("Generating CA certificate...")
    ca_key, ca_cert = generate_ca()
    
    print("Generating server certificate...")
    server_key, server_cert = generate_server_cert(ca_key, ca_cert)
    
    print("Generating client certificate...")
    client_key, client_cert = generate_client_cert(ca_key, ca_cert)
    
    # Write CA files
    with open('certs/ca.key', 'wb') as f:
        f.write(ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    with open('certs/ca.crt', 'wb') as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    
    # Write server files
    with open('certs/server.key', 'wb') as f:
        f.write(server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    with open('certs/server.crt', 'wb') as f:
        f.write(server_cert.public_bytes(serialization.Encoding.PEM))
    
    # Write client files
    with open('certs/client.key', 'wb') as f:
        f.write(client_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    with open('certs/client.crt', 'wb') as f:
        f.write(client_cert.public_bytes(serialization.Encoding.PEM))
    
    print("Certificates generated successfully!")
    print("Files created:")
    print("  certs/ca.crt")
    print("  certs/ca.key") 
    print("  certs/server.crt")
    print("  certs/server.key")
    print("  certs/client.crt")
    print("  certs/client.key")

if __name__ == "__main__":
    main() 
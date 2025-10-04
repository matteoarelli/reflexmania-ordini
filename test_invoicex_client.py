import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clients.invoicex_api import InvoiceXAPIClient
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

print("=" * 70)
print("TEST INVOICEX API CLIENT - VERSIONE CORRETTA")
print("=" * 70)

# Inizializza client
client = InvoiceXAPIClient(
    base_url='https://api.reflexmania.it/',
    api_key='52bf3c1f206dae8e45bf647cda396172'
)

# Test 1: Health Check
print("\n[1] Health Check...")
if client.health_check():
    print("✓ API raggiungibile\n")
else:
    print("✗ API non raggiungibile")
    sys.exit(1)

# Test 2: Cerca cliente esistente
print("[2] Test cerca cliente esistente...")
email_test = 'info@reflexmania.it'
esiste = client.cerca_cliente_per_email(email_test)
print(f"Cliente '{email_test}' esiste: {esiste}")

if esiste:
    codice = client.get_codice_cliente(email_test)
    print(f"Codice cliente: {codice}\n")

print("\n" + "=" * 70)
print("✓ TEST COMPLETATI")
print("=" * 70)
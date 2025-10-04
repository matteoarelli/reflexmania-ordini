"""
Test connessione API InvoiceX
Salva come: test_api.py
Esegui: python test_api.py
"""

import requests
import sys

print("=" * 60)
print("TEST API INVOICEX")
print("=" * 60)

BASE_URL = 'https://api.reflexmania.it'
API_KEY = '52bf3c1f206dae8e45bf647cda396172'

# Test 1: Endpoint cercapermail
print("\n[1] Test cercapermail...")
try:
    response = requests.get(
        f'{BASE_URL}/cercapermail',
        params={'email': 'info@reflexmania.it'},
        headers={'Apikey': API_KEY},
        timeout=10
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        print("✓ API raggiungibile!")
    else:
        print("✗ Status code inatteso")
        
except Exception as e:
    print(f"✗ Errore: {e}")
    sys.exit(1)

# Test 2: Endpoint getCodiceDaEmail
print("\n[2] Test getCodiceDaEmail...")
try:
    response = requests.get(
        f'{BASE_URL}/getCodiceDaEmail',
        params={'email': 'info@reflexmania.it'},
        headers={'Apikey': API_KEY},
        timeout=10
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"✗ Errore: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETATO")
print("=" * 60)

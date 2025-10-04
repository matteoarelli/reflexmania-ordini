"""
Debug dettagliato connessione API
"""

import requests
import sys

BASE_URL = 'https://api.reflexmania.it'
API_KEY = '52bf3c1f206dae8e45bf647cda396172'

print("=" * 70)
print("DEBUG API INVOICEX")
print("=" * 70)

# Test 1: Endpoint cercapermail (come health check)
print("\n[Test 1] Endpoint cercapermail...")
try:
    response = requests.get(
        f'{BASE_URL}/cercapermail',
        params={'email': 'test@healthcheck.com'},
        headers={'Apikey': API_KEY},
        timeout=10
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response Length: {len(response.text)} bytes")
    print(f"Response Preview: {response.text[:200]}")
    
    if response.status_code == 200:
        print("✓ Endpoint risponde correttamente")
    else:
        print(f"✗ Status code inatteso: {response.status_code}")
        
except requests.exceptions.Timeout:
    print("✗ TIMEOUT - Server non risponde entro 10s")
except requests.exceptions.ConnectionError as e:
    print(f"✗ CONNECTION ERROR: {e}")
except Exception as e:
    print(f"✗ ERRORE: {type(e).__name__}: {e}")

# Test 2: Endpoint con email reale
print("\n[Test 2] Cerca cliente reale...")
try:
    response = requests.get(
        f'{BASE_URL}/cercapermail',
        params={'email': 'info@reflexmania.it'},
        headers={'Apikey': API_KEY},
        timeout=10
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: '{response.text}'")
    
    if response.text.strip().lower() == 'true':
        print("✓ Cliente trovato!")
        
        # Test 3: Get codice
        print("\n[Test 3] Recupera codice cliente...")
        response2 = requests.get(
            f'{BASE_URL}/getCodiceDaEmail',
            params={'email': 'info@reflexmania.it'},
            headers={'Apikey': API_KEY},
            timeout=10
        )
        print(f"Status Code: {response2.status_code}")
        print(f"Codice Cliente: '{response2.text}'")
    else:
        print(f"Cliente non trovato (response: '{response.text}')")
        
except Exception as e:
    print(f"✗ ERRORE: {type(e).__name__}: {e}")

# Test 4: Verifica SSL
print("\n[Test 4] Verifica SSL...")
try:
    response = requests.get(BASE_URL, timeout=5, verify=True)
    print("✓ Certificato SSL valido")
except requests.exceptions.SSLError:
    print("✗ Problema con certificato SSL")
    print("  Prova con verify=False (solo per test)")

# Test 5: DNS Resolution
print("\n[Test 5] DNS Resolution...")
try:
    import socket
    ip = socket.gethostbyname('api.reflexmania.it')
    print(f"✓ DNS risolve a: {ip}")
except socket.gaierror:
    print("✗ Impossibile risolvere DNS per api.reflexmania.it")

print("\n" + "=" * 70)
print("DEBUG COMPLETATO")
print("=" * 70)

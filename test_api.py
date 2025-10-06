#!/usr/bin/env python3
"""
Test endpoint InvoiceX per verifica supporto metodo_pagamento
"""
import requests
import json

# Configurazione
API_URL = 'https://api.reflexmania.it'
API_KEY = '52bf3c1f206dae8e45bf647cda396172'
CODICE_CLIENTE_TEST = 'TEST123'

def test_crea_ddt_con_pagamento():
    """
    Test creazione DDT con metodo_pagamento nel payload
    """
    url = f"{API_URL}/crea-ddt-vendita-codice/{CODICE_CLIENTE_TEST}"
    
    headers = {
        'Apikey': API_KEY,
        'Content-Type': 'application/json'
    }
    
    # Payload CON metodo_pagamento
    payload = {
        'riferimento': 'TEST-PAYMENT-001',
        'metodo_pagamento': 'BACKMARKET'
    }
    
    print("=" * 60)
    print("TEST: Creazione DDT con metodo_pagamento")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("-" * 60)
    
    try:
        # Usa requests.request per forzare GET con body JSON
        response = requests.request(
            'GET',
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")
        print("-" * 60)
        
        if response.status_code == 200:
            print("✅ SUCCESSO: API ha accettato la richiesta")
            print(f"   DDT ID ritornato: {response.text.strip()}")
            
            # Verifica se è un numero (ID valido)
            ddt_id = response.text.strip()
            if ddt_id.isdigit():
                print("✅ DDT creato con successo!")
                return True
            else:
                print("⚠️  ATTENZIONE: Risposta non è un ID numerico")
                return False
        else:
            print(f"❌ ERRORE: API ha ritornato status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ ERRORE CONNESSIONE: {e}")
        return False


def test_crea_ddt_senza_pagamento():
    """
    Test creazione DDT SENZA metodo_pagamento (per confronto)
    """
    url = f"{API_URL}/crea-ddt-vendita-codice/{CODICE_CLIENTE_TEST}"
    
    headers = {
        'Apikey': API_KEY,
        'Content-Type': 'application/json'
    }
    
    # Payload SENZA metodo_pagamento
    payload = {
        'riferimento': 'TEST-NO-PAYMENT-001'
    }
    
    print("\n" + "=" * 60)
    print("TEST: Creazione DDT SENZA metodo_pagamento (controllo)")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("-" * 60)
    
    try:
        response = requests.request(
            'GET',
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        print("-" * 60)
        
        if response.status_code == 200:
            print("✅ SUCCESSO: API ha accettato la richiesta")
            return True
        else:
            print(f"⚠️  API ha ritornato status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ ERRORE: {e}")
        return False


if __name__ == "__main__":
    print("\n🧪 TEST API INVOICEX - SUPPORTO METODO_PAGAMENTO\n")
    
    # Test 1: Con metodo_pagamento
    result1 = test_crea_ddt_con_pagamento()
    
    # Test 2: Senza metodo_pagamento (per confronto)
    result2 = test_crea_ddt_senza_pagamento()
    
    # Riepilogo
    print("\n" + "=" * 60)
    print("RIEPILOGO TEST")
    print("=" * 60)
    print(f"Test con metodo_pagamento:    {'✅ OK' if result1 else '❌ FAIL'}")
    print(f"Test senza metodo_pagamento:  {'✅ OK' if result2 else '❌ FAIL'}")
    print("=" * 60)
    
    if result1:
        print("\n✅ RISULTATO: L'API supporta il campo metodo_pagamento!")
        print("   → Puoi procedere con il deploy dei file aggiornati")
    elif result2:
        print("\n⚠️  RISULTATO: L'API ignora il campo metodo_pagamento")
        print("   → Il campo non causa errori ma probabilmente viene ignorato")
        print("   → Serve verificare nel database InvoiceX se viene salvato")
    else:
        print("\n❌ RISULTATO: Problemi di connessione o cliente TEST123 inesistente")
        print("   → Riprova con un codice cliente valido")

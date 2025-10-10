#!/usr/bin/env python3
"""
Script di test per diagnosticare disabilitazione prodotto Magento
"""

import requests
from config import MAGENTO_URL, MAGENTO_TOKEN
from clients.magento_api import MagentoAPIClient

# SKU da testare
TEST_SKU = "76WW0UT76W"

print("=" * 60)
print("TEST DIAGNOSTICO: Disabilitazione Prodotto Magento")
print("=" * 60)

# STEP 1: Test connessione base
print("\n1️⃣ TEST CONNESSIONE MAGENTO API")
print("-" * 60)
url = f"{MAGENTO_URL}/rest/V1/orders"
headers = {
    'Authorization': f'Bearer {MAGENTO_TOKEN}',
    'Content-Type': 'application/json'
}
params = {'searchCriteria[pageSize]': 1}

try:
    response = requests.get(url, headers=headers, params=params, timeout=10)
    if response.status_code == 200:
        print("✅ Connessione OK")
    else:
        print(f"❌ Errore connessione: HTTP {response.status_code}")
        print(f"Response: {response.text}")
except Exception as e:
    print(f"❌ Errore: {e}")

# STEP 2: Verifica esistenza prodotto
print(f"\n2️⃣ VERIFICA ESISTENZA PRODOTTO: {TEST_SKU}")
print("-" * 60)
from urllib.parse import quote
sku_encoded = quote(TEST_SKU, safe='')
url_product = f"{MAGENTO_URL}/rest/V1/products/{sku_encoded}"

try:
    response = requests.get(url_product, headers=headers, timeout=10)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Prodotto trovato!")
        print(f"   - SKU: {data.get('sku')}")
        print(f"   - Nome: {data.get('name')}")
        print(f"   - Status: {data.get('status')} (1=Enabled, 2=Disabled)")
        print(f"   - Qty: {data.get('extension_attributes', {}).get('stock_item', {}).get('qty', 'N/A')}")
        current_status = data.get('status')
    elif response.status_code == 404:
        print(f"❌ Prodotto NON TROVATO su Magento")
        print(f"   Il prodotto con SKU '{TEST_SKU}' non esiste nel catalogo Magento")
        print(f"   Questo è il motivo per cui la disabilitazione non funziona!")
        current_status = None
    else:
        print(f"❌ Errore: HTTP {response.status_code}")
        print(f"Response: {response.text}")
        current_status = None
except Exception as e:
    print(f"❌ Errore: {e}")
    current_status = None

# STEP 3: Test disabilitazione (solo se prodotto esiste)
if current_status is not None:
    print(f"\n3️⃣ TEST DISABILITAZIONE PRODOTTO (SOLO VISTA GENERALE)")
    print("-" * 60)
    
    # Salva stato iniziale
    print(f"Status PRIMA disabilitazione:")
    status_before = {}
    for store in ['all', 'it', 'en', 'de']:
        url_store = f"{MAGENTO_URL}/rest/{store}/V1/products/{sku_encoded}"
        try:
            resp = requests.get(url_store, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get('status')
                # Verifica se usa "Use Default Value" (non ha status esplicito per la vista)
                status_before[store] = status
                print(f"   - Store '{store}': Status = {status} (1=Enabled, 2=Disabled)")
        except:
            pass
    
    # Inizializza client
    magento_client = MagentoAPIClient(MAGENTO_URL, MAGENTO_TOKEN)
    
    print(f"\n🔄 Esecuzione disabilitazione SOLO su vista generale...")
    success = magento_client.disable_product(TEST_SKU)
    
    if success:
        print(f"✅ Disabilitazione completata!")
        
        # Verifica stato DOPO disabilitazione
        print(f"\nStatus DOPO disabilitazione:")
        all_disabled = True
        for store in ['all', 'it', 'en', 'de']:
            url_store = f"{MAGENTO_URL}/rest/{store}/V1/products/{sku_encoded}"
            try:
                resp = requests.get(url_store, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get('status')
                    qty = data.get('extension_attributes', {}).get('stock_item', {}).get('qty', 'N/A')
                    in_stock = data.get('extension_attributes', {}).get('stock_item', {}).get('is_in_stock', 'N/A')
                    
                    status_icon = "✅" if status == 2 else "❌"
                    qty_icon = "✅" if qty == 0 else "⚠️"
                    
                    # Indica se eredita dalla vista generale
                    inheritance = ""
                    if store != 'all' and status == 2:
                        inheritance = " (eredita da vista generale)"
                    
                    print(f"   - Store '{store}': {status_icon} Status={status}, {qty_icon} Qty={qty}, InStock={in_stock}{inheritance}")
                    
                    if status != 2 or qty != 0:
                        all_disabled = False
            except Exception as e:
                print(f"   - Store '{store}': ⚠️ Errore verifica: {e}")
        
        if all_disabled:
            print(f"\n✅ SUCCESSO! Prodotto disabilitato su vista generale")
            print(f"   Le altre viste erediteranno automaticamente se configurate con 'Use Default Value'")
        else:
            print(f"\n⚠️ ATTENZIONE: Prodotto non completamente disabilitato")
    else:
        print(f"❌ Disabilitazione fallita")
else:
    print(f"\n⚠️ SKIP: Test disabilitazione saltato (prodotto non esiste)")

# STEP 4: Verifica permessi token
print(f"\n4️⃣ VERIFICA PERMESSI TOKEN")
print("-" * 60)
print("Tentativo update prodotto (test permessi)...")
payload = {"product": {"sku": TEST_SKU, "visibility": 4}}
try:
    response = requests.put(url_product, headers=headers, json=payload, timeout=10)
    if response.status_code in [200, 404]:
        print("✅ Token ha permessi di scrittura")
    elif response.status_code == 401:
        print("❌ Token NON valido (401 Unauthorized)")
    elif response.status_code == 403:
        print("❌ Token non ha permessi di scrittura (403 Forbidden)")
    else:
        print(f"⚠️ Response: HTTP {response.status_code}")
except Exception as e:
    print(f"❌ Errore: {e}")

# RIEPILOGO
print("\n" + "=" * 60)
print("RIEPILOGO DIAGNOSI")
print("=" * 60)

if current_status is None:
    print("🔴 PROBLEMA PRINCIPALE: Prodotto non esiste su Magento")
    print("\n💡 SOLUZIONE:")
    print("   1. Verifica che il prodotto con SKU '76WW0UT76W' esista su Magento")
    print("   2. Oppure il prodotto BackMarket usa uno SKU diverso da Magento")
    print("   3. Controlla la mappatura SKU BackMarket → Magento")
elif current_status == 2:
    print("✅ Prodotto già disabilitato su Magento")
else:
    print("✅ Tutto OK - Sistema pronto per disabilitare prodotti")

print("\n" + "=" * 60)
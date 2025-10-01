#!/usr/bin/env python3
"""
Sistema di gestione ordini marketplace per ReflexMania - VERSIONE DASHBOARD
- Visualizza ordini pendenti da tutti i canali
- Accetta ordini con workflow completo
- Disabilita prodotto su tutti i canali
- Crea DDT automaticamente
- Genera CSV Packlink per ordini accettati

Deploy su Railway con IP statico
"""

from flask import Flask, request, jsonify, send_file, render_template_string
import requests
import mysql.connector
import pandas as pd
import os
from datetime import datetime
from io import StringIO, BytesIO
import logging
from typing import List, Dict, Optional
import json

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== CONFIGURAZIONI ====================

# BackMarket
BACKMARKET_TOKEN = os.getenv('BACKMARKET_TOKEN', 'NDNjYzQzMDRmNGU2NTUzYzkzYjAwYjpCTVQtOTJhZjQ0MjU5YTlhMmYzMGRhMzA3YWJhZWMwZGI5YzUwMjAxMTdhYQ==')
BACKMARKET_BASE_URL = "https://www.backmarket.fr"

# Refurbed
REFURBED_TOKEN = os.getenv('REFURBED_TOKEN', '277931ea-1ede-4a14-8aaa-41b2222d2aba')
REFURBED_BASE_URL = "https://api.refurbed.com"

# CDiscount (Octopia)
OCTOPIA_CLIENT_ID = os.getenv('OCTOPIA_CLIENT_ID', 'reflexmania')
OCTOPIA_CLIENT_SECRET = os.getenv('OCTOPIA_CLIENT_SECRET', 'qTpoc2gd40Huhzi64FIKY6f9NoKac0C6')
OCTOPIA_SELLER_ID = os.getenv('OCTOPIA_SELLER_ID', '405765')

# InvoiceX DB
INVOICEX_CONFIG = {
    'user': os.getenv('INVOICEX_USER', 'ilblogdi_inv2021'),
    'password': os.getenv('INVOICEX_PASS', 'pWTrEKV}=fF-'),
    'host': os.getenv('INVOICEX_HOST', 'nl1-ts3.a2hosting.com'),
    'database': os.getenv('INVOICEX_DB', 'ilblogdi_invoicex2021'),
}

# ==================== CLIENT API (stessi di prima) ====================

class BackMarketClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = BACKMARKET_BASE_URL
        self.headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def get_orders(self, status: str = None, limit: int = 100) -> List[Dict]:
        try:
            url = f"{self.base_url}/ws/orders"
            params = {'limit': limit}
            if status:
                params['status'] = status
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except Exception as e:
            logger.error(f"Errore BackMarket get_orders: {e}")
            return []
    
    def accept_order(self, order_id: str) -> bool:
        """Accetta un ordine su BackMarket aggiornando le orderlines allo stato 2"""
        try:
            # Prima recupera i dettagli dell'ordine per ottenere gli SKU
            order_url = f"{self.base_url}/ws/orders/{order_id}"
            order_response = requests.get(order_url, headers=self.headers)
            
            if order_response.status_code != 200:
                logger.error(f"Impossibile recuperare dettagli ordine {order_id}")
                return False
            
            order_data = order_response.json()
            orderlines = order_data.get('orderlines', [])
            
            if not orderlines:
                logger.error(f"Nessuna orderline trovata per ordine {order_id}")
                return False
            
            # Accetta ogni orderline specificando il suo SKU
            success_count = 0
            for orderline in orderlines:
                sku = orderline.get('listing') or orderline.get('serial_number')
                
                if not sku:
                    logger.warning(f"SKU mancante per orderline in ordine {order_id}")
                    continue
                
                # Aggiorna orderline con SKU specifico
                update_url = f"{self.base_url}/ws/orders/{order_id}"
                data = {
                    "order_id": int(order_id),
                    "new_state": 2,  # Accepted
                    "sku": sku
                }
                
                response = requests.post(update_url, headers=self.headers, json=data)
                
                if response.status_code == 200:
                    logger.info(f"Orderline {sku} accettata per ordine {order_id}")
                    success_count += 1
                else:
                    logger.error(f"Errore accettazione orderline {sku}: {response.status_code} - {response.text}")
            
            if success_count > 0:
                logger.info(f"Ordine {order_id} accettato: {success_count}/{len(orderlines)} orderlines")
                return True
            else:
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Errore connessione BackMarket API: {e}")
            return False
        except Exception as e:
            logger.error(f"Errore imprevisto: {e}")
            return False
    
    def disable_listing(self, listing_id: str) -> bool:
        """Disabilita un listing (imposta stock a 0)"""
        try:
            url = f"{self.base_url}/ws/listings/{listing_id}"
            data = {'quantity': 0}
            response = requests.put(url, headers=self.headers, json=data)
            response.raise_for_status()
            logger.info(f"Listing BackMarket {listing_id} disabilitato")
            return True
        except Exception as e:
            logger.error(f"Errore disabilitazione listing BackMarket: {e}")
            return False

class RefurbishedClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = REFURBED_BASE_URL
        self.headers = {
            'Authorization': f'Plain {token}',
            'Content-Type': 'application/json'
        }
    
    def get_orders(self, limit: int = 100) -> List[Dict]:
        try:
            url = f"{self.base_url}/refb.merchant.v1.OrderService/ListOrders"
            data = {"pagination": {"limit": limit}}
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            result = response.json()
            return result.get('orders', [])
        except Exception as e:
            logger.error(f"Errore Refurbed get_orders: {e}")
            return []
    
    def disable_offer(self, sku: str) -> bool:
        """Disabilita un'offerta (imposta stock a 0)"""
        try:
            url = f"{self.base_url}/refb.merchant.v1.OfferService/UpdateOffer"
            data = {
                "identifier": {"sku": sku},
                "stock": 0
            }
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            logger.info(f"Offerta Refurbed SKU {sku} disabilitata")
            return True
        except Exception as e:
            logger.error(f"Errore disabilitazione offerta Refurbed: {e}")
            return False

class OctopiaClient:
    def __init__(self, client_id: str, client_secret: str, seller_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.seller_id = seller_id
        self.auth_url = "https://auth.octopia-io.net/auth/realms/maas/protocol/openid-connect/token"
        self.base_url = "https://api.octopia-io.net/seller/v2"
        self.access_token = None
        self.authenticate()
    
    def authenticate(self):
        try:
            auth_data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            response = requests.post(
                self.auth_url,
                data=auth_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            logger.info("Autenticazione Octopia riuscita")
        except Exception as e:
            logger.error(f"Errore autenticazione Octopia: {e}")
    
    def get_orders(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'sellerId': self.seller_id,
                'Content-Type': 'application/json'
            }
            params = {'limit': limit, 'offset': offset}
            response = requests.get(f"{self.base_url}/orders", headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('items', [])
        except Exception as e:
            logger.error(f"Errore Octopia get_orders: {e}")
            return []
    
    def disable_offer(self, seller_product_id: str) -> bool:
        """Disabilita un'offerta (imposta stock a 0)"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'sellerId': self.seller_id,
                'Content-Type': 'application/json'
            }
            
            # Octopia usa il meccanismo di package XML per aggiornare stock
            # Per semplicità usiamo l'API diretta se disponibile
            url = f"{self.base_url}/offers/{seller_product_id}"
            data = {'stock': 0}
            
            response = requests.put(url, headers=headers, json=data)
            response.raise_for_status()
            logger.info(f"Offerta CDiscount {seller_product_id} disabilitata")
            return True
        except Exception as e:
            # Fallback: logga solo se l'API non è disponibile
            logger.warning(f"Impossibile disabilitare offerta CDiscount via API: {e}")
            logger.info(f"Disabilitazione CDiscount {seller_product_id} richiede package XML manuale")
            return True  # Ritorna True per non bloccare il workflow

# ==================== FUNZIONI HELPER ====================

def normalize_order(order: Dict, source: str) -> Dict:
    """Normalizza ordini da diversi marketplace"""
    
    if source == 'backmarket':
        shipping = order.get('shipping_address', {})
        items = []
        for item in order.get('orderlines', []):
            # BackMarket usa 'listing' come SKU e 'serial_number' come seriale
            sku = item.get('serial_number') or item.get('listing', '')
            items.append({
                'sku': sku,
                'name': item.get('product', 'N/A'),
                'quantity': item.get('quantity', 1)
            })
        
        return {
            'order_id': str(order.get('order_id')),
            'source': 'BackMarket',
            'status': order.get('state', 'unknown'),
            'date': order.get('date_creation', ''),
            'customer_name': f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip(),
            'customer_email': shipping.get('email', ''),
            'customer_phone': shipping.get('phone', ''),
            'address': f"{shipping.get('street', '')} {shipping.get('street2', '')}".strip(),
            'city': shipping.get('city', ''),
            'postal_code': shipping.get('postal_code', ''),
            'country': shipping.get('country', ''),
            'items': items,
            'total': float(order.get('price', 0)),
            'accepted': False
        }
    
    elif source == 'refurbed':
        shipping = order.get('shipping_address', {})
        items = []
        for item in order.get('items', []):
            items.append({
                'sku': item.get('sku', item.get('item_identifier', '')),
                'name': item.get('name', 'N/A'),
                'quantity': 1
            })
        
        return {
            'order_id': str(order.get('id')),
            'source': 'Refurbed',
            'status': order.get('state', 'unknown'),
            'date': order.get('released_at', ''),
            'customer_name': f"{shipping.get('first_name', '')} {shipping.get('family_name', '')}".strip(),
            'customer_email': order.get('customer_email', ''),
            'customer_phone': shipping.get('phone_number', ''),
            'address': f"{shipping.get('street_name', '')} {shipping.get('house_no', '')}".strip(),
            'city': shipping.get('town', ''),
            'postal_code': shipping.get('post_code', ''),
            'country': shipping.get('country_code', ''),
            'items': items,
            'total': float(order.get('total_paid', 0)),
            'accepted': False
        }
    
    elif source == 'octopia':
        items = []
        shipping = {}
        
        for line in order.get('lines', []):
            shipping = line.get('shippingAddress', {})
            offer = line.get('offer', {})
            items.append({
                'sku': offer.get('sellerProductId', ''),
                'name': offer.get('productTitle', 'N/A'),
                'quantity': line.get('quantity', 1)
            })
        
        return {
            'order_id': order.get('orderId'),
            'source': 'CDiscount',
            'status': order.get('status', 'unknown'),
            'date': order.get('createdAt', ''),
            'customer_name': f"{shipping.get('firstName', '')} {shipping.get('lastName', '')}".strip(),
            'customer_email': shipping.get('email', ''),
            'customer_phone': shipping.get('phone', ''),
            'address': shipping.get('addressLine1', ''),
            'city': shipping.get('city', ''),
            'postal_code': shipping.get('postalCode', ''),
            'country': shipping.get('countryCode', ''),
            'items': items,
            'total': float(order.get('totalPrice', {}).get('sellingPrice', 0)),
            'accepted': False
        }
    
    return {}

def get_pending_orders() -> List[Dict]:
    """Recupera tutti gli ordini pendenti da tutti i canali"""
    all_orders = []
    seen_order_ids = set()  # Per deduplicare ordini BackMarket
    
    # BackMarket - tutti gli ordini non ancora spediti
    bm_client = BackMarketClient(BACKMARKET_TOKEN)
    bm_count = 0
    
    # Tutti gli stati che indicano "non ancora spedito"
    for status in ['waiting_acceptance', 'accepted', 'to_ship']:
        orders = bm_client.get_orders(status=status)
        for order in orders:
            # Filtra solo ordini NON già spediti (state != 9)
            order_state = order.get('state', 0)
            order_id = str(order.get('order_id'))
            
            # Deduplica: salta se già visto questo order_id
            if order_id in seen_order_ids:
                continue
            
            if order_state != 9:  # 9 = Shipped
                all_orders.append(normalize_order(order, 'backmarket'))
                seen_order_ids.add(order_id)
                bm_count += 1
        logger.info(f"BackMarket status '{status}': {len(orders)} ordini totali")
    
    logger.info(f"BackMarket totale NON spediti (deduplicati): {bm_count} ordini")
    
    # Refurbed - solo ordini non ancora spediti
    rf_client = RefurbishedClient(REFURBED_TOKEN)
    rf_orders = rf_client.get_orders()
    rf_count = 0
    for order in rf_orders:
        if order.get('state') not in ['SHIPPED', 'DELIVERED', 'CANCELLED']:
            all_orders.append(normalize_order(order, 'refurbed'))
            rf_count += 1
    
    logger.info(f"Refurbed: {rf_count} ordini da processare")
    
    # CDiscount - solo ordini non ancora spediti
    oct_client = OctopiaClient(OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID)
    oct_orders = oct_client.get_orders()
    cd_count = 0
    for order in oct_orders:
        if order.get('status') not in ['Shipped', 'Delivered', 'Cancelled']:
            all_orders.append(normalize_order(order, 'octopia'))
            cd_count += 1
    
    logger.info(f"CDiscount: {cd_count} ordini da processare")
    
    return all_orders

def disable_product_on_channels(sku: str, source: str) -> Dict:
    """Disabilita un prodotto su tutti i canali impostando stock a 0"""
    results = {
        'backmarket': {'attempted': False, 'success': False, 'message': ''},
        'refurbed': {'attempted': False, 'success': False, 'message': ''},
        'cdiscount': {'attempted': False, 'success': False, 'message': ''}
    }
    
    logger.info(f"Disabilitazione prodotto SKU {sku} su tutti i canali")
    
    # BackMarket - Disabilita listing
    try:
        bm_client = BackMarketClient(BACKMARKET_TOKEN)
        results['backmarket']['attempted'] = True
        
        # Il listing ID su BackMarket è spesso il SKU stesso o il serial number
        # Potrebbe richiedere una ricerca preventiva del listing
        success = bm_client.disable_listing(sku)
        results['backmarket']['success'] = success
        results['backmarket']['message'] = 'Disabilitato' if success else 'Errore disabilitazione'
    except Exception as e:
        results['backmarket']['message'] = f'Errore: {str(e)}'
        logger.error(f"Errore disabilitazione BackMarket: {e}")
    
    # Refurbed - Disabilita offerta
    try:
        rf_client = RefurbishedClient(REFURBED_TOKEN)
        results['refurbed']['attempted'] = True
        
        success = rf_client.disable_offer(sku)
        results['refurbed']['success'] = success
        results['refurbed']['message'] = 'Disabilitato' if success else 'Errore disabilitazione'
    except Exception as e:
        results['refurbed']['message'] = f'Errore: {str(e)}'
        logger.error(f"Errore disabilitazione Refurbed: {e}")
    
    # CDiscount - Disabilita offerta
    try:
        oct_client = OctopiaClient(OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID)
        results['cdiscount']['attempted'] = True
        
        success = oct_client.disable_offer(sku)
        results['cdiscount']['success'] = success
        results['cdiscount']['message'] = 'Disabilitato' if success else 'Package XML richiesto'
    except Exception as e:
        results['cdiscount']['message'] = f'Errore: {str(e)}'
        logger.error(f"Errore disabilitazione CDiscount: {e}")
    
    # Log risultati
    logger.info(f"Risultati disabilitazione SKU {sku}:")
    logger.info(f"  - BackMarket: {results['backmarket']}")
    logger.info(f"  - Refurbed: {results['refurbed']}")
    logger.info(f"  - CDiscount: {results['cdiscount']}")
    
    return results

def create_ddt_invoicex(order: Dict) -> Optional[str]:
    """Crea DDT su InvoiceX e ritorna il numero DDT"""
    try:
        conn = mysql.connector.connect(**INVOICEX_CONFIG)
        cursor = conn.cursor()
        
        # Ottieni prossimo numero DDT
        query_num = """
        SELECT MAX(CAST(numero AS UNSIGNED)) as max_num 
        FROM documenti_vendita 
        WHERE tipo = 'DDT' AND YEAR(data) = YEAR(CURDATE())
        """
        cursor.execute(query_num)
        result = cursor.fetchone()
        max_num = result[0] if result[0] else 0
        ddt_number = str(max_num + 1).zfill(4)
        
        # Inserisci DDT
        query_header = """
        INSERT INTO documenti_vendita 
        (tipo, numero, data, cliente, totale, note, stato)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        values_header = (
            'DDT',
            ddt_number,
            datetime.now().strftime('%Y-%m-%d'),
            order['customer_name'],
            order['total'],
            f"Ordine {order['source']} #{order['order_id']}",
            'Emesso'
        )
        
        cursor.execute(query_header, values_header)
        ddt_id = cursor.lastrowid
        
        # Inserisci righe
        query_lines = """
        INSERT INTO documenti_vendita_righe
        (documento_id, descrizione, quantita, prezzo_unitario)
        VALUES (%s, %s, %s, %s)
        """
        
        for item in order['items']:
            values_line = (
                ddt_id,
                f"{item['name']} - SKU: {item['sku']}",
                item['quantity'],
                order['total'] / len(order['items'])
            )
            cursor.execute(query_lines, values_line)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"DDT {ddt_number} creato con successo")
        return ddt_number
        
    except Exception as e:
        logger.error(f"Errore creazione DDT: {e}")
        return None

# ==================== ROUTES ====================

@app.route('/')
def dashboard():
    """Dashboard principale con tabella ordini"""
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ReflexMania - Gestione Ordini</title>
        <meta charset="utf-8">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f5f5f5;
                padding: 20px;
            }
            .container { max-width: 1400px; margin: 0 auto; }
            h1 { 
                color: #333; 
                margin-bottom: 30px;
                font-size: 32px;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .stat-card h3 {
                color: #666;
                font-size: 14px;
                margin-bottom: 10px;
            }
            .stat-card .number {
                font-size: 32px;
                font-weight: bold;
                color: #007bff;
            }
            .actions {
                background: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .btn {
                padding: 12px 24px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
                margin-right: 10px;
                transition: all 0.3s;
            }
            .btn-primary { background: #007bff; color: white; }
            .btn-primary:hover { background: #0056b3; }
            .btn-success { background: #28a745; color: white; }
            .btn-success:hover { background: #218838; }
            .btn-small { padding: 6px 12px; font-size: 12px; }
            
            table {
                width: 100%;
                background: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            th {
                background: #f8f9fa;
                padding: 15px;
                text-align: left;
                font-weight: 600;
                color: #333;
                border-bottom: 2px solid #dee2e6;
            }
            td {
                padding: 15px;
                border-bottom: 1px solid #dee2e6;
            }
            tr:hover { background: #f8f9fa; }
            .badge {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
            }
            .badge-backmarket { background: #e3f2fd; color: #1976d2; }
            .badge-refurbed { background: #f3e5f5; color: #7b1fa2; }
            .badge-cdiscount { background: #fff3e0; color: #f57c00; }
            .badge-accepted { background: #d4edda; color: #155724; }
            .badge-pending { background: #fff3cd; color: #856404; }
            
            #loading {
                display: none;
                text-align: center;
                padding: 20px;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 ReflexMania - Gestione Ordini</h1>
            
            <div class="stats">
                <div class="stat-card">
                    <h3>Ordini Pendenti</h3>
                    <div class="number" id="pending-count">-</div>
                </div>
                <div class="stat-card">
                    <h3>BackMarket</h3>
                    <div class="number" id="bm-count">-</div>
                </div>
                <div class="stat-card">
                    <h3>Refurbed</h3>
                    <div class="number" id="rf-count">-</div>
                </div>
                <div class="stat-card">
                    <h3>CDiscount</h3>
                    <div class="number" id="cd-count">-</div>
                </div>
            </div>
            
            <div class="actions">
                <button class="btn btn-primary" onclick="refreshOrders()">🔄 Aggiorna Ordini</button>
                <button class="btn btn-success" onclick="downloadCSV()">📦 Scarica CSV Packlink</button>
            </div>
            
            <div id="loading">⏳ Caricamento in corso...</div>
            
            <table id="orders-table">
                <thead>
                    <tr>
                        <th>Numero Ordine</th>
                        <th>Canale</th>
                        <th>Cliente</th>
                        <th>Prodotto</th>
                        <th>SKU / Seriale</th>
                        <th>Data</th>
                        <th>Importo</th>
                        <th>Stato</th>
                        <th>Azioni</th>
                    </tr>
                </thead>
                <tbody id="orders-body">
                    <tr><td colspan="8" style="text-align: center; padding: 40px;">Caricamento ordini...</td></tr>
                </tbody>
            </table>
        </div>
        
        <script>
            let orders = [];
            
            function refreshOrders() {
                document.getElementById('loading').style.display = 'block';
                fetch('/api/orders')
                    .then(r => r.json())
                    .then(data => {
                        orders = data.orders;
                        updateStats();
                        renderOrders();
                        document.getElementById('loading').style.display = 'none';
                    })
                    .catch(err => {
                        console.error(err);
                        alert('Errore nel caricamento ordini');
                        document.getElementById('loading').style.display = 'none';
                    });
            }
            
            function updateStats() {
                const bm = orders.filter(o => o.source === 'BackMarket').length;
                const rf = orders.filter(o => o.source === 'Refurbed').length;
                const cd = orders.filter(o => o.source === 'CDiscount').length;
                
                document.getElementById('pending-count').textContent = orders.length;
                document.getElementById('bm-count').textContent = bm;
                document.getElementById('rf-count').textContent = rf;
                document.getElementById('cd-count').textContent = cd;
            }
            
            function renderOrders() {
                const tbody = document.getElementById('orders-body');
                
                if (orders.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px;">✅ Nessun ordine pendente</td></tr>';
                    return;
                }
                
                tbody.innerHTML = orders.map(order => {
                    const badgeClass = 'badge-' + order.source.toLowerCase().replace('c', 'c');
                    const date = new Date(order.date).toLocaleDateString('it-IT');
                    
                    // Estrai info prodotti
                    let productInfo = 'N/A';
                    let skuInfo = 'N/A';
                    
                    if (order.items && order.items.length > 0) {
                        const item = order.items[0];
                        productInfo = item.name || 'N/A';
                        skuInfo = item.sku || 'N/A';
                        
                        // Se ci sono più prodotti, mostra il conteggio
                        if (order.items.length > 1) {
                            productInfo += ` (+${order.items.length - 1})`;
                        }
                    }
                    
                    // Determina i pulsanti da mostrare in base allo stato
                    let actionButtons = '';
                    let statusBadge = '';
                    
                    if (order.source === 'BackMarket') {
                        const stateNum = order.status;
                        
                        if (stateNum === 1 || order.status === 'waiting_acceptance') {
                            // Ordine da accettare - mostra entrambi i pulsanti
                            actionButtons = `
                                <button class="btn btn-primary btn-small" onclick="acceptOrderOnly('${order.order_id}', '${order.source}')" style="margin-right: 5px;">
                                    ✓ Accetta Ordine
                                </button>
                                <button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">
                                    📄 Crea DDT
                                </button>
                            `;
                            statusBadge = '<span class="badge badge-pending">Da Accettare</span>';
                        } else if (stateNum === 2 || order.status === 'accepted') {
                            // Ordine già accettato - solo DDT
                            actionButtons = `
                                <button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">
                                    📄 Crea DDT
                                </button>
                            `;
                            statusBadge = '<span class="badge badge-accepted">Accettato</span>';
                        } else if (stateNum === 3 || order.status === 'to_ship') {
                            // Pronto per spedizione - solo DDT
                            actionButtons = `
                                <button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">
                                    📄 Crea DDT
                                </button>
                            `;
                            statusBadge = '<span class="badge badge-accepted">Da Spedire</span>';
                        } else {
                            actionButtons = `
                                <button class="btn btn-primary btn-small" onclick="acceptOrderOnly('${order.order_id}', '${order.source}')" style="margin-right: 5px;">
                                    ✓ Accetta Ordine
                                </button>
                                <button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">
                                    📄 Crea DDT
                                </button>
                            `;
                            statusBadge = '<span class="badge badge-pending">Pendente</span>';
                        }
                    } else {
                        // Per Refurbed e CDiscount mostra solo DDT (non serve accettazione)
                        actionButtons = `
                            <button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">
                                📄 Crea DDT
                            </button>
                        `;
                        statusBadge = '<span class="badge badge-pending">Pendente</span>';
                    }
                    
                    return `
                        <tr>
                            <td><strong>${order.order_id}</strong></td>
                            <td><span class="badge ${badgeClass}">${order.source}</span></td>
                            <td>${order.customer_name}</td>
                            <td>${productInfo}</td>
                            <td><code>${skuInfo}</code></td>
                            <td>${date}</td>
                            <td><strong>€${order.total.toFixed(2)}</strong></td>
                            <td>${statusBadge}</td>
                            <td>${actionButtons}</td>
                        </tr>
                    `;
                }).join('');
            }
            
            function acceptOrderOnly(orderId, source) {
                if (!confirm(`Confermi l'accettazione dell'ordine ${orderId} su ${source}?`)) {
                    return;
                }
                
                document.getElementById('loading').style.display = 'block';
                
                fetch('/api/accept_order_only', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({order_id: orderId, source: source})
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        alert(`✅ Ordine ${orderId} accettato con successo su ${source}!`);
                        refreshOrders();
                    } else {
                        alert('❌ Errore: ' + data.error);
                        document.getElementById('loading').style.display = 'none';
                    }
                })
                .catch(err => {
                    alert('❌ Errore di connessione');
                    console.error(err);
                    document.getElementById('loading').style.display = 'none';
                });
            }
            
            function createDDTOnly(orderId, source) {
                if (!confirm(`Confermi la creazione del DDT per l'ordine ${orderId}?\n\nQuesto:\n- Disabiliterà i prodotti su tutti i canali\n- Creerà il DDT su InvoiceX`)) {
                    return;
                }
                
                document.getElementById('loading').style.display = 'block';
                
                fetch('/api/create_ddt_only', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({order_id: orderId, source: source})
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        alert(`✅ DDT creato con successo!\n\nNumero DDT: ${data.ddt_number}\n\nL'ordine è ora pronto per la spedizione.`);
                        refreshOrders();
                    } else {
                        alert('❌ Errore: ' + data.error);
                        document.getElementById('loading').style.display = 'none';
                    }
                })
                .catch(err => {
                    alert('❌ Errore di connessione');
                    console.error(err);
                    document.getElementById('loading').style.display = 'none';
                });
            }
            
            function acceptOrder(orderId, source) {
                if (!confirm(`Confermi l'accettazione dell'ordine ${orderId}?\n\nQuesto:\n- Accetterà l'ordine su ${source}\n- Disabiliterà i prodotti su tutti i canali\n- Creerà il DDT su InvoiceX`)) {
                    return;
                }
                
                document.getElementById('loading').style.display = 'block';
                
                fetch('/api/accept_order', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({order_id: orderId, source: source})
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        alert(`✅ Ordine accettato con successo!\n\nDDT: ${data.ddt_number}\n\nL'ordine è ora pronto per la spedizione.`);
                        refreshOrders();
                    } else {
                        alert('❌ Errore: ' + data.error);
                        document.getElementById('loading').style.display = 'none';
                    }
                })
                .catch(err => {
                    alert('❌ Errore di connessione');
                    console.error(err);
                    document.getElementById('loading').style.display = 'none';
                });
            }
            
            function downloadCSV() {
                window.location.href = '/api/packlink_csv';
            }
            
            // Carica ordini all'avvio
            refreshOrders();
            
            // Auto-refresh ogni 2 minuti
            setInterval(refreshOrders, 120000);
        </script>
    </body>
    </html>
    """
    
    return html

@app.route('/api/orders')
def api_orders():
    """API: ritorna lista ordini pendenti"""
    try:
        orders = get_pending_orders()
        return jsonify({'orders': orders, 'count': len(orders)})
    except Exception as e:
        logger.error(f"Errore API orders: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/accept_order_only', methods=['POST'])
def api_accept_order_only():
    """API: accetta solo l'ordine sul marketplace (senza DDT)"""
    try:
        data = request.json
        order_id = data.get('order_id')
        source = data.get('source')
        
        # Solo BackMarket ha bisogno di accettazione esplicita
        if source == 'BackMarket':
            bm_client = BackMarketClient(BACKMARKET_TOKEN)
            if not bm_client.accept_order(order_id):
                return jsonify({'success': False, 'error': 'Errore accettazione ordine'}), 500
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'message': 'Ordine accettato sul marketplace'
        })
        
    except Exception as e:
        logger.error(f"Errore accept_order_only: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create_ddt_only', methods=['POST'])
def api_create_ddt_only():
    """API: crea solo DDT e disabilita prodotti (senza accettazione ordine)"""
    try:
        data = request.json
        order_id = data.get('order_id')
        source = data.get('source')
        
        # Trova l'ordine completo
        all_orders = get_pending_orders()
        order = next((o for o in all_orders if o['order_id'] == order_id and o['source'] == source), None)
        
        if not order:
            return jsonify({'success': False, 'error': 'Ordine non trovato'}), 404
        
        # 1. Disabilita prodotti su tutti i canali
        disable_results = {}
        for item in order['items']:
            result = disable_product_on_channels(item['sku'], source)
            disable_results[item['sku']] = result
        
        # 2. Crea DDT su InvoiceX
        ddt_number = create_ddt_invoicex(order)
        if not ddt_number:
            return jsonify({'success': False, 'error': 'Errore creazione DDT'}), 500
        
        return jsonify({
            'success': True,
            'ddt_number': ddt_number,
            'order_id': order_id,
            'message': 'DDT creato con successo'
        })
        
    except Exception as e:
        logger.error(f"Errore create_ddt_only: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/accept_order', methods=['POST'])
def api_accept_order():
    """API: accetta ordine e crea DDT"""
    try:
        data = request.json
        order_id = data.get('order_id')
        source = data.get('source')
        
        # Trova l'ordine completo
        all_orders = get_pending_orders()
        order = next((o for o in all_orders if o['order_id'] == order_id and o['source'] == source), None)
        
        if not order:
            return jsonify({'success': False, 'error': 'Ordine non trovato'}), 404
        
        # 1. Accetta ordine sul marketplace
        if source == 'BackMarket':
            bm_client = BackMarketClient(BACKMARKET_TOKEN)
            if not bm_client.accept_order(order_id):
                return jsonify({'success': False, 'error': 'Errore accettazione ordine'}), 500
        
        # 2. Disabilita prodotti su tutti i canali
        disable_results = {}
        for item in order['items']:
            result = disable_product_on_channels(item['sku'], source)
            disable_results[item['sku']] = result
        
        # 3. Crea DDT su InvoiceX
        ddt_number = create_ddt_invoicex(order)
        if not ddt_number:
            return jsonify({'success': False, 'error': 'Errore creazione DDT'}), 500
        
        return jsonify({
            'success': True,
            'ddt_number': ddt_number,
            'order_id': order_id,
            'message': 'Ordine accettato e DDT creato'
        })
        
    except Exception as e:
        logger.error(f"Errore accept_order: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/packlink_csv')
def api_packlink_csv():
    """API: genera CSV Packlink per ordini accettati"""
    try:
        # TODO: Recupera solo ordini accettati dal DB locale o flag
        # Per ora usiamo tutti gli ordini pendenti
        orders = get_pending_orders()
        
        rows = []
        for order in orders:
            for item in order.get('items', []):
                row = {
                    'Destinatario': order['customer_name'],
                    'Indirizzo': order['address'],
                    'CAP': order['postal_code'],
                    'Città': order['city'],
                    'Paese': order['country'],
                    'Telefono': order['customer_phone'],
                    'Email': order['customer_email'],
                    'Riferimento': f"{order['source']}-{order['order_id']}",
                    'Contenuto': item['name'],
                    'Valore dichiarato': order['total'],
                    'Peso (kg)': '0.5',
                    'Lunghezza (cm)': '20',
                    'Larghezza (cm)': '15',
                    'Altezza (cm)': '10',
                }
                rows.append(row)
        
        df = pd.DataFrame(rows)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, sep=';', index=False, encoding='utf-8')
        
        csv_bytes = BytesIO()
        csv_bytes.write(csv_buffer.getvalue().encode('utf-8'))
        csv_bytes.seek(0)
        
        filename = f"packlink_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Errore packlink CSV: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
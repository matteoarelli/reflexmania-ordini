#!/usr/bin/env python3
"""
Sistema di gestione ordini marketplace per ReflexMania
- Estrazione ordini da BackMarket, Refurbed, CDiscount
- Generazione CSV per Packlink Pro
- Creazione DDT su InvoiceX

Deploy su Railway con IP statico
"""

from flask import Flask, request, jsonify, send_file
import requests
import mysql.connector
import pandas as pd
import os
from datetime import datetime
from io import StringIO, BytesIO
import logging
from typing import List, Dict, Optional
import base64

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

# ==================== CLIENT API ====================

class BackMarketClient:
    """Client per API BackMarket"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = BACKMARKET_BASE_URL
        self.headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def get_orders(self, status: str = None, limit: int = 100) -> List[Dict]:
        """Recupera ordini da BackMarket"""
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

class RefurbishedClient:
    """Client per API Refurbed"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = REFURBED_BASE_URL
        self.headers = {
            'Authorization': f'Plain {token}',
            'Content-Type': 'application/json'
        }
    
    def get_orders(self, limit: int = 100) -> List[Dict]:
        """Recupera ordini da Refurbed"""
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

class OctopiaClient:
    """Client per API CDiscount/Octopia"""
    
    def __init__(self, client_id: str, client_secret: str, seller_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.seller_id = seller_id
        self.auth_url = "https://auth.octopia-io.net/auth/realms/maas/protocol/openid-connect/token"
        self.base_url = "https://api.octopia-io.net/seller/v2"
        self.access_token = None
        self.authenticate()
    
    def authenticate(self):
        """Autentica con Octopia"""
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
        """Recupera ordini da CDiscount"""
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

# ==================== GENERAZIONE CSV PACKLINK ====================

def normalize_order(order: Dict, source: str) -> Dict:
    """Normalizza ordini da diversi marketplace in formato comune"""
    
    if source == 'backmarket':
        return {
            'order_id': order.get('order_id'),
            'source': 'BackMarket',
            'customer_name': f"{order.get('shipping_address', {}).get('first_name', '')} {order.get('shipping_address', {}).get('last_name', '')}",
            'customer_email': order.get('customer_email', ''),
            'customer_phone': order.get('shipping_address', {}).get('phone', ''),
            'address': order.get('shipping_address', {}).get('street', ''),
            'city': order.get('shipping_address', {}).get('city', ''),
            'postal_code': order.get('shipping_address', {}).get('postal_code', ''),
            'country': order.get('shipping_address', {}).get('country', ''),
            'items': [{'sku': item.get('sku'), 'name': item.get('name'), 'quantity': item.get('quantity')} 
                     for item in order.get('items', [])],
            'total': order.get('total_price', 0)
        }
    
    elif source == 'refurbed':
        shipping = order.get('shipping_address', {})
        return {
            'order_id': order.get('id'),
            'source': 'Refurbed',
            'customer_name': f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}",
            'customer_email': order.get('customer_email', ''),
            'customer_phone': shipping.get('phone', ''),
            'address': shipping.get('street', ''),
            'city': shipping.get('city', ''),
            'postal_code': shipping.get('postal_code', ''),
            'country': shipping.get('country_code', ''),
            'items': [{'sku': item.get('sku'), 'name': item.get('name'), 'quantity': 1} 
                     for item in order.get('line_items', [])],
            'total': order.get('total_price', {}).get('amount', 0)
        }
    
    elif source == 'octopia':
        shipping = order.get('ShippingAddress', {})
        return {
            'order_id': order.get('OrderId'),
            'source': 'CDiscount',
            'customer_name': f"{shipping.get('FirstName', '')} {shipping.get('LastName', '')}",
            'customer_email': order.get('CustomerEmail', ''),
            'customer_phone': shipping.get('Phone', ''),
            'address': shipping.get('Address', ''),
            'city': shipping.get('City', ''),
            'postal_code': shipping.get('ZipCode', ''),
            'country': shipping.get('Country', ''),
            'items': [{'sku': item.get('SellerProductId'), 'name': item.get('ProductName'), 'quantity': item.get('Quantity')} 
                     for item in order.get('OrderLines', [])],
            'total': order.get('TotalPrice', 0)
        }
    
    return {}

def generate_packlink_csv(orders: List[Dict]) -> str:
    """Genera CSV per Packlink Pro secondo specifiche"""
    
    rows = []
    for order in orders:
        # Un ordine può avere più righe se ci sono più items
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
                'Peso (kg)': '0.5',  # Default
                'Lunghezza (cm)': '20',
                'Larghezza (cm)': '15',
                'Altezza (cm)': '10',
            }
            rows.append(row)
    
    df = pd.DataFrame(rows)
    
    # Genera CSV con separatore punto e virgola
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, sep=';', index=False, encoding='utf-8')
    
    return csv_buffer.getvalue()

# ==================== DDT INVOICEX ====================

class InvoiceXClient:
    """Client per generare DDT su InvoiceX"""
    
    def __init__(self, config: Dict):
        self.config = config
    
    def create_ddt(self, order: Dict) -> bool:
        """Crea DDT su InvoiceX per un ordine"""
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            
            # Data corrente
            data_ddt = datetime.now().strftime('%Y-%m-%d')
            
            # Inserisci intestazione DDT
            query_header = """
            INSERT INTO documenti_vendita 
            (tipo, numero, data, cliente, totale, note, stato)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            values_header = (
                'DDT',  # tipo
                self._get_next_ddt_number(cursor),  # numero
                data_ddt,  # data
                order['customer_name'],  # cliente
                order['total'],  # totale
                f"Ordine {order['source']} #{order['order_id']}",  # note
                'Emesso'  # stato
            )
            
            cursor.execute(query_header, values_header)
            ddt_id = cursor.lastrowid
            
            # Inserisci righe DDT
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
                    order['total'] / len(order['items'])  # Dividi prezzo equamente
                )
                cursor.execute(query_lines, values_line)
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"DDT creato con successo: ID {ddt_id}")
            return True
            
        except Exception as e:
            logger.error(f"Errore creazione DDT: {e}")
            return False
    
    def _get_next_ddt_number(self, cursor) -> str:
        """Ottiene il prossimo numero DDT"""
        query = """
        SELECT MAX(CAST(numero AS UNSIGNED)) as max_num 
        FROM documenti_vendita 
        WHERE tipo = 'DDT' AND YEAR(data) = YEAR(CURDATE())
        """
        cursor.execute(query)
        result = cursor.fetchone()
        
        max_num = result[0] if result[0] else 0
        return str(max_num + 1).zfill(4)

# ==================== ENDPOINTS API ====================

@app.route('/')
def index():
    """Homepage con dashboard"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ReflexMania - Gestione Ordini</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; }
            .button { 
                display: inline-block; 
                padding: 15px 30px; 
                margin: 10px; 
                background: #007bff; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px;
                cursor: pointer;
                border: none;
                font-size: 16px;
            }
            .button:hover { background: #0056b3; }
            .success { background: #28a745; }
            .success:hover { background: #218838; }
            h1 { color: #333; }
            .section { margin: 30px 0; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>🚀 ReflexMania - Gestione Ordini Marketplace</h1>
        
        <div class="section">
            <h2>📦 Generazione Etichette Packlink</h2>
            <p>Scarica CSV con ordini da BackMarket, Refurbed e CDiscount</p>
            <form action="/generate_packlink_csv" method="get">
                <button type="submit" class="button">Scarica CSV Packlink</button>
            </form>
        </div>
        
        <div class="section">
            <h2>📄 Generazione DDT InvoiceX</h2>
            <p>Crea DDT per tutti gli ordini non ancora processati</p>
            <form action="/generate_ddt" method="post">
                <button type="submit" class="button success">Genera DDT</button>
            </form>
        </div>
        
        <div class="section">
            <h2>ℹ️ Info Sistema</h2>
            <p><strong>Status:</strong> ✅ Operativo</p>
            <p><strong>IP Statico:</strong> Configurato su Railway</p>
            <p><strong>Marketplaces:</strong> BackMarket, Refurbed, CDiscount</p>
        </div>
    </body>
    </html>
    """

@app.route('/generate_packlink_csv', methods=['GET'])
def generate_packlink_csv_endpoint():
    """Genera e scarica CSV per Packlink Pro"""
    try:
        logger.info("Inizio generazione CSV Packlink")
        
        all_orders = []
        
        # BackMarket - prendi ordini da accettare, accettati e da spedire
        logger.info("Recupero ordini BackMarket...")
        bm_client = BackMarketClient(BACKMARKET_TOKEN)
        
        # Prova diversi status
        for status in ['waiting_acceptance', 'accepted', 'to_ship']:
            orders = bm_client.get_orders(status=status)
            for order in orders:
                all_orders.append(normalize_order(order, 'backmarket'))
            logger.info(f"BackMarket ({status}): {len(orders)} ordini")
        
        # Refurbed
        logger.info("Recupero ordini Refurbed...")
        rf_client = RefurbishedClient(REFURBED_TOKEN)
        rf_orders = rf_client.get_orders()
        for order in rf_orders:
            all_orders.append(normalize_order(order, 'refurbed'))
        logger.info(f"Refurbed: {len(rf_orders)} ordini")
        
        # CDiscount
        logger.info("Recupero ordini CDiscount...")
        oct_client = OctopiaClient(OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID)
        oct_orders = oct_client.get_orders()
        for order in oct_orders:
            all_orders.append(normalize_order(order, 'octopia'))
        logger.info(f"CDiscount: {len(oct_orders)} ordini")
        
        # Genera CSV
        csv_content = generate_packlink_csv(all_orders)
        
        # Crea file in memoria
        csv_buffer = BytesIO()
        csv_buffer.write(csv_content.encode('utf-8'))
        csv_buffer.seek(0)
        
        filename = f"packlink_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        logger.info(f"CSV generato: {len(all_orders)} ordini totali")
        
        return send_file(
            csv_buffer,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Errore generazione CSV: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate_ddt', methods=['POST'])
def generate_ddt_endpoint():
    """Genera DDT su InvoiceX per tutti gli ordini"""
    try:
        logger.info("Inizio generazione DDT")
        
        all_orders = []
        
        # Recupera ordini da tutti i marketplace
        bm_client = BackMarketClient(BACKMARKET_TOKEN)
        rf_client = RefurbishedClient(REFURBED_TOKEN)
        oct_client = OctopiaClient(OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID)
        
        # BackMarket - prendi ordini in diversi stati
        for status in ['waiting_acceptance', 'accepted', 'to_ship']:
            for order in bm_client.get_orders(status=status):
                all_orders.append(normalize_order(order, 'backmarket'))
        
        for order in rf_client.get_orders():
            all_orders.append(normalize_order(order, 'refurbed'))
        
        for order in oct_client.get_orders():
            all_orders.append(normalize_order(order, 'octopia'))
        
        # Crea DDT per ogni ordine
        invoicex = InvoiceXClient(INVOICEX_CONFIG)
        success_count = 0
        error_count = 0
        
        for order in all_orders:
            if invoicex.create_ddt(order):
                success_count += 1
            else:
                error_count += 1
        
        logger.info(f"DDT generati: {success_count} successi, {error_count} errori")
        
        return jsonify({
            'success': True,
            'total_orders': len(all_orders),
            'ddt_created': success_count,
            'errors': error_count
        })
        
    except Exception as e:
        logger.error(f"Errore generazione DDT: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/debug_orders', methods=['GET'])
def debug_orders():
    """Debug: mostra struttura ordini grezzi dalle API"""
    try:
        result = {
            'backmarket': [],
            'refurbed': [],
            'cdiscount': []
        }
        
        # BackMarket
        bm_client = BackMarketClient(BACKMARKET_TOKEN)
        bm_orders = bm_client.get_orders(status='accepted', limit=1)
        if bm_orders:
            result['backmarket'] = bm_orders[0]  # Solo il primo ordine
        
        # Refurbed
        rf_client = RefurbishedClient(REFURBED_TOKEN)
        rf_orders = rf_client.get_orders(limit=1)
        if rf_orders:
            result['refurbed'] = rf_orders[0]
        
        # CDiscount
        oct_client = OctopiaClient(OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID)
        oct_orders = oct_client.get_orders(limit=1)
        if oct_orders:
            result['cdiscount'] = oct_orders[0]
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
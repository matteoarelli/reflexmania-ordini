#!/usr/bin/env python3
"""
Sistema di gestione ordini marketplace per ReflexMania - VERSIONE DASHBOARD
Deploy su Railway con IP statico
Supporto: BackMarket, Refurbed, CDiscount, Magento
"""

from flask import Flask, request, jsonify, send_file
import pandas as pd
import os
from datetime import datetime
from io import BytesIO
import logging

# Import moduli locali
from config import (
    BACKMARKET_TOKEN, BACKMARKET_BASE_URL,
    REFURBED_TOKEN, REFURBED_BASE_URL,
    OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID,
    MAGENTO_URL, MAGENTO_TOKEN,
    INVOICEX_CONFIG,
    INVOICEX_API_URL, INVOICEX_API_KEY
)
from clients import BackMarketClient, RefurbishedClient, OctopiaClient
from clients.invoicex_api import InvoiceXAPIClient
from clients.magento_api import MagentoAPIClient
from services import (
    get_pending_orders, 
    disable_product_on_channels,
)
from services.ddt_service import DDTService
from services.magento_service import MagentoService

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Inizializza clients marketplace
bm_client = BackMarketClient(BACKMARKET_TOKEN, BACKMARKET_BASE_URL)
rf_client = RefurbishedClient(REFURBED_TOKEN, REFURBED_BASE_URL)
oct_client = OctopiaClient(OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID)

# Inizializza Magento client
magento_client = MagentoAPIClient(MAGENTO_URL, MAGENTO_TOKEN)
magento_service = MagentoService(magento_client)

# Inizializza InvoiceX API client
invoicex_api_client = InvoiceXAPIClient(
    base_url=INVOICEX_API_URL,
    api_key=INVOICEX_API_KEY
)

# Inizializza DDT Service
ddt_service = DDTService(invoicex_api_client)


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
            .badge-magento { background: #ffe0e0; color: #c62828; }
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
            <h1>ReflexMania - Gestione Ordini</h1>
            
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
                <div class="stat-card">
                    <h3>Magento</h3>
                    <div class="number" id="mg-count">-</div>
                </div>
            </div>
            
            <div class="actions">
                <button class="btn btn-primary" onclick="refreshOrders()">Aggiorna Ordini</button>
                <button class="btn btn-success" onclick="downloadCSV()">Scarica CSV Packlink</button>
            </div>
            
            <div id="loading">Caricamento in corso...</div>
            
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
                    <tr><td colspan="9" style="text-align: center; padding: 40px;">Caricamento ordini...</td></tr>
                </tbody>
            </table>
        </div>
        
        <script>
            let orders = [];
            
            function refreshOrders() {
                document.getElementById('loading').style.display = 'block';
                fetch('/api/orders/all')
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
                const mg = orders.filter(o => o.source === 'Magento').length;
                
                document.getElementById('pending-count').textContent = orders.length;
                document.getElementById('bm-count').textContent = bm;
                document.getElementById('rf-count').textContent = rf;
                document.getElementById('cd-count').textContent = cd;
                document.getElementById('mg-count').textContent = mg;
            }
            
            function renderOrders() {
                const tbody = document.getElementById('orders-body');
                
                if (orders.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; padding: 40px;">Nessun ordine pendente</td></tr>';
                    return;
                }
                
                tbody.innerHTML = orders.map(order => {
                    const badgeClass = 'badge-' + order.source.toLowerCase();
                    const date = new Date(order.date).toLocaleDateString('it-IT');
                    
                    let productInfo = 'N/A';
                    let skuInfo = 'N/A';
                    
                    if (order.items && order.items.length > 0) {
                        const item = order.items[0];
                        productInfo = item.name || 'N/A';
                        skuInfo = item.sku || 'N/A';
                        
                        if (order.items.length > 1) {
                            productInfo += ` (+${order.items.length - 1})`;
                        }
                    }
                    
                    let actionButtons = '';
                    let statusBadge = '';
                    
                    if (order.source === 'Magento') {
                        actionButtons = `<button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">Crea DDT</button>`;
                        statusBadge = '<span class="badge badge-pending">Processing</span>';
                    } else if (order.source === 'BackMarket') {
                        const stateNum = order.status;
                        
                        let packingSlipBtn = '';
                        if (order.delivery_note) {
                            packingSlipBtn = `<a href="${order.delivery_note}" target="_blank" class="btn btn-primary btn-small" style="margin-right: 5px; background: #6c757d;">Packing Slip</a>`;
                        }
                        
                        if (stateNum === 1 || order.status === 'waiting_acceptance') {
                            actionButtons = `${packingSlipBtn}<button class="btn btn-primary btn-small" onclick="acceptOrderOnly('${order.order_id}', '${order.source}')" style="margin-right: 5px;">Accetta</button><button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">Crea DDT</button>`;
                            statusBadge = '<span class="badge badge-pending">Da Accettare</span>';
                        } else if (stateNum === 2 || order.status === 'accepted') {
                            actionButtons = `${packingSlipBtn}<button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')" style="margin-right: 5px;">Crea DDT</button><button class="btn btn-primary btn-small" onclick="markAsShipped('${order.order_id}', '${order.source}')" style="background: #17a2b8;">Spedito</button>`;
                            statusBadge = '<span class="badge badge-accepted">Accettato</span>';
                        } else if (stateNum === 3 || order.status === 'to_ship') {
                            actionButtons = `${packingSlipBtn}<button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')" style="margin-right: 5px;">Crea DDT</button><button class="btn btn-primary btn-small" onclick="markAsShipped('${order.order_id}', '${order.source}')" style="background: #17a2b8;">Spedito</button>`;
                            statusBadge = '<span class="badge badge-accepted">Da Spedire</span>';
                        } else {
                            actionButtons = `${packingSlipBtn}<button class="btn btn-primary btn-small" onclick="acceptOrderOnly('${order.order_id}', '${order.source}')" style="margin-right: 5px;">Accetta</button><button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">Crea DDT</button>`;
                            statusBadge = '<span class="badge badge-pending">Pendente</span>';
                        }
                    } else if (order.source === 'Refurbed') {
                        const orderState = order.status;
                        
                        if (orderState === 'NEW') {
                            actionButtons = `<button class="btn btn-primary btn-small" onclick="acceptOrderOnly('${order.order_id}', '${order.source}')" style="margin-right: 5px;">Accetta</button><button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">Crea DDT</button>`;
                            statusBadge = '<span class="badge badge-pending">Da Accettare</span>';
                        } else if (orderState === 'ACCEPTED') {
                            actionButtons = `<button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')" style="margin-right: 5px;">Crea DDT</button><button class="btn btn-primary btn-small" onclick="markAsShipped('${order.order_id}', '${order.source}')" style="background: #17a2b8;">Spedito</button>`;
                            statusBadge = '<span class="badge badge-accepted">Accettato</span>';
                        } else {
                            actionButtons = `<button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">Crea DDT</button>`;
                            statusBadge = '<span class="badge badge-pending">Pendente</span>';
                        }
                    } else {
                        actionButtons = `<button class="btn btn-success btn-small" onclick="createDDTOnly('${order.order_id}', '${order.source}')">Crea DDT</button>`;
                        statusBadge = '<span class="badge badge-pending">Pendente</span>';
                    }
                    
                    return `<tr><td><strong>${order.order_id}</strong></td><td><span class="badge ${badgeClass}">${order.source}</span></td><td>${order.customer_name}</td><td>${productInfo}</td><td><code>${skuInfo}</code></td><td>${date}</td><td><strong>€${order.total.toFixed(2)}</strong></td><td>${statusBadge}</td><td>${actionButtons}</td></tr>`;
                }).join('');
            }
            
            function markAsShipped(orderId, source) {
                const trackingNumber = prompt(`Inserisci il numero di tracking per l'ordine ${orderId}:`);
                if (!trackingNumber || trackingNumber.trim() === '') { alert('Numero di tracking obbligatorio'); return; }
                const trackingUrl = prompt(`Inserisci l'URL di tracking (opzionale):`);
                if (!confirm(`Confermi la spedizione dell'ordine ${orderId}?\\n\\nTracking: ${trackingNumber}`)) return;
                document.getElementById('loading').style.display = 'block';
                fetch('/api/mark_shipped', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, source: source, tracking_number: trackingNumber, tracking_url: trackingUrl || ''}) })
                .then(r => r.json()).then(data => { if (data.success) { alert(`Ordine ${orderId} marcato come spedito!\\n\\nTracking comunicato al marketplace.`); refreshOrders(); } else { alert('Errore: ' + data.error); document.getElementById('loading').style.display = 'none'; } })
                .catch(err => { alert('Errore di connessione'); console.error(err); document.getElementById('loading').style.display = 'none'; });
            }
            
            function acceptOrderOnly(orderId, source) {
                if (!confirm(`Confermi l'accettazione dell'ordine ${orderId} su ${source}?`)) return;
                document.getElementById('loading').style.display = 'block';
                fetch('/api/accept_order_only', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, source: source}) })
                .then(r => r.json()).then(data => { if (data.success) { alert(`Ordine ${orderId} accettato con successo su ${source}!`); refreshOrders(); } else { alert('Errore: ' + data.error); document.getElementById('loading').style.display = 'none'; } })
                .catch(err => { alert('Errore di connessione'); console.error(err); document.getElementById('loading').style.display = 'none'; });
            }
            
            function createDDTOnly(orderId, source) {
                if (!confirm(`Confermi la creazione del DDT per l'ordine ${orderId}?\\n\\nQuesto:\\n- Disabiliterà i prodotti su tutti i canali\\n- Creerà il DDT su InvoiceX`)) return;
                document.getElementById('loading').style.display = 'block';
                fetch('/api/create_ddt_only', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, source: source}) })
                .then(r => r.json()).then(data => { if (data.success) { alert(`DDT creato con successo!\\n\\nNumero DDT: ${data.ddt_number}\\n\\nL'ordine è ora pronto per la spedizione.`); refreshOrders(); } else { alert('Errore: ' + data.error); document.getElementById('loading').style.display = 'none'; } })
                .catch(err => { alert('Errore di connessione'); console.error(err); document.getElementById('loading').style.display = 'none'; });
            }
            
            function downloadCSV() { window.location.href = '/api/packlink_csv'; }
            
            refreshOrders();
            setInterval(refreshOrders, 120000);
        </script>
    </body>
    </html>
    """
    
    return html


# ============================================================================
# API MARKETPLACE (BackMarket, Refurbed, CDiscount)
# ============================================================================

@app.route('/api/orders')
def api_orders():
    """API: ritorna lista ordini pendenti marketplace"""
    try:
        orders = get_pending_orders(bm_client, rf_client, oct_client)
        return jsonify({'orders': orders, 'count': len(orders)})
    except Exception as e:
        logger.error(f"Errore API orders: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/mark_shipped', methods=['POST'])
def api_mark_shipped():
    """API: marca ordine come spedito e comunica tracking al marketplace"""
    try:
        data = request.json
        order_id = data.get('order_id')
        source = data.get('source')
        tracking_number = data.get('tracking_number')
        tracking_url = data.get('tracking_url', '')
        
        if not tracking_number:
            return jsonify({'success': False, 'error': 'Tracking number obbligatorio'}), 400
        
        if source == 'BackMarket':
            if not bm_client.mark_as_shipped(order_id, tracking_number, tracking_url):
                return jsonify({'success': False, 'error': 'Errore comunicazione tracking'}), 500
        
        # Magento: marca come complete dopo spedizione
        if source == 'Magento':
            order = magento_service.get_order_by_id(order_id)
            if order and order.get('entity_id'):
                magento_service.mark_order_as_completed(order['entity_id'])
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'tracking_number': tracking_number,
            'message': 'Ordine marcato come spedito'
        })
        
    except Exception as e:
        logger.error(f"Errore mark_shipped: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accept_order_only', methods=['POST'])
def api_accept_order_only():
    """API: accetta solo l'ordine sul marketplace (senza DDT)"""
    try:
        data = request.json
        order_id = data.get('order_id')
        source = data.get('source')
        
        if source == 'BackMarket':
            if not bm_client.accept_order(order_id):
                return jsonify({'success': False, 'error': 'Errore accettazione ordine'}), 500
        elif source == 'Refurbed':
            if not rf_client.accept_order(order_id):
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
    """API: crea solo DDT e disabilita prodotti"""
    try:
        data = request.json
        order_id = data.get('order_id')
        source = data.get('source')
        
        # Gestione Magento
        if source == 'Magento':
            order = magento_service.get_order_by_id(order_id)
            if not order:
                return jsonify({'success': False, 'error': 'Ordine Magento non trovato'}), 404
            
            # Disabilita prodotti
            for item in order['items']:
                disable_product_on_channels(item['sku'], '', bm_client, rf_client, oct_client)
            
            # Crea DDT
            result = ddt_service.create_ddt_from_order(order)
            if not result['success']:
                return jsonify({'success': False, 'error': result.get('error', 'Errore creazione DDT')}), 500
            
            # Marca ordine come completato
            if order.get('entity_id'):
                magento_service.mark_order_as_completed(order['entity_id'])
            
            return jsonify({
                'success': True,
                'ddt_number': result['ddt_number'],
                'order_id': order_id,
                'message': 'DDT creato con successo'
            })
        
        # Gestione Marketplace (BackMarket, Refurbed, CDiscount)
        all_orders = get_pending_orders(bm_client, rf_client, oct_client)
        order = next((o for o in all_orders if o['order_id'] == order_id and o['source'] == source), None)
        
        if not order:
            return jsonify({'success': False, 'error': 'Ordine non trovato'}), 404
        
        for item in order['items']:
            listing_id = item.get('listing_id', '')
            disable_product_on_channels(item['sku'], listing_id, bm_client, rf_client, oct_client)
        
        result = ddt_service.crea_ddt_da_ordine_marketplace(order, source.lower())
        if not result['success']:
            return jsonify({'success': False, 'error': result.get('error', 'Errore creazione DDT')}), 500
        
        ddt_number = result['ddt_id']
        
        return jsonify({
            'success': True,
            'ddt_number': ddt_number,
            'order_id': order_id,
            'message': 'DDT creato con successo'
        })
        
    except Exception as e:
        logger.error(f"Errore create_ddt_only: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/packlink_csv')
def api_packlink_csv():
    """API: genera CSV Packlink per ordini accettati"""
    try:
        marketplace_orders = get_pending_orders(bm_client, rf_client, oct_client)
        magento_orders = magento_service.get_all_pending_orders()
        
        # Converti ordini Magento nel formato compatibile con CSV
        magento_converted = []
        for order in magento_orders:
            magento_converted.append({
                'order_id': order['order_id'],
                'source': 'Magento',
                'customer_name': f"{order['customer']['name']} {order['customer']['surname']}",
                'customer_email': order['customer']['email'],
                'customer_phone': order['customer']['phone'],
                'address': order['customer']['address'],
                'postal_code': order['customer']['zip'],
                'city': order['customer']['city'],
                'country': order['customer']['country'],
                'total': order['total'],
                'items': order['items']
            })
        
        all_orders = marketplace_orders + magento_converted
        
        rows = []
        for order in all_orders:
            name_parts = order['customer_name'].split()
            first_name = name_parts[0] if name_parts else ''
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
            
            row = {
                'Numero di ordine': f"{order['source']}-{order['order_id']}",
                'nome mittente': 'ReflexMania',
                'Cognome mittente': 'SRL',
                'Azienda mittente': 'ReflexMania SRL',
                'Indirizzo Di Spedizione 1': 'Via primo maggio 16',
                'Indirizzo Di Spedizione 2': '',
                'CAP Spedizione': '60131',
                'citta Spedizione': 'Ancona',
                'provincia di Spedizione': 'AN',
                'Paese di spedizione': 'IT',
                'Telefono spedizione': '0712916347',
                'Email Spedizione': 'info@reflexmania.it',
                'Nome destinatario': first_name,
                'Cognome destinatario': last_name,
                'Azienda destinatario': '',
                'Indirizzo di consegna 1': order['address'],
                'Indirizzo di consegna 2': '',
                'CAP di consegna': order['postal_code'],
                'citta di consegna': order['city'],
                'provincia di consegna': '',
                'Paese di consegna': order['country'],
                'Telefono di consegna': order['customer_phone'],
                'Email di consegna': order['customer_email'],
                'assicurazione': 'NO',
                'Titolo dell\'oggetto': order['items'][0]['name'] if order['items'] else 'Prodotto',
                'Valore merce': str(int(order['total'])),
                'Larghezza oggetto': '20',
                'Altezza oggetto': '25',
                'Lughezza oggetto': '29',
                'Peso dell\'oggetto': '3'
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        
        csv_buffer = BytesIO()
        csv_string = df.to_csv(sep=';', index=False, encoding='utf-8')
        csv_buffer.write(csv_string.encode('utf-8'))
        csv_buffer.seek(0)
        
        filename = f"packlink_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return send_file(
            csv_buffer,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Errore packlink CSV: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API MAGENTO
# ============================================================================

@app.route('/api/magento/orders', methods=['GET'])
def get_magento_orders():
    """API: recupera ordini Magento in processing"""
    try:
        orders = magento_service.get_all_pending_orders()
        return jsonify({
            'success': True,
            'channel': 'magento',
            'count': len(orders),
            'orders': orders
        }), 200
    except Exception as e:
        logger.error(f"Errore recupero ordini Magento: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/magento/orders/<order_id>', methods=['GET'])
def get_magento_order(order_id):
    """API: recupera dettaglio ordine Magento"""
    try:
        order = magento_service.get_order_by_id(order_id)
        if not order:
            return jsonify({'success': False, 'error': f'Ordine {order_id} non trovato'}), 404
        return jsonify({'success': True, 'order': order}), 200
    except Exception as e:
        logger.error(f"Errore recupero ordine Magento {order_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API UNIFIED DASHBOARD
# ============================================================================

@app.route('/api/orders/all', methods=['GET'])
def get_all_orders():
    """API: recupera TUTTI gli ordini da tutti i canali"""
    try:
        # Ordini marketplace
        marketplace_orders = get_pending_orders(bm_client, rf_client, oct_client)
        
        # Ordini Magento - converti nel formato compatibile con la dashboard
        magento_orders = magento_service.get_all_pending_orders()
        magento_converted = []
        
        for order in magento_orders:
            magento_converted.append({
                'order_id': order['order_id'],
                'source': 'Magento',
                'customer_name': f"{order['customer']['name']} {order['customer']['surname']}",
                'customer_email': order['customer']['email'],
                'customer_phone': order['customer']['phone'],
                'address': order['customer']['address'],
                'postal_code': order['customer']['zip'],
                'city': order['customer']['city'],
                'country': order['customer']['country'],
                'total': order['total'],
                'date': order['order_date'],
                'status': order['status'],
                'items': order['items']
            })
        
        all_orders = marketplace_orders + magento_converted
        
        return jsonify({
            'success': True,
            'total_count': len(all_orders),
            'orders': all_orders,
            'channels': {
                'backmarket': len([o for o in all_orders if o['source'] == 'BackMarket']),
                'refurbed': len([o for o in all_orders if o['source'] == 'Refurbed']),
                'cdiscount': len([o for o in all_orders if o['source'] == 'CDiscount']),
                'magento': len(magento_converted)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Errore recupero ordini unificati: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'backmarket': 'ok',
            'refurbed': 'ok',
            'cdiscount': 'ok',
            'magento': 'ok',
            'invoicex': 'ok'
        }
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
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
import requests

# Import moduli locali
from config import (
    BACKMARKET_TOKEN, BACKMARKET_BASE_URL,
    REFURBED_TOKEN, REFURBED_BASE_URL,
    OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID,
    MAGENTO_URL, MAGENTO_TOKEN,
    INVOICEX_CONFIG,
    INVOICEX_API_URL, INVOICEX_API_KEY,
    ANASTASIA_DB_CONFIG, ANASTASIA_URL
)
from clients import BackMarketClient, RefurbishedClient, OctopiaClient
from clients.invoicex_api import InvoiceXAPIClient
from clients.magento_api import MagentoAPIClient
from clients.anastasia_api import AnastasiaClient
from services import (
    get_pending_orders, 
    disable_product_on_channels,
)
from services.ddt_service import DDTService
from services.magento_service import MagentoService
from services.automation_service import AutomationService
from apscheduler.schedulers.background import BackgroundScheduler

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# INIZIALIZZAZIONE FLASK APP
# ============================================================================
app = Flask(__name__)

# Scheduler globale per automazione
scheduler = None

# ============================================================================
# INIZIALIZZAZIONE CLIENTS
# ============================================================================

# Inizializza clients marketplace
bm_client = BackMarketClient(BACKMARKET_TOKEN, BACKMARKET_BASE_URL)
rf_client = RefurbishedClient(REFURBED_TOKEN, REFURBED_BASE_URL)
oct_client = OctopiaClient(OCTOPIA_CLIENT_ID, OCTOPIA_CLIENT_SECRET, OCTOPIA_SELLER_ID)
logger.info("✅ Clients marketplace inizializzati")

# Inizializza Magento client
magento_client = MagentoAPIClient(MAGENTO_URL, MAGENTO_TOKEN)
magento_service = MagentoService(magento_client)
logger.info("✅ MagentoService inizializzato")

# Inizializza InvoiceX API client
invoicex_api_client = InvoiceXAPIClient(
    base_url=INVOICEX_API_URL,
    api_key=INVOICEX_API_KEY
)
logger.info("✅ InvoiceX client inizializzato")

# Inizializza Anastasia client
try:
    anastasia_client = AnastasiaClient(ANASTASIA_DB_CONFIG)
    logger.info("✅ Client Anastasia inizializzato")
except Exception as e:
    logger.error(f"❌ Errore inizializzazione Anastasia: {e}")
    anastasia_client = None

# ============================================================================
# INIZIALIZZAZIONE SERVICES (ORDINE IMPORTANTE!)
# ============================================================================

# DDT Service
ddt_service = DDTService(invoicex_api_client)
logger.info("✅ DDTService inizializzato")

# Order Service (usa la nuova classe)
from services.order_service import OrderService
from utils.order_tracker import OrderTracker

# ✅ CREA TRACKER UNA VOLTA SOLA
order_tracker = OrderTracker()
logger.info("✅ OrderTracker globale inizializzato")

order_service = OrderService(
    backmarket_client=bm_client,
    refurbed_client=rf_client,
    magento_client=magento_client,
    octopia_client=oct_client,
    anastasia_client=anastasia_client,
    order_tracker=order_tracker  # ✅ PASSA IL TRACKER
)
logger.info("✅ OrderService inizializzato")

# Automation Service (DEVE essere l'ULTIMO)
automation_service = AutomationService(
    backmarket_client=bm_client,
    refurbed_client=rf_client,
    magento_service=magento_service,
    ddt_service=ddt_service,
    order_service=order_service
)
logger.info("✅ AutomationService inizializzato")


# ============================================================================
# FUNZIONI UTILITY
# ============================================================================

def generate_tracking_url(carrier: str, tracking_number: str) -> str:
    """Genera l'URL di tracking completo basato sul corriere"""
    carrier = carrier.upper().strip()
    tracking_number = tracking_number.strip()
    
    tracking_urls = {
        'UPS': f'https://www.ups.com/track?loc=en_US&tracknum={tracking_number}',
        'DHL': f'https://mydhl.express.dhl/it/it/tracking.html#/results?id={tracking_number}',
        'BRT': f'https://vas.brt.it/vas/sped_det_show.hsm?chisono={tracking_number}',
        'GLS': f'https://gls-group.eu/IT/it/ricerca-pacchi?match={tracking_number}',
        'TNT': f'https://www.tnt.com/express/it_it/site/tracking.html?searchType=con&cons={tracking_number}',
        'FEDEX': f'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
        'POSTE': f'https://www.poste.it/cerca/index.html#/risultati-spedizioni/{tracking_number}',
        'SDA': f'https://www.sda.it/wps/portal/Servizi_online/dettaglio-spedizione?locale=it&tracing.letteraVettura={tracking_number}'
    }
    
    return tracking_urls.get(carrier, tracking_number)


def _get_order_recommendation(items_info: list, can_accept_any: bool) -> str:
    """Genera raccomandazione in base allo stato degli items"""
    if not items_info:
        return "⚠️ Nessun item trovato"
    
    if can_accept_any:
        acceptable = sum(1 for i in items_info if i['can_accept'])
        return f"✅ Puoi accettare questo ordine ({acceptable} items accettabili)"
    
    all_accepted = all(i['state'] == 'ACCEPTED' for i in items_info)
    if all_accepted:
        return "ℹ️ Ordine già completamente accettato. Puoi procedere alla spedizione."
    
    all_shipped = all(i['state'] == 'SHIPPED' for i in items_info)
    if all_shipped:
        return "📦 Ordine già spedito completamente."
    
    final_states = [i for i in items_info if i['is_final_state']]
    if final_states:
        states = ", ".join(set(i['state'] for i in final_states))
        return f"❌ Impossibile accettare: alcuni items sono in stati finali ({states})"
    
    return "⚠️ Verifica manualmente lo stato degli items"

def get_payment_label(payment_method: str) -> str:
    """Converte codice metodo pagamento in label leggibile"""
    labels = {
        'banktransfer': '🏦 Bonifico',
        'checkmo': '📝 Manuale',
        'purchaseorder': '📋 Ordine Acquisto',
        'cashondelivery': '💵 Contrassegno',
        'free': '🎁 Gratuito',
        'paypal_express': '💳 PayPal',
        'paypal': '💳 PayPal',
        'stripe_payments': '💳 Stripe',
    }
    return labels.get(payment_method, f'💰 {payment_method}')


def send_telegram_order_confirmed(order: dict, ddt_number: str):
    """Notifica Telegram quando ordine pending viene confermato"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        return
    
    try:
        message = (
            f"✅ *Ordine confermato!*\n\n"
            f"🔢 Ordine: `{order.get('order_id', 'N/A')}`\n"
            f"👤 Cliente: {order.get('customer_name', 'N/A')}\n"
            f"💰 Totale: €{order.get('total', 0):.2f}\n"
            f"📄 DDT: `{ddt_number}`\n\n"
            f"_Prodotti disabilitati su tutti i canali_"
        )
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        logger.error(f"Errore notifica Telegram: {e}")


# ============================================================================
# API ANASTASIA TICKETS
# ============================================================================

@app.route('/api/tickets/stats')
def api_tickets_stats():
    """API: Statistiche ticket Anastasia"""
    try:
        if not anastasia_client:
            return jsonify({'error': 'Client Anastasia non disponibile'}), 503
        
        stats = anastasia_client.get_ticket_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Errore API tickets stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tickets/open')
def api_tickets_open():
    """API: Lista ultimi ticket aperti"""
    try:
        if not anastasia_client:
            return jsonify({'error': 'Client Anastasia non disponibile'}), 503
        
        limit = request.args.get('limit', 10, type=int)
        tickets = anastasia_client.get_open_tickets(limit=limit)
        
        return jsonify({
            'success': True,
            'count': len(tickets),
            'tickets': tickets
        })
    except Exception as e:
        logger.error(f"Errore API tickets open: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tickets/closed-today')
def api_tickets_closed_today():
    """API: Lista ticket chiusi oggi"""
    try:
        if not anastasia_client:
            return jsonify({'error': 'Client Anastasia non disponibile'}), 503
        
        tickets = anastasia_client.get_recent_closed_tickets(limit=5)
        
        return jsonify({
            'success': True,
            'count': len(tickets),
            'tickets': tickets
        })
    except Exception as e:
        logger.error(f"Errore API tickets closed today: {e}")
        return jsonify({'error': str(e)}), 500
@app.route('/')
def dashboard():
    """Dashboard principale con tabella ordini + widget Anastasia"""
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ReflexMania - Gestione Unificata</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            
            .container { 
                max-width: 1600px; 
                margin: 0 auto; 
            }
            
            .header {
                background: rgba(255,255,255,0.95);
                backdrop-filter: blur(10px);
                padding: 30px;
                border-radius: 16px;
                margin-bottom: 20px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }
            
            .header h1 { 
                color: #333; 
                font-size: 32px;
                margin-bottom: 10px;
                font-weight: 700;
            }
            
            .header-subtitle {
                color: #666;
                font-size: 14px;
            }
            
            .main-grid {
                display: grid;
                grid-template-columns: 1fr 380px;
                gap: 20px;
                margin-bottom: 20px;
            }
            
            @media (max-width: 1200px) {
                .main-grid {
                    grid-template-columns: 1fr;
                }
            }
            
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .stat-card {
                background: rgba(255,255,255,0.95);
                backdrop-filter: blur(10px);
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 4px 16px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }
            
            .stat-card:hover {
                transform: translateY(-4px);
                box-shadow: 0 8px 24px rgba(0,0,0,0.15);
            }
            
            .stat-card h3 {
                color: #666;
                font-size: 12px;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                font-weight: 600;
            }
            
            .stat-card .number {
                font-size: 36px;
                font-weight: 700;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .orders-section {
                background: rgba(255,255,255,0.95);
                backdrop-filter: blur(10px);
                border-radius: 16px;
                padding: 25px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }
            
            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            
            .section-header h2 {
                font-size: 24px;
                color: #333;
                font-weight: 700;
            }
            
            .actions {
                display: flex;
                gap: 10px;
            }
            
            .btn {
                padding: 10px 20px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.3s;
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }
            
            .btn-primary { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; 
            }
            
            .btn-primary:hover { 
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }
            
            .btn-success { 
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                color: white; 
            }
            
            .btn-success:hover { 
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(17, 153, 142, 0.4);
            }
            
            .btn-small { 
                padding: 6px 12px; 
                font-size: 12px; 
            }
            
            table {
                width: 100%;
                background: white;
                border-radius: 12px;
                overflow: hidden;
            }
            
            th {
                background: #f8f9fa;
                padding: 15px;
                text-align: left;
                font-weight: 600;
                color: #333;
                font-size: 13px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                border-bottom: 2px solid #e9ecef;
            }
            
            td {
                padding: 15px;
                border-bottom: 1px solid #f1f3f5;
            }
            
            tr:hover { 
                background: #f8f9fa; 
            }
            
            .badge {
                display: inline-block;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .badge-backmarket { background: #e3f2fd; color: #1976d2; }
            .badge-refurbed { background: #f3e5f5; color: #7b1fa2; }
            .badge-cdiscount { background: #fff3e0; color: #f57c00; }
            .badge-magento { background: #ffe0e0; color: #c62828; }
            .badge-accepted { background: #d4edda; color: #155724; }
            .badge-pending { background: #fff3cd; color: #856404; }
            
            .anastasia-widget {
                background: rgba(255,255,255,0.95);
                backdrop-filter: blur(10px);
                border-radius: 16px;
                padding: 25px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                height: fit-content;
                position: sticky;
                top: 20px;
            }
            
            .widget-header {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
            }
            
            .widget-header h2 {
                font-size: 24px;
                color: #333;
                font-weight: 700;
            }
            
            .widget-icon {
                font-size: 32px;
            }
            
            .ticket-stats {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 12px;
                margin-bottom: 20px;
            }
            
            .ticket-stat {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 10px;
                text-align: center;
            }
            
            .ticket-stat .label {
                font-size: 11px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
                font-weight: 600;
            }
            
            .ticket-stat .value {
                font-size: 32px;
                font-weight: 700;
            }
            
            .ticket-stat.open .value { color: #dc3545; }
            .ticket-stat.closed .value { color: #28a745; }
            
            .ticket-list {
                margin-bottom: 20px;
            }
            
            .ticket-item {
                background: #f8f9fa;
                padding: 12px;
                border-radius: 8px;
                margin-bottom: 10px;
                transition: all 0.2s;
                cursor: pointer;
            }
            
            .ticket-item:hover {
                background: #e9ecef;
                transform: translateX(4px);
            }
            
            .ticket-item .ticket-title {
                font-weight: 600;
                color: #333;
                font-size: 14px;
                margin-bottom: 4px;
                display: block;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            
            .ticket-item .ticket-meta {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 12px;
                color: #666;
            }
            
            .ticket-item .customer-name {
                font-weight: 500;
            }
            
            .ticket-item .ticket-time {
                font-size: 11px;
                color: #999;
            }
            
            .btn-anastasia {
                width: 100%;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                color: white;
                padding: 14px;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                font-weight: 700;
                cursor: pointer;
                transition: all 0.3s;
                text-align: center;
                text-decoration: none;
                display: block;
            }
            
            .btn-anastasia:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(245, 87, 108, 0.4);
            }
            
            .empty-state {
                text-align: center;
                padding: 40px 20px;
                color: #999;
            }
            
            .empty-state-icon {
                font-size: 48px;
                margin-bottom: 10px;
                opacity: 0.3;
            }
            
            #loading {
                display: none;
                text-align: center;
                padding: 20px;
                color: #666;
                background: rgba(255,255,255,0.9);
                border-radius: 10px;
                margin: 20px 0;
            }
            
            .spinner {
                border: 3px solid #f3f3f3;
                border-top: 3px solid #667eea;
                border-radius: 50%;
                width: 30px;
                height: 30px;
                animation: spin 1s linear infinite;
                margin: 0 auto 10px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .error-widget {
                background: #fff3cd;
                border: 2px solid #ffc107;
                border-radius: 10px;
                padding: 15px;
                margin-bottom: 15px;
                color: #856404;
                font-size: 13px;
            }
            .pending-section {
                background: rgba(255,255,255,0.95);
                backdrop-filter: blur(10px);
                border-radius: 16px;
                padding: 25px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                border-left: 4px solid #ffc107;
                margin-top: 30px;
            }
            
            .pending-section h2 { color: #856404; }
            
            .badge-bonifico { background: #e3f2fd; color: #1565c0; }
            .badge-manuale { background: #fff3e0; color: #e65100; }
            
            .waiting-time {
                font-size: 12px;
                padding: 4px 8px;
                border-radius: 4px;
                background: #fff3cd;
                color: #856404;
            }
            
            .waiting-time.warning { background: #f8d7da; color: #721c24; }
            
            .btn-confirm {
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                color: white;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 ReflexMania - Gestione Unificata</h1>
                <div class="header-subtitle">Dashboard ordini marketplace + ticket valutazioni</div>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <h3>📦 Ordini Totali</h3>
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
                <div class="stat-card">
                    <h3>🎫 Ticket Aperti</h3>
                    <div class="number" id="tickets-open-header">-</div>
                </div>
            </div>
            
            <div class="main-grid">
                <div class="orders-section">
                    <div class="section-header">
                        <h2>📦 Ordini Marketplace</h2>
                        <div class="actions">
                            <button class="btn btn-primary" onclick="refreshOrders()">
                                🔄 Aggiorna
                            </button>
                            <button class="btn btn-success" onclick="downloadCSV()">
                                📥 CSV Packlink
                            </button>
                        </div>
                    </div>
                    
                    <div id="loading">
                        <div class="spinner"></div>
                        Caricamento in corso...
                    </div>
                    
                    <div style="overflow-x: auto;">
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
                </div>
                <div class="anastasia-widget">
                    <div class="widget-header">
                        <span class="widget-icon">🎫</span>
                        <h2>Ticket Anastasia</h2>
                    </div>
                    
                    <div id="anastasia-error" class="error-widget" style="display: none;">
                        ⚠️ Impossibile connettersi al sistema Anastasia
                    </div>
                    
                    <div class="ticket-stats">
                        <div class="ticket-stat open">
                            <div class="label">Aperti</div>
                            <div class="value" id="tickets-open">0</div>
                        </div>
                        <div class="ticket-stat closed">
                            <div class="label">Chiusi Oggi</div>
                            <div class="value" id="tickets-closed-today">0</div>
                        </div>
                    </div>
                    
                    <div class="ticket-list" id="ticket-list">
                        <div class="empty-state">
                            <div class="empty-state-icon">🔭</div>
                            <div>Caricamento ticket...</div>
                        </div>
                    </div>
                    
                    <a href="https://anastasia.reflexmania.com" target="_blank" class="btn-anastasia">
                        Apri Anastasia →
                    </a>
                </div>
                <!-- Ordini in attesa pagamento -->
                    <div class="pending-section" id="pending-section" style="display: none;">
                        <div class="section-header">
                            <h2>⏳ Ordini in Attesa Pagamento</h2>
                            <div class="actions">
                                <button class="btn btn-primary" onclick="refreshPendingOrders()">🔄 Aggiorna</button>
                            </div>
                        </div>
                        
                        <div style="overflow-x: auto;">
                            <table id="pending-table">
                                <thead>
                                    <tr>
                                        <th>Ordine</th>
                                        <th>Cliente</th>
                                        <th>Prodotto</th>
                                        <th>Importo</th>
                                        <th>Pagamento</th>
                                        <th>In Attesa Da</th>
                                        <th>Azioni</th>
                                    </tr>
                                </thead>
                                <tbody id="pending-body">
                                    <tr><td colspan="7" style="text-align: center;">Caricamento...</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
            </div>
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
                        refreshPendingOrders();
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
                    tbody.innerHTML = '<tr><td colspan="9" class="empty-state"><div class="empty-state-icon">✅</div><div>Nessun ordine pendente</div></td></tr>';
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
                        const entityId = order.entity_id || 0;
                        actionButtons = `
                            <button class="btn btn-success btn-small" 
                                    onclick="createDDTOnly('${order.order_id}', '${order.source}')" 
                                    style="margin-right: 5px;">
                                Crea DDT
                            </button>
                            <button class="btn btn-primary btn-small" 
                                    onclick="shipMagentoOrder('${order.order_id}', ${entityId})" 
                                    style="background: #17a2b8;">
                                📦 Spedito
                            </button>
                        `;
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
                    
                    return `<tr>
                        <td><strong>${order.order_id}</strong></td>
                        <td><span class="badge ${badgeClass}">${order.source}</span></td>
                        <td>${order.customer_name}</td>
                        <td>${productInfo}</td>
                        <td><code>${skuInfo}</code></td>
                        <td>${date}</td>
                        <td><strong>€${order.total.toFixed(2)}</strong></td>
                        <td>${statusBadge}</td>
                        <td>${actionButtons}</td>
                    </tr>`;
                }).join('');
            }
            
            function shipMagentoOrder(orderNumber, entityId) {
                const trackingNumber = prompt(`Inserisci il numero di tracking per l'ordine Magento ${orderNumber}:`);
                
                if (!trackingNumber || trackingNumber.trim() === '') {
                    alert('Numero di tracking obbligatorio');
                    return;
                }
                
                const carrier = prompt(`Inserisci il corriere (BRT, UPS, DHL, FEDEX, TNT, GLS):`, 'BRT');
                
                if (!carrier || carrier.trim() === '') {
                    alert('Corriere obbligatorio');
                    return;
                }
                
                const validCarriers = ['BRT', 'UPS', 'DHL', 'FEDEX', 'TNT', 'GLS'];
                const carrierUpper = carrier.trim().toUpperCase();
                
                if (!validCarriers.includes(carrierUpper)) {
                    alert(`Corriere non valido. Usa uno tra: ${validCarriers.join(', ')}`);
                    return;
                }
                
                if (!confirm(`Confermi la spedizione dell'ordine Magento ${orderNumber}?\\n\\nTracking: ${trackingNumber}\\nCorriere: ${carrierUpper}`)) {
                    return;
                }
                
                document.getElementById('loading').style.display = 'block';
                
                fetch('/api/magento/ship_order', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        order_id: orderNumber,
                        entity_id: entityId,
                        tracking_number: trackingNumber,
                        carrier: carrierUpper
                    })
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    document.getElementById('loading').style.display = 'none';
                    
                    if (data.success) {
                        alert(`✅ Ordine Magento ${orderNumber} spedito con successo!\\n\\n` +
                              `Shipment ID: ${data.shipment_id}\\n` +
                              `Tracking: ${data.tracking_number}\\n` +
                              `Corriere: ${data.carrier}\\n\\n` +
                              `I prodotti sono stati disabilitati su tutti i marketplace.`);
                        refreshOrders();
                    } else {
                        alert('❌ Errore: ' + (data.error || 'Errore sconosciuto'));
                    }
                })
                .catch(err => {
                    document.getElementById('loading').style.display = 'none';
                    alert('❌ Errore di connessione: ' + err.message);
                    console.error('Errore shipment:', err);
                });
            }
            
            function markAsShipped(orderId, source) {
                const trackingNumber = prompt(`Inserisci il numero di tracking per l'ordine ${orderId}:`);
                
                if (!trackingNumber || trackingNumber.trim() === '') {
                    alert('Numero di tracking obbligatorio');
                    return;
                }
                
                let carrier = 'BRT';
                let trackingUrl = '';
                
                if (source === 'Refurbed') {
                    carrier = prompt(
                        `Seleziona il corriere per ${orderId}:\\n\\n` +
                        `Digita uno tra:\\n` +
                        `- UPS\\n` +
                        `- DHL\\n` +
                        `- BRT (default)\\n` +
                        `- GLS\\n` +
                        `- TNT\\n` +
                        `- FEDEX\\n` +
                        `- POSTE\\n` +
                        `- SDA`,
                        'BRT'
                    );
                    
                    if (!carrier || carrier.trim() === '') {
                        carrier = 'BRT';
                    }
                    
                    carrier = carrier.toUpperCase().trim();
                    
                    const validCarriers = ['UPS', 'DHL', 'BRT', 'GLS', 'TNT', 'FEDEX', 'POSTE', 'SDA'];
                    if (!validCarriers.includes(carrier)) {
                        alert(`Corriere non valido. Usa uno tra: ${validCarriers.join(', ')}`);
                        return;
                    }
                } else {
                    trackingUrl = prompt(`Inserisci l'URL di tracking (opzionale):`) || '';
                }
                
                const confirmMsg = source === 'Refurbed' 
                    ? `Confermi la spedizione dell'ordine ${orderId}?\\n\\nTracking: ${trackingNumber}\\nCorriere: ${carrier}`
                    : `Confermi la spedizione dell'ordine ${orderId}?\\n\\nTracking: ${trackingNumber}`;
                
                if (!confirm(confirmMsg)) {
                    return;
                }
                
                document.getElementById('loading').style.display = 'block';
                
                const requestBody = {
                    order_id: orderId,
                    source: source,
                    tracking_number: trackingNumber
                };
                
                if (source === 'Refurbed') {
                    requestBody.carrier = carrier;
                } else if (trackingUrl) {
                    requestBody.tracking_url = trackingUrl;
                }
                
                fetch('/api/mark_shipped', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(requestBody)
                })
                .then(response => {
                    return response.json().then(data => ({
                        ok: response.ok,
                        data: data
                    }));
                })
                .then(result => {
                    document.getElementById('loading').style.display = 'none';
                    
                    if (result.ok) {
                        let message = `✅ Ordine ${orderId} marcato come spedito!\\n\\nTracking: ${trackingNumber}`;
                        
                        if (result.data.tracking_url) {
                            message += `\\n\\nURL tracking: ${result.data.tracking_url}`;
                        }
                        
                        if (result.data.carrier) {
                            message += `\\nCorriere: ${result.data.carrier}`;
                        }
                        
                        if (result.data.items_shipped) {
                            message += `\\n\\nItems spediti: ${result.data.items_shipped}`;
                        }
                        
                        message += '\\n\\nTracking comunicato al marketplace.';
                        
                        alert(message);
                        refreshOrders();
                    } else {
                        alert(`❌ Errore: ${result.data.error || 'Errore sconosciuto'}`);
                    }
                })
                .catch(err => {
                    document.getElementById('loading').style.display = 'none';
                    alert(`❌ Errore di connessione: ${err.message}`);
                    console.error(err);
                });
            }
            
            function acceptOrderOnly(orderId, source) {
                if (!confirm(`Confermi l'accettazione dell'ordine ${orderId} su ${source}?`)) {
                    return;
                }
                
                document.getElementById('loading').style.display = 'block';
                
                fetch('/api/accept_order_only', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        order_id: orderId,
                        source: source
                    })
                })
                .then(response => {
                    return response.json().then(data => ({
                        ok: response.ok,
                        status: response.status,
                        data: data
                    }));
                })
                .then(result => {
                    document.getElementById('loading').style.display = 'none';
                    
                    if (result.ok) {
                        const message = result.data.message || `Ordine ${orderId} accettato con successo`;
                        alert(`✅ ${message}\\n\\nLa tabella ordini verrà aggiornata tra 3 secondi...`);
                        
                        setTimeout(() => {
                            console.log('🔄 Refresh automatico dopo accettazione...');
                            refreshOrders();
                        }, 3000);
                    } else {
                        const errorMsg = result.data.error || 'Errore sconosciuto';
                        const details = result.data.details || '';
                        
                        let fullMessage = `❌ Errore durante l'accettazione:\\n\\n${errorMsg}`;
                        if (details) {
                            fullMessage += `\\n\\n${details}`;
                        }
                        
                        alert(fullMessage);
                        console.error('Errore accettazione:', result.data);
                    }
                })
                .catch(err => {
                    document.getElementById('loading').style.display = 'none';
                    alert(`❌ Errore di connessione:\\n\\n${err.message}`);
                    console.error('Errore fetch:', err);
                });
            }
            
            function createDDTOnly(orderId, source) {
                if (!confirm(`Confermi la creazione del DDT per l'ordine ${orderId}?\\n\\nQuesto:\\n- Disabiliterà i prodotti su tutti i canali\\n- Creerà il DDT su InvoiceX`)) return;
                document.getElementById('loading').style.display = 'block';
                fetch('/api/create_ddt_only', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, source: source}) })
                .then(r => r.json()).then(data => { if (data.success) { alert(`DDT creato con successo!\\n\\nNumero DDT: ${data.ddt_number}\\n\\nL'ordine è ora pronto per la spedizione.`); refreshOrders(); } else { alert('Errore: ' + data.error); document.getElementById('loading').style.display = 'none'; } })
                .catch(err => { alert('Errore di connessione'); console.error(err); document.getElementById('loading').style.display = 'none'; });
            }
            
            function downloadCSV() { window.location.href = '/api/packlink_csv'; }
            
            function refreshTickets() {
                fetch('/api/tickets/stats')
                    .then(r => r.json())
                    .then(data => {
                        if (data.error) {
                            document.getElementById('anastasia-error').style.display = 'block';
                            return;
                        }
                        document.getElementById('anastasia-error').style.display = 'none';
                        document.getElementById('tickets-open').textContent = data.open || 0;
                        document.getElementById('tickets-closed-today').textContent = data.today_closed || 0;
                        document.getElementById('tickets-open-header').textContent = data.open || 0;
                    })
                    .catch(err => {
                        console.error('Errore stats Anastasia:', err);
                        document.getElementById('anastasia-error').style.display = 'block';
                    });
                
                fetch('/api/tickets/open?limit=5')
                    .then(r => r.json())
                    .then(data => {
                        if (data.error || !data.tickets) {
                            return;
                        }
                        
                        const list = document.getElementById('ticket-list');
                        
                        if (data.tickets.length === 0) {
                            list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">✅</div><div>Nessun ticket aperto</div></div>';
                            return;
                        }
                        
                        list.innerHTML = data.tickets.map(ticket => `
                            <div class="ticket-item" onclick="window.open('https://anastasia.reflexmania.com', '_blank')">
                                <span class="ticket-title">${ticket.title}</span>
                                <div class="ticket-meta">
                                    <span class="customer-name">👤 ${ticket.customer_name}</span>
                                    <span class="ticket-time">${ticket.last_update}</span>
                                </div>
                            </div>
                        `).join('');
                    })
                    .catch(err => {
                        console.error('Errore lista Anastasia:', err);
                    });
            }
            
            refreshOrders();
            refreshTickets();
            
            setInterval(refreshOrders, 120000);
            setInterval(refreshTickets, 30000);
        let pendingOrders = [];
            
            function refreshPendingOrders() {
                fetch('/api/orders/pending_magento')
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            pendingOrders = data.orders;
                            renderPendingOrders();
                            document.getElementById('pending-section').style.display = 
                                pendingOrders.length > 0 ? 'block' : 'none';
                        }
                    })
                    .catch(err => console.error('Errore pending:', err));
            }
            
            function renderPendingOrders() {
                const tbody = document.getElementById('pending-body');
                
                if (pendingOrders.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">✅ Nessun ordine in attesa</td></tr>';
                    return;
                }
                
                tbody.innerHTML = pendingOrders.map(order => {
                    let productInfo = order.items?.[0]?.name || 'N/A';
                    if (order.items?.length > 1) productInfo += ` (+${order.items.length - 1})`;
                    
                    const pm = order.payment_method || '';
                    let paymentBadge = pm.includes('banktransfer') 
                        ? '<span class="badge badge-bonifico">🏦 Bonifico</span>'
                        : `<span class="badge badge-pending">${order.payment_label || pm}</span>`;
                    
                    const waiting = order.waiting_time || {};
                    const waitingClass = waiting.days >= 3 ? 'warning' : '';
                    
                    return `<tr>
                        <td><strong>${order.order_id}</strong></td>
                        <td>${order.customer_name}</td>
                        <td>${productInfo}</td>
                        <td><strong>€${order.total.toFixed(2)}</strong></td>
                        <td>${paymentBadge}</td>
                        <td><span class="waiting-time ${waitingClass}">${waiting.label || 'N/A'}</span></td>
                        <td><button class="btn btn-confirm btn-small" onclick="confirmPendingOrder(${order.entity_id}, '${order.order_id}')">✅ Conferma</button></td>
                    </tr>`;
                }).join('');
            }
            
            function confirmPendingOrder(entityId, orderId) {
                if (!confirm(`Confermi il pagamento per ordine ${orderId}?\\n\\nQuesto creerà il DDT e disabiliterà i prodotti.`)) return;
                
                document.getElementById('loading').style.display = 'block';
                
                fetch(`/api/pending_magento/confirm/${entityId}`, { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        document.getElementById('loading').style.display = 'none';
                        if (data.success) {
                            alert(`✅ Ordine ${orderId} confermato!\\nDDT: ${data.ddt_number}`);
                            refreshPendingOrders();
                            refreshOrders();
                        } else {
                            alert('❌ Errore: ' + data.error);
                        }
                    })
                    .catch(err => {
                        document.getElementById('loading').style.display = 'none';
                        alert('❌ Errore: ' + err.message);
                    });
            }
            
            // Carica pending all'avvio
            refreshPendingOrders();    
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

@app.route('/api/orders/pending_magento')
def api_pending_magento_orders():
    """API: Ordini Magento in attesa di pagamento"""
    try:
        orders = order_service.get_magento_waiting_payment_orders()
        
        from services.order_service import calculate_waiting_time
        for order in orders:
            waiting = calculate_waiting_time(order.get('waiting_since', ''))
            order['waiting_time'] = waiting
            order['payment_label'] = get_payment_label(order.get('payment_method', ''))
        
        return jsonify({
            'success': True,
            'count': len(orders),
            'orders': orders
        })
    except Exception as e:
        logger.error(f"Errore API pending magento: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pending_magento/confirm/<int:entity_id>', methods=['POST'])
def confirm_pending_magento(entity_id):
    """Conferma ordine pending e avvia flusso DDT"""
    try:
        logger.info(f"🔄 Conferma ordine pending entity_id={entity_id}")
        
        result = order_service.confirm_magento_pending_order(entity_id)
        if not result['success']:
            return jsonify(result), 400
        
        order = result['order']
        order_id = order['order_id']
        
        # Crea DDT
        ddt_result = ddt_service.crea_ddt_da_ordine_marketplace(order, 'magento')
        if not ddt_result.get('success'):
            return jsonify({
                'success': False,
                'error': f"Ordine confermato ma errore DDT: {ddt_result.get('error')}",
                'order_confirmed': True
            }), 500
        
        ddt_number = ddt_result.get('ddt_id', 'N/A')
        
        # Disabilita prodotti
        for item in order.get('items', []):
            sku = item.get('sku', '')
            if sku:
                order_service.disable_product_all_channels(sku)
        
        # Notifica Telegram
        send_telegram_order_confirmed(order, ddt_number)
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'ddt_number': ddt_number,
            'message': f'Ordine #{order_id} confermato, DDT {ddt_number} creato'
        })
        
    except Exception as e:
        logger.error(f"Errore conferma pending: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
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
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📦 Richiesta spedizione ordine")
        logger.info(f"   Order ID: {order_id}")
        logger.info(f"   Source: {source}")
        logger.info(f"   Tracking: {tracking_number}")
        logger.info(f"{'='*60}\n")
        
        # BackMarket
        if source == 'BackMarket':
            final_tracking = tracking_url if tracking_url else tracking_number
            
            if not bm_client.mark_as_shipped(order_id, tracking_number, final_tracking):
                return jsonify({'success': False, 'error': 'Errore comunicazione tracking'}), 500
            
            return jsonify({
                'success': True,
                'order_id': order_id,
                'tracking_number': tracking_number,
                'message': 'Ordine marcato come spedito su BackMarket'
            })
        
        # Refurbed
        elif source == 'Refurbed':
            carrier = data.get('carrier', 'BRT').upper()
            
            if not tracking_url:
                tracking_url = generate_tracking_url(carrier, tracking_number)
                logger.info(f"🔗 URL generato: {tracking_url}")
            
            # Recupera items DIRETTAMENTE da Refurbed API
            logger.info(f"🔍 Recupero items per ordine {order_id} da Refurbed API...")
            
            items_url = f"{rf_client.base_url}/refb.merchant.v1.OrderItemService/ListOrderItemsByOrder"
            items_body = {"order_id": order_id}
            
            import requests
            items_response = requests.post(
                items_url,
                headers=rf_client.headers,
                json=items_body,
                timeout=30
            )
            
            if items_response.status_code != 200:
                return jsonify({
                    'success': False,
                    'error': f'Impossibile recuperare items ordine: HTTP {items_response.status_code}'
                }), 500
            
            items_data = items_response.json()
            items = items_data.get('order_items', [])
            
            if not items:
                return jsonify({'success': False, 'error': 'Nessun item trovato per questo ordine'}), 404
            
            logger.info(f"✅ Trovati {len(items)} items per ordine {order_id}")
            
            success_count = 0
            errors = []
            
            for item in items:
                item_id = item.get('id')  # ← Usa 'id' direttamente dall'API Refurbed
                if item_id:
                    success, message = rf_client.mark_as_shipped(item_id, tracking_url)
                    if success:
                        success_count += 1
                        logger.info(f"✅ Item {item_id} spedito")
                    else:
                        errors.append(f"Item {item_id}: {message}")
                        logger.error(f"❌ Item {item_id}: {message}")
            
            if success_count == 0:
                return jsonify({
                    'success': False, 
                    'error': f"Nessun item spedito. Errori: {'; '.join(errors)}"
                }), 500
            
            return jsonify({
                'success': True,
                'order_id': order_id,
                'tracking_number': tracking_number,
                'tracking_url': tracking_url,
                'carrier': carrier,
                'items_shipped': success_count,
                'message': f'{success_count} items spediti su Refurbed'
            })
        
        # Magento (STESSO LIVELLO di "elif source == 'Refurbed'")
        elif source == 'Magento':
            order = magento_service.get_order_by_id(order_id)
            if order and order.get('entity_id'):
                magento_service.mark_order_as_completed(order['entity_id'])
            
            return jsonify({
                'success': True,
                'order_id': order_id,
                'tracking_number': tracking_number,
                'message': 'Ordine marcato come spedito'
            })
        
        else:
            return jsonify({
                'success': False,
                'error': f'Marketplace {source} non supportato'
            }), 400
        
    except Exception as e:
        logger.error(f"❌ Errore mark_shipped: {e}")
        logger.exception(e)
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/accept_order_only', methods=['POST'])
def api_accept_order_only():
    """API: accetta solo l'ordine sul marketplace (senza DDT)"""
    try:
        data = request.json
        order_id = data.get('order_id')
        source = data.get('source')
        
        if not order_id or not source:
            return jsonify({
                'success': False,
                'error': 'Parametri mancanti: order_id e source richiesti'
            }), 400
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📨 Richiesta accettazione ordine")
        logger.info(f"   Order ID: {order_id}")
        logger.info(f"   Source: {source}")
        logger.info(f"{'='*60}\n")
        
        # BackMarket
        if source == 'BackMarket':
            success = bm_client.accept_order(order_id)
            
            if not success:
                logger.error(f"❌ BackMarket: Accettazione fallita per {order_id}")
                return jsonify({
                    'success': False, 
                    'error': 'Impossibile accettare l\'ordine su BackMarket. Verifica lo stato dell\'ordine.'
                }), 500
            
            logger.info(f"✅ BackMarket: Ordine {order_id} accettato")
            return jsonify({
                'success': True,
                'order_id': order_id,
                'source': source,
                'message': f'✅ Ordine {order_id} accettato su BackMarket'
            })
        
        # Refurbed
        elif source == 'Refurbed':
            success, message = rf_client.accept_order(order_id)
            
            if not success:
                logger.error(f"❌ Refurbed: {message}")
                return jsonify({
                    'success': False, 
                    'error': message,
                    'order_id': order_id,
                    'source': source,
                    'details': 'Verifica lo stato degli order items. Gli ordini possono essere accettati solo se in stato NEW o PENDING.'
                }), 500
            
            logger.info(f"✅ Refurbed: {message}")
            return jsonify({
                'success': True,
                'order_id': order_id,
                'source': source,
                'message': message
            })
        
        else:
            logger.warning(f"⚠️ Marketplace {source} non supporta accettazione ordini")
            return jsonify({
                'success': False,
                'error': f'Il marketplace {source} non supporta l\'accettazione ordini tramite questa funzione'
            }), 400
        
    except Exception as e:
        logger.error(f"❌ Errore imprevisto in accept_order_only: {e}")
        logger.exception(e)
        return jsonify({
            'success': False, 
            'error': f'Errore del server: {str(e)}',
            'type': 'server_error'
        }), 500


@app.route('/api/create_ddt_only', methods=['POST'])
def api_create_ddt_only():
    """API: crea solo DDT e disabilita prodotti"""
    try:
        data = request.json
        order_id = data.get('order_id')
        source = data.get('source')
        
        if source == 'Magento':
            order = magento_service.get_order_by_id(order_id)
            if not order:
                return jsonify({'success': False, 'error': 'Ordine Magento non trovato'}), 404
            
            for item in order['items']:
                disable_product_on_channels(item['sku'], '', bm_client, rf_client, oct_client, magento_client)
            
            result = ddt_service.crea_ddt_da_ordine_marketplace(order, 'magento')
            if not result['success']:
                return jsonify({'success': False, 'error': result.get('error', 'Errore creazione DDT')}), 500
            
            if order.get('entity_id'):
                magento_service.mark_order_as_completed(order['entity_id'])
            
            return jsonify({
                'success': True,
                'ddt_number': result['ddt_id'],
                'order_id': order_id,
                'message': 'DDT creato con successo'
            })
        
        all_orders = get_pending_orders(bm_client, rf_client, oct_client)
        order = next((o for o in all_orders if o['order_id'] == order_id and o['source'] == source), None)
        
        if not order:
            return jsonify({'success': False, 'error': 'Ordine non trovato'}), 404
        
        for item in order['items']:
            listing_id = item.get('listing_id', '')
            disable_product_on_channels(item['sku'], listing_id, bm_client, rf_client, oct_client, magento_client)
        
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


@app.route('/api/magento/ship_order', methods=['POST'])
def ship_magento_order():
    """API: Crea shipment per ordine Magento con tracking"""
    try:
        data = request.json
        order_id = data.get('order_id')
        entity_id = data.get('entity_id')
        tracking_number = data.get('tracking_number')
        carrier_name = data.get('carrier', 'BRT').upper()
        
        if not tracking_number or not tracking_number.strip():
            return jsonify({'success': False, 'error': 'Numero di tracking obbligatorio'}), 400
        
        if not entity_id:
            return jsonify({'success': False, 'error': 'Entity ID ordine mancante'}), 400
        
        carrier_code = magento_client.get_carrier_code(carrier_name)
        
        logger.info(f"📦 Creazione shipment Magento ordine #{order_id} (entity_id: {entity_id})")
        logger.info(f"🚚 Tracking: {tracking_number} - Corriere: {carrier_name} ({carrier_code})")
        
        shipment_id = magento_client.create_shipment(
            order_id=entity_id,
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_title=carrier_name
        )
        
        if shipment_id:
            order = magento_service.get_order_by_id(order_id)
            if order and order.get('items'):
                for item in order['items']:
                    sku = item.get('sku')
                    if sku:
                        logger.info(f"🔧 Disabilitazione prodotto {sku} su tutti i marketplace")
                        disable_product_on_channels(
                            sku, '', bm_client, rf_client, oct_client, magento_client
                        )
            
            return jsonify({
                'success': True,
                'shipment_id': shipment_id,
                'order_id': order_id,
                'tracking_number': tracking_number,
                'carrier': carrier_name,
                'message': f'✅ Ordine {order_id} spedito con successo'
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Errore creazione shipment su Magento'}), 500
            
    except Exception as e:
        logger.error(f"❌ Errore ship_magento_order: {str(e)}")
        logger.exception(e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders/all', methods=['GET'])
def get_all_orders():
    """API: recupera TUTTI gli ordini da tutti i canali"""
    try:
        marketplace_orders = get_pending_orders(bm_client, rf_client, oct_client)
        magento_orders = magento_service.get_all_pending_orders()
        magento_converted = []
        
        for order in magento_orders:
            magento_converted.append({
                'order_id': order['order_id'],
                'entity_id': order.get('entity_id', 0),
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
# DEBUG ENDPOINTS
# ============================================================================

@app.route('/api/debug/refurbed/<order_id>')
def debug_refurbed_order(order_id):
    """Endpoint debug per analizzare un ordine Refurbed"""
    try:
        logger.info(f"🔍 Debug richiesto per ordine Refurbed {order_id}")
        
        order = rf_client.get_order_details(order_id)
        
        if not order:
            return jsonify({
                'success': False,
                'error': 'Ordine non trovato o errore API Refurbed',
                'order_id': order_id
            }), 404
        
        list_url = f"{rf_client.base_url}/refb.merchant.v1.OrderItemService/ListOrderItemsByOrder"
        list_body = {"order_id": order_id}
        
        response = requests.post(list_url, headers=rf_client.headers, json=list_body, timeout=30)
        
        items_info = []
        can_accept_any = False
        
        if response.status_code == 200:
            items_data = response.json()
            items = items_data.get('order_items', [])
            
            state_transitions = {
                'NEW': ['REJECTED', 'CANCELLED', 'ACCEPTED'],
                'PENDING': ['REJECTED', 'CANCELLED', 'ACCEPTED'],
                'ACCEPTED': ['CANCELLED', 'SHIPPED'],
                'REJECTED': [],
                'CANCELLED': [],
                'SHIPPED': ['RETURNED'],
                'RETURNED': []
            }
            
            for item in items:
                current_state = item.get('state', 'UNKNOWN')
                possible_transitions = state_transitions.get(current_state, [])
                can_accept = 'ACCEPTED' in possible_transitions
                
                if can_accept:
                    can_accept_any = True
                
                items_info.append({
                    'id': item.get('id'),
                    'sku': item.get('sku'),
                    'state': current_state,
                    'name': item.get('name', 'N/A'),
                    'quantity': item.get('quantity', 0),
                    'can_accept': can_accept,
                    'possible_transitions': possible_transitions,
                    'is_final_state': len(possible_transitions) == 0,
                    'shipment_status': item.get('shipment_status'),
                    'tracking_link': item.get('parcel_tracking_link')
                })
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'order_state': order.get('state', 'UNKNOWN'),
            'created_at': order.get('created_at'),
            'customer': {
                'name': f"{order.get('customer', {}).get('first_name', '')} {order.get('customer', {}).get('last_name', '')}".strip(),
                'email': order.get('customer', {}).get('email')
            },
            'items_count': len(items_info),
            'items': items_info,
            'can_accept': can_accept_any,
            'acceptance_summary': {
                'acceptable': sum(1 for i in items_info if i['can_accept']),
                'already_accepted': sum(1 for i in items_info if i['state'] == 'ACCEPTED'),
                'final_state': sum(1 for i in items_info if i['is_final_state']),
                'total': len(items_info)
            },
            'recommendation': _get_order_recommendation(items_info, can_accept_any)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Errore debug endpoint: {e}")
        logger.exception(e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/refurbed/verify/<order_id>')
def verify_refurbed_order_state(order_id):
    """Verifica lo stato REALE di un ordine su Refurbed"""
    try:
        logger.info(f"🔍 Verifica stato ordine {order_id} su Refurbed API...")
        
        order_url = f"{rf_client.base_url}/refb.merchant.v1.OrderService/GetOrder"
        order_body = {"order_id": order_id}
        
        order_response = requests.post(order_url, headers=rf_client.headers, json=order_body, timeout=30)
        
        if order_response.status_code != 200:
            return jsonify({
                'success': False,
                'error': f'Errore API: HTTP {order_response.status_code}'
            }), 500
        
        order_data = order_response.json()
        order = order_data.get('order', {})
        
        items_url = f"{rf_client.base_url}/refb.merchant.v1.OrderItemService/ListOrderItemsByOrder"
        items_body = {"order_id": order_id}
        
        items_response = requests.post(items_url, headers=rf_client.headers, json=items_body, timeout=30)
        
        items = []
        if items_response.status_code == 200:
            items_data = items_response.json()
            items = items_data.get('order_items', [])
        
        items_analysis = []
        for item in items:
            items_analysis.append({
                'id': item.get('id'),
                'sku': item.get('sku'),
                'state': item.get('state'),
                'name': item.get('name', 'N/A')
            })
        
        order_state = order.get('state', 'UNKNOWN')
        all_accepted = all(i['state'] == 'ACCEPTED' for i in items_analysis)
        has_new = any(i['state'] == 'NEW' for i in items_analysis)
        
        expected_state = 'UNKNOWN'
        if has_new:
            expected_state = 'NEW'
        elif all_accepted:
            expected_state = 'ACCEPTED'
        elif any(i['state'] == 'ACCEPTED' for i in items_analysis):
            expected_state = 'ACCEPTED'
        
        state_mismatch = (expected_state != order_state) and (expected_state != 'UNKNOWN')
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'current_state': order_state,
            'expected_state': expected_state,
            'state_mismatch': state_mismatch,
            'items_count': len(items_analysis),
            'items': items_analysis,
            'analysis': {
                'all_accepted': all_accepted,
                'has_new_items': has_new,
                'calculation_rule': 'At least one item ACCEPTED and no items NEW = Order ACCEPTED',
                'conclusion': '✅ Ordine correttamente in stato ACCEPTED' if order_state == 'ACCEPTED' 
                             else f'⚠️ Ordine ancora in stato {order_state} - potrebbe essere in aggiornamento'
            },
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Errore verifica: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/test/refurbed/accept/<order_id>', methods=['POST'])
def test_accept_refurbed(order_id):
    """Endpoint test per accettazione Refurbed con log dettagliati"""
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 TEST: Accettazione ordine Refurbed {order_id}")
        logger.info(f"{'='*60}\n")
        
        success, message = rf_client.accept_order(order_id)
        
        response_data = {
            'success': success,
            'message': message,
            'order_id': order_id,
            'timestamp': datetime.now().isoformat()
        }
        
        if success:
            logger.info(f"✅ Test completato con successo")
            return jsonify(response_data), 200
        else:
            logger.error(f"❌ Test fallito: {message}")
            return jsonify(response_data), 500
        
    except Exception as e:
        logger.error(f"❌ Errore test accept: {e}")
        logger.exception(e)
        return jsonify({
            'success': False,
            'error': str(e),
            'order_id': order_id
        }), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health')
def health():
    """Health check con verifica Anastasia"""
    anastasia_status = 'ok'
    
    if anastasia_client:
        try:
            if not anastasia_client.health_check():
                anastasia_status = 'error'
        except:
            anastasia_status = 'error'
    else:
        anastasia_status = 'unavailable'
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'backmarket': 'ok',
            'refurbed': 'ok',
            'cdiscount': 'ok',
            'magento': 'ok',
            'invoicex': 'ok',
            'anastasia': anastasia_status
        }
    })
# ============================================================
# ROUTES - AUTOMAZIONE (Flask)
# ============================================================

@app.route('/api/automation/process-orders', methods=['POST'])
def trigger_automation():
    """
    Triggera manualmente il processo di automazione
    Accetta ordini e crea DDT per tutti gli ordini pendenti
    """
    try:
        logger.info("🚀 Automazione triggerata manualmente via API")
        results = automation_service.process_all_pending_orders()
        
        return jsonify({
            "success": True,
            "results": results,
            "message": f"{results['orders_processed']} ordini processati"
        })
    except Exception as e:
        logger.error(f"Errore automazione: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/automation/status', methods=['GET'])
def automation_status():
    """Stato dello scheduler di automazione"""
    global scheduler
    
    if not scheduler:
        return jsonify({
            "enabled": False,
            "status": "disabled",
            "message": "Automazione disabilitata"
        })
    
    jobs = scheduler.get_jobs()
    automation_job = next((job for job in jobs if job.id == "automation_job"), None)
    
    if automation_job:
        return jsonify({
            "enabled": True,
            "status": "running",
            "next_run": automation_job.next_run_time.isoformat() if automation_job.next_run_time else None,
            "interval_minutes": os.getenv("AUTOMATION_INTERVAL_MINUTES", "15")
        })
    else:
        return jsonify({
            "enabled": True,
            "status": "scheduled",
            "message": "Scheduler attivo ma job non trovato"
        })


@app.route('/api/test-telegram', methods=['GET'])
def test_telegram():
    """Test notifica Telegram"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        return jsonify({
            "success": False,
            "error": "TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID non configurati"
        })
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": "✅ Test notifica da ReflexMania Automation!\n\nSe ricevi questo messaggio, Telegram è configurato correttamente.",
            "parse_mode": "Markdown"
        }, timeout=10)
        
        if response.status_code == 200:
            return jsonify({
                "success": True,
                "message": "Notifica Telegram inviata con successo!"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Errore Telegram: {response.status_code}",
                "response": response.text
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/api/tracker/status', methods=['GET'])
def tracker_status():
    """Mostra contenuto tracker ordini"""
    try:
        # ✅ USA IL TRACKER DI order_service (stesso istanza)
        return jsonify({
            "success": True,
            "tracker_file": "/tmp/ordini_processati.json",
            "stats": order_service.order_tracker.get_stats(),
            "data": order_service.order_tracker.data,
            "total_orders": order_service.order_tracker._count_orders(order_service.order_tracker.data)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500   

# ============================================================
# STARTUP - AVVIA SCHEDULER AUTOMAZIONE
# ============================================================

def start_automation_scheduler():
    """Avvia lo scheduler per l'automazione ordini"""
    global scheduler
    
    if os.getenv("ENABLE_AUTOMATION", "true").lower() != "true":
        logger.info("⏸️ Automazione disabilitata (ENABLE_AUTOMATION=false)")
        return
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: automation_service.process_all_pending_orders(),
        trigger="interval",
        minutes=int(os.getenv("AUTOMATION_INTERVAL_MINUTES", "15")),
        id="automation_job",
        name="Automazione ordini",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"⏰ Scheduler automazione avviato (ogni {os.getenv('AUTOMATION_INTERVAL_MINUTES', '15')} minuti)")

# Avvia scheduler all'avvio dell'applicazione
start_automation_scheduler()

# ============================================================================
# AVVIO APPLICAZIONE
# ============================================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
                
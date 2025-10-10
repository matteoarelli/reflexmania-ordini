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

# Import client Anastasia
from clients.anastasia_api import AnastasiaClient
from config import ANASTASIA_DB_CONFIG, ANASTASIA_URL

# Inizializza Anastasia client
try:
    anastasia_client = AnastasiaClient(ANASTASIA_DB_CONFIG)
    logger.info("✅ Client Anastasia inizializzato")
except Exception as e:
    logger.error(f"❌ Errore inizializzazione Anastasia: {e}")
    anastasia_client = None


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
            
            /* WIDGET ANASTASIA */
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
        </style>
    </head>
    <body>
        <div class="container">
            <!-- HEADER -->
            <div class="header">
                <h1>🚀 ReflexMania - Gestione Unificata</h1>
                <div class="header-subtitle">Dashboard ordini marketplace + ticket valutazioni</div>
            </div>
            
            <!-- STATISTICHE GLOBALI -->
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
            
            <!-- GRID PRINCIPALE -->
            <div class="main-grid">
                <!-- SEZIONE ORDINI -->
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
                
                <!-- WIDGET ANASTASIA -->
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
            </div>
        </div>
<script>
            let orders = [];
            
            // ========== ORDINI ==========
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
            
            // ========== MAGENTO SHIPMENT ==========
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
                
                if (!confirm(`Confermi la spedizione dell'ordine Magento ${orderNumber}?\n\nTracking: ${trackingNumber}\nCorriere: ${carrierUpper}`)) {
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
                        alert(`✅ Ordine Magento ${orderNumber} spedito con successo!\n\n` +
                              `Shipment ID: ${data.shipment_id}\n` +
                              `Tracking: ${data.tracking_number}\n` +
                              `Corriere: ${data.carrier}\n\n` +
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
            
            // ========== ALTRE FUNZIONI ==========
            function markAsShipped(orderId, source) {
                const trackingNumber = prompt(`Inserisci il numero di tracking per l'ordine ${orderId}:`);
                if (!trackingNumber || trackingNumber.trim() === '') { alert('Numero di tracking obbligatorio'); return; }
                const trackingUrl = prompt(`Inserisci l'URL di tracking (opzionale):`);
                if (!confirm(`Confermi la spedizione dell'ordine ${orderId}?\n\nTracking: ${trackingNumber}`)) return;
                document.getElementById('loading').style.display = 'block';
                fetch('/api/mark_shipped', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, source: source, tracking_number: trackingNumber, tracking_url: trackingUrl || ''}) })
                .then(r => r.json()).then(data => { if (data.success) { alert(`Ordine ${orderId} marcato come spedito!\n\nTracking comunicato al marketplace.`); refreshOrders(); } else { alert('Errore: ' + data.error); document.getElementById('loading').style.display = 'none'; } })
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
                if (!confirm(`Confermi la creazione del DDT per l'ordine ${orderId}?\n\nQuesto:\n- Disabiliterà i prodotti su tutti i canali\n- Creerà il DDT su InvoiceX`)) return;
                document.getElementById('loading').style.display = 'block';
                fetch('/api/create_ddt_only', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, source: source}) })
                .then(r => r.json()).then(data => { if (data.success) { alert(`DDT creato con successo!\n\nNumero DDT: ${data.ddt_number}\n\nL'ordine è ora pronto per la spedizione.`); refreshOrders(); } else { alert('Errore: ' + data.error); document.getElementById('loading').style.display = 'none'; } })
                .catch(err => { alert('Errore di connessione'); console.error(err); document.getElementById('loading').style.display = 'none'; });
            }
            
            function downloadCSV() { window.location.href = '/api/packlink_csv'; }
            
            // ========== ANASTASIA TICKETS ==========
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
            
            // Auto-refresh
            refreshOrders();
            refreshTickets();
            
            setInterval(refreshOrders, 120000); // Ordini ogni 2 minuti
            setInterval(refreshTickets, 30000);  // Ticket ogni 30 secondi
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


# ============================================================================
# API UNIFIED DASHBOARD
# ============================================================================

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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
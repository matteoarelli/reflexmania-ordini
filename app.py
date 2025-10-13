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

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# INIZIALIZZAZIONE FLASK APP
# ============================================================================
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

# Inizializza Anastasia client
try:
    anastasia_client = AnastasiaClient(ANASTASIA_DB_CONFIG)
    logger.info("✅ Client Anastasia inizializzato")
except Exception as e:
    logger.error(f"❌ Errore inizializzazione Anastasia: {e}")
    anastasia_client = None


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
    # IL TUO HTML COMPLETO DELLA DASHBOARD
    # (Mantieni tutto il codice HTML esistente)
    pass  # Sostituisci con il tuo HTML
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
            
            all_orders = get_pending_orders(bm_client, rf_client, oct_client)
            order = next((o for o in all_orders if o['order_id'] == order_id and o['source'] == source), None)
            
            if not order:
                return jsonify({'success': False, 'error': 'Ordine non trovato'}), 404
            
            success_count = 0
            errors = []
            
            for item in order.get('items', []):
                item_id = item.get('listing_id') or item.get('id')
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
        
        # Magento
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


# ============================================================================
# AVVIO APPLICAZIONE
# ============================================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)    
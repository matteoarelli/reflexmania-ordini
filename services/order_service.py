#!/usr/bin/env python3
"""
Servizio per gestione ordini multi-marketplace
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def normalize_order(order: Dict, source: str) -> Dict:
    """Normalizza ordini da diversi marketplace"""
    
    if source == 'backmarket':
        shipping = order.get('shipping_address', {})
        items = []
        for item in order.get('orderlines', []):
            sku = item.get('serial_number') or item.get('listing', '')
            items.append({
                'sku': sku,
                'listing_id': item.get('listing', ''),
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
            'delivery_note': order.get('delivery_note', ''),
            'accepted': False
        }
    
    elif source == 'refurbed':
        shipping = order.get('shipping_address', {})
        items = []
        
        order_items = order.get('items', order.get('order_items', []))
        
        for item in order_items:
            item_name = (
                item.get('name') or 
                item.get('title') or 
                item.get('product_name') or
                item.get('instance_name') or
                'N/A'
            )
            
            sku = item.get('sku', '')
            if not sku:
                offer_data = item.get('offer_data', {})
                sku = offer_data.get('sku', item.get('id', ''))
            
            items.append({
                'sku': sku,
                'name': item_name,
                'quantity': item.get('quantity', 1)
            })
        
        order_date = (
            order.get('released_at') or 
            order.get('created_at') or 
            order.get('order_date') or 
            order.get('date') or
            ''
        )
        
        return {
            'order_id': str(order.get('id', '')),
            'source': 'Refurbed',
            'status': order.get('state', 'NEW'),
            'date': order_date,
            'customer_name': f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip(),
            'customer_email': order.get('email', ''),
            'customer_phone': shipping.get('phone', ''),
            'address': f"{shipping.get('street', '')} {shipping.get('house_no', '')} {shipping.get('supplement', '')}".strip(),
            'city': shipping.get('town', ''),
            'postal_code': shipping.get('post_code', ''),
            'country': shipping.get('country_code', ''),
            'items': items,
            'total': float(order.get('settlement_total_paid', order.get('total_paid', 0))),
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


def get_pending_orders(bm_client, rf_client, oct_client) -> List[Dict]:
    """Recupera tutti gli ordini pendenti da tutti i canali"""
    all_orders = []
    seen_order_ids = set()
    
    # BackMarket
    bm_count = 0
    for status in ['waiting_acceptance', 'accepted', 'to_ship']:
        orders = bm_client.get_orders(status=status)
        for order in orders:
            order_state = order.get('state', 0)
            order_id = str(order.get('order_id'))
            
            if order_id in seen_order_ids:
                continue
            
            if order_state != 9:
                all_orders.append(normalize_order(order, 'backmarket'))
                seen_order_ids.add(order_id)
                bm_count += 1
        logger.info(f"BackMarket status '{status}': {len(orders)} ordini totali")
    
    logger.info(f"BackMarket totale NON spediti (deduplicati): {bm_count} ordini")
    
    # Refurbed
    rf_orders_all = rf_client.get_orders(state=None, limit=100, sort_desc=True)
    logger.info(f"Refurbed: recuperati {len(rf_orders_all)} ordini TOTALI")
    
    rf_pending = []
    for order in rf_orders_all:
        order_state = order.get('state', 'NEW')
        if order_state not in ['SHIPPED', 'DELIVERED', 'CANCELLED', 'RETURNED', 'REJECTED']:
            rf_pending.append(order)
            all_orders.append(normalize_order(order, 'refurbed'))
    
    rf_count = len(rf_pending)
    logger.info(f"Refurbed: {rf_count} ordini pendenti")
    
    # CDiscount
    oct_orders = oct_client.get_orders()
    cd_count = 0
    
    for order in oct_orders:
        if order.get('status') not in ['Shipped', 'Delivered', 'Cancelled']:
            all_orders.append(normalize_order(order, 'octopia'))
            cd_count += 1
    
    logger.info(f"CDiscount: {cd_count} ordini da processare")
    
    return all_orders


def disable_product_on_channels(sku: str, listing_id: str, bm_client, rf_client, oct_client) -> Dict:
    """Disabilita un prodotto su tutti i canali impostando stock a 0"""
    results = {
        'backmarket': {'attempted': False, 'success': False, 'message': ''},
        'refurbed': {'attempted': False, 'success': False, 'message': ''},
        'cdiscount': {'attempted': False, 'success': False, 'message': ''}
    }
    
    logger.info(f"Disabilitazione prodotto SKU {sku} su tutti i canali")
    
    try:
        results['backmarket']['attempted'] = True
        # Usa listing_id se disponibile, altrimenti SKU
        id_to_disable = listing_id if listing_id else sku
        success = bm_client.disable_listing(id_to_disable)
        results['backmarket']['success'] = success
        results['backmarket']['message'] = 'Disabilitato' if success else 'Errore disabilitazione'
    except Exception as e:
        results['backmarket']['message'] = f'Errore: {str(e)}'
        logger.error(f"Errore disabilitazione BackMarket: {e}")
    
    try:
        results['refurbed']['attempted'] = True
        success = rf_client.disable_offer(sku)
        results['refurbed']['success'] = success
        results['refurbed']['message'] = 'Disabilitato' if success else 'Errore disabilitazione'
    except Exception as e:
        results['refurbed']['message'] = f'Errore: {str(e)}'
        logger.error(f"Errore disabilitazione Refurbed: {e}")
    
    try:
        results['cdiscount']['attempted'] = True
        success = oct_client.disable_offer(sku)
        results['cdiscount']['success'] = success
        results['cdiscount']['message'] = 'Disabilitato' if success else 'Package XML richiesto'
    except Exception as e:
        results['cdiscount']['message'] = f'Errore: {str(e)}'
        logger.error(f"Errore disabilitazione CDiscount: {e}")
    
    logger.info(f"Risultati disabilitazione SKU {sku}:")
    logger.info(f"  - BackMarket: {results['backmarket']}")
    logger.info(f"  - Refurbed: {results['refurbed']}")
    logger.info(f"  - CDiscount: {results['cdiscount']}")
    
    return results

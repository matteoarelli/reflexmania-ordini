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
    
        # 🆕 LOG DEBUG per verificare struttura orderlines
        logger.info(f"[NORMALIZE-BACKMARKET] Order ID: {order.get('order_id')}")
        logger.info(f"[NORMALIZE-BACKMARKET] Orderlines ricevute: {len(order.get('orderlines', []))}")
    
        for idx, item in enumerate(order.get('orderlines', [])):
            sku = item.get('serial_number') or item.get('listing', '')
            
            # FIX: Usa 'listing_id' (numerico) invece di 'listing' (SKU)
            listing_id_numeric = item.get('listing_id', '')
            
            logger.info(f"[NORMALIZE-BACKMARKET]   Item #{idx+1}:")
            logger.info(f"[NORMALIZE-BACKMARKET]     SKU (listing): {item.get('listing')}")
            logger.info(f"[NORMALIZE-BACKMARKET]     Serial: {item.get('serial_number')}")
            logger.info(f"[NORMALIZE-BACKMARKET]     Listing ID (numerico): {listing_id_numeric}")
            
            items.append({
                'sku': sku,
                'listing_id': str(listing_id_numeric) if listing_id_numeric else '',
                'name': item.get('product', 'N/A'),
                'quantity': item.get('quantity', 1),
                'price': float(item.get('price', 0))
            })
    
        logger.info(f"[NORMALIZE-BACKMARKET] Items normalizzati: {len(items)}")
        
        customer_email = (
            order.get('customer_email') or 
            order.get('email') or
            shipping.get('email') or
            ''
        )
        
        return {
            'order_id': str(order.get('order_id')),
            'source': 'BackMarket',
            'channel': 'backmarket',
            'payment_method': 'backmarket',
            'status': order.get('state', 'unknown'),
            'date': order.get('date_creation', ''),
            'customer_name': f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip(),
            'customer_email': customer_email,
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
        
        order_items = order.get('items', [])
        
        # 🆕 LOG DEBUG PER REFURBED
        logger.info(f"[NORMALIZE-REFURBED] Order ID: {order.get('id')}")
        logger.info(f"[NORMALIZE-REFURBED] Items ricevuti dall'API: {len(order_items)}")
        
        for idx, item in enumerate(order_items):
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
            
            price = float(item.get('settlement_total_paid', 0))
            
            logger.info(f"[NORMALIZE-REFURBED]   Item #{idx+1}: SKU={sku}, Name={item_name}, Price={price}")
            
            items.append({
                'sku': sku,
                'name': item_name,
                'quantity': int(item.get('quantity', 1)),
                'price': price
            })
        
        logger.info(f"[NORMALIZE-REFURBED] Items normalizzati: {len(items)}")
        
        order_date = (
            order.get('released_at') or 
            order.get('created_at') or 
            order.get('order_date') or 
            order.get('date') or
            ''
        )
        
        customer_email = (
            order.get('customer_email') or
            order.get('email') or
            shipping.get('email') or
            order.get('customer', {}).get('email') or
            ''
        )
        
        if not customer_email:
            order_id = order.get('id', 'unknown')
            customer_email = f"refurbed_{order_id}@placeholder.reflexmania.it"
            logger.warning(f"Email mancante per ordine Refurbed {order_id}, usando placeholder")
        
        first_name = shipping.get('first_name', '')
        family_name = shipping.get('family_name', '')
        customer_name = f"{first_name} {family_name}".strip()
        
        return {
            'order_id': str(order.get('id', '')),
            'source': 'Refurbed',
            'channel': 'refurbed',
            'payment_method': 'refurbed',
            'status': order.get('state', 'NEW'),
            'date': order_date,
            'customer_name': customer_name,
            'customer_email': customer_email,
            'customer_phone': shipping.get('phone_number', ''),
            'address': f"{shipping.get('street_name', '')} {shipping.get('house_no', '')}".strip(),
            'city': shipping.get('town', ''),
            'postal_code': shipping.get('post_code', ''),
            'country': shipping.get('country_code', ''),
            'items': items,
            'total': float(order.get('settlement_total_paid', 0)),
            'accepted': False
        }
    
    elif source == 'octopia':
        items = []
        shipping = {}
        
        for line in order.get('lines', []):
            shipping = line.get('shippingAddress', {})
            offer = line.get('offer', {})
            
            price_data = line.get('price', {})
            price = float(price_data.get('amount', 0))
            
            if price == 0:
                price = float(price_data.get('sellingPrice', 0))
            if price == 0:
                price = float(line.get('unitPrice', 0))
            if price == 0:
                price = float(offer.get('price', 0))
            
            items.append({
                'sku': offer.get('sellerProductId', ''),
                'name': offer.get('productTitle', 'N/A'),
                'quantity': line.get('quantity', 1),
                'price': price
            })
        
        return {
            'order_id': order.get('orderId'),
            'source': 'CDiscount',
            'channel': 'cdiscount',
            'payment_method': 'cdiscount',
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


def disable_product_on_channels(
    sku: str, 
    listing_id: str, 
    bm_client, 
    rf_client, 
    oct_client,
    magento_client=None
) -> Dict:
    """
    Disabilita un prodotto su tutti i canali impostando stock a 0
    
    Args:
        sku: SKU del prodotto
        listing_id: ID listing BackMarket (opzionale)
        bm_client: Client BackMarket
        rf_client: Client Refurbed
        oct_client: Client Octopia/CDiscount
        magento_client: Client Magento (opzionale)
        
    Returns:
        Dict con risultati per ogni canale
    """
    results = {
        'backmarket': {'attempted': False, 'success': False, 'message': ''},
        'refurbed': {'attempted': False, 'success': False, 'message': ''},
        'cdiscount': {'attempted': False, 'success': False, 'message': ''},
        'magento': {'attempted': False, 'success': False, 'message': ''}
    }
    
    logger.info(f"🔄 Disabilitazione prodotto SKU {sku} su tutti i canali")
    
    # BackMarket
    try:
        results['backmarket']['attempted'] = True
        id_to_disable = listing_id if listing_id else sku
        success = bm_client.disable_listing(id_to_disable)
        results['backmarket']['success'] = success
        results['backmarket']['message'] = '✅ Disabilitato' if success else '❌ Errore disabilitazione'
    except Exception as e:
        results['backmarket']['message'] = f'❌ Errore: {str(e)}'
        logger.error(f"Errore disabilitazione BackMarket: {e}")
    
    # Refurbed
    try:
        results['refurbed']['attempted'] = True
        success = rf_client.disable_offer(sku)
        results['refurbed']['success'] = success
        results['refurbed']['message'] = '✅ Disabilitato' if success else '❌ Errore disabilitazione'
    except Exception as e:
        results['refurbed']['message'] = f'❌ Errore: {str(e)}'
        logger.error(f"Errore disabilitazione Refurbed: {e}")
    
    # CDiscount
    try:
        results['cdiscount']['attempted'] = True
        success = oct_client.disable_offer(sku)
        results['cdiscount']['success'] = success
        results['cdiscount']['message'] = '✅ Disabilitato' if success else '⚠️ Package XML richiesto'
    except Exception as e:
        results['cdiscount']['message'] = f'❌ Errore: {str(e)}'
        logger.error(f"Errore disabilitazione CDiscount: {e}")
    
    # Magento
    if magento_client:
        try:
            results['magento']['attempted'] = True
            success = magento_client.disable_product(sku)
            results['magento']['success'] = success
            results['magento']['message'] = '✅ Disabilitato' if success else '❌ Errore disabilitazione'
        except Exception as e:
            results['magento']['message'] = f'❌ Errore: {str(e)}'
            logger.error(f"Errore disabilitazione Magento: {e}")
    else:
        results['magento']['message'] = '⚠️ Client non disponibile'
    
    logger.info(f"📊 Risultati disabilitazione SKU {sku}:")
    logger.info(f"  - BackMarket: {results['backmarket']}")
    logger.info(f"  - Refurbed: {results['refurbed']}")
    logger.info(f"  - CDiscount: {results['cdiscount']}")
    logger.info(f"  - Magento: {results['magento']}")
    
    return results
# ============================================================================
# CLASSE ORDER SERVICE (wrapper per automazione)
# ============================================================================

class OrderService:
    """
    Servizio per gestione ordini multi-marketplace
    Wrapper per le funzioni esistenti
    """
    
    def __init__(
        self, 
        backmarket_client, 
        refurbed_client, 
        magento_client,
        octopia_client,
        anastasia_client
    ):
        self.bm_client = backmarket_client
        self.rf_client = refurbed_client
        self.magento_client = magento_client
        self.oct_client = octopia_client
        self.anastasia_client = anastasia_client
        
        # ✅ AGGIUNGI QUESTO
        self.order_tracker = OrderTracker()

        logger.info("OrderService inizializzato")
    
    def get_all_pending_orders(self) -> List[Dict]:
        """Recupera tutti gli ordini pendenti da tutti i marketplace"""
        return get_pending_orders(
            bm_client=self.bm_client,
            rf_client=self.rf_client,
            oct_client=self.oct_client
        )
    
    def get_backmarket_pending_orders(self) -> List[Dict]:
        """Recupera solo ordini BackMarket NON ancora accettati"""
        orders = []
        seen_order_ids = set()
        
        # ✅ SOLO waiting_acceptance (non ancora accettati)
        for status in ['waiting_acceptance']:
            bm_orders = self.bm_client.get_orders(status=status)
            for order in bm_orders:
                order_state = order.get('state', 0)
                order_id = str(order.get('order_id'))
                
                # ✅ FILTRO: Skip se già processato
                if self.order_tracker.is_processed('backmarket', order_id):
                    continue
                
                if order_id not in seen_order_ids and order_state != 9:
                    orders.append(normalize_order(order, 'backmarket'))
                    seen_order_ids.add(order_id)
        
        logger.info(f"BackMarket: {len(orders)} ordini in attesa di accettazione")
        return orders
    
    def get_refurbed_pending_orders(self) -> List[Dict]:
        """Recupera solo ordini Refurbed NON ancora processati"""
        rf_orders_all = self.rf_client.get_orders(state=None, limit=100, sort_desc=True)
        orders = []
        
        for order in rf_orders_all:
            order_state = order.get('state', 'NEW')
            order_id = str(order.get('id', ''))
            
            # ✅ FILTRO: Skip se già processato
            if self.order_tracker.is_processed('refurbed', order_id):
                continue
            
            if order_state == 'NEW':
                orders.append(normalize_order(order, 'refurbed'))
        
        logger.info(f"Refurbed: {len(orders)} ordini NEW in attesa")
        return orders
    
    def get_magento_pending_orders(self) -> List[Dict]:
        """Recupera ordini Magento in processing SENZA DDT già creato"""
        orders = []
        
        try:
            # Recupera ordini in processing
            mg_orders = self.magento_client.get_processing_orders()
            logger.info(f"Magento: trovati {len(mg_orders)} ordini in processing")
            
            for order in mg_orders:
                order_id = order.get('increment_id', '')
                
                if not order_id:
                    continue
                
                # Verifica se esiste già DDT su InvoiceX
                riferimento = f"MAGENTO-{order_id}"
                
                # Qui dovremmo controllare su InvoiceX, ma non abbiamo accesso
                # al client InvoiceX in OrderService
                # Soluzione: normalizziamo l'ordine e il controllo lo fa DDTService
                
                orders.append(normalize_order(order, 'magento'))
            
            logger.info(f"Magento: {len(orders)} ordini da controllare")
            
        except Exception as e:
            logger.error(f"Errore recupero ordini Magento: {e}")
        
        return orders
    
    def disable_product_all_channels(self, sku: str, listing_id: str = '') -> Dict:
        """Disabilita prodotto su tutti i canali"""
        return disable_product_on_channels(
            sku=sku,
            listing_id=listing_id,
            bm_client=self.bm_client,
            rf_client=self.rf_client,
            oct_client=self.oct_client,
            magento_client=self.magento_client
        )
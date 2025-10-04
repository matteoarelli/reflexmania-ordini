"""
Order Service - Normalizzazione ordini dai vari marketplace
"""
import logging

logger = logging.getLogger(__name__)


def normalize_backmarket_order(order):
    """Normalizza ordine BackMarket"""
    try:
        shipping = order.get('shipping_address', {})
        items_data = order.get('items', [])
        
        items = []
        for item in items_data:
            items.append({
                'name': item.get('product_name', 'Prodotto'),
                'sku': item.get('sku', ''),
                'listing_id': item.get('listing_id', ''),
                'quantity': item.get('quantity', 1),
                'price': float(item.get('unit_price', 0)),  # Prezzo unitario
                'unit_price': float(item.get('unit_price', 0))
            })
        
        return {
            'order_id': str(order.get('id', '')),
            'source': 'BackMarket',
            'customer_name': f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip(),
            'customer_email': shipping.get('email', ''),
            'customer_phone': shipping.get('phone_number', ''),
            'address': shipping.get('address_line_1', ''),
            'postal_code': shipping.get('postal_code', ''),
            'city': shipping.get('city', ''),
            'country': shipping.get('country', 'IT'),
            'total': float(order.get('total_price', 0)),
            'shipping_cost': float(order.get('shipping_price', 0)),
            'date': order.get('created_at', ''),
            'status': order.get('state', ''),
            'delivery_note': order.get('delivery_note', ''),
            'items': items
        }
    except Exception as e:
        logger.error(f"Errore normalizzazione BackMarket: {str(e)}")
        return None


def normalize_refurbed_order(order):
    """Normalizza ordine Refurbed"""
    try:
        address = order.get('shippingAddress', {})
        items_data = order.get('orderItems', [])
        
        items = []
        for item in items_data:
            items.append({
                'name': item.get('productName', 'Prodotto'),
                'sku': item.get('sku', ''),
                'listing_id': '',
                'quantity': item.get('quantity', 1),
                'price': float(item.get('price', 0)),  # Prezzo unitario
                'unit_price': float(item.get('price', 0))
            })
        
        # FIX EMAIL: prova più fonti
        email = (
            order.get('customerEmail', '') or 
            address.get('email', '') or 
            order.get('customer', {}).get('email', '')
        )
        
        if not email:
            logger.warning(f"Email mancante per ordine Refurbed {order.get('orderId')}")
        
        return {
            'order_id': str(order.get('orderId', '')),
            'source': 'Refurbed',
            'customer_name': f"{address.get('firstName', '')} {address.get('lastName', '')}".strip(),
            'customer_email': email,  # FIX: email estratta da più fonti
            'customer_phone': address.get('phone', ''),
            'address': address.get('street', ''),
            'postal_code': address.get('zipCode', ''),
            'city': address.get('city', ''),
            'country': address.get('countryCode', 'IT'),
            'total': float(order.get('totalPrice', 0)),
            'shipping_cost': float(order.get('shippingCost', 0)),
            'date': order.get('orderDate', ''),
            'status': order.get('orderState', ''),
            'items': items
        }
    except Exception as e:
        logger.error(f"Errore normalizzazione Refurbed: {str(e)}")
        return None


def normalize_cdiscount_order(order):
    """Normalizza ordine CDiscount/Octopia"""
    try:
        address = order.get('ShippingAddress', {})
        billing = order.get('BillingAddress', {})
        items_data = order.get('OrderLineList', [])
        
        items = []
        for item in items_data:
            # FIX PREZZO: prova tutti i campi possibili
            price = float(item.get('UnitPrice', 0))
            if price == 0:
                price = float(item.get('SellerPrice', 0))
            if price == 0:
                price = float(item.get('AcceptedPrice', 0))
            if price == 0:
                price = float(item.get('Price', 0))
            
            items.append({
                'name': item.get('ProductName', 'Prodotto'),
                'sku': item.get('SellerProductId', ''),
                'listing_id': '',
                'quantity': int(item.get('Quantity', 1)),
                'price': price,  # Prezzo con fallback multipli
                'unit_price': price
            })
        
        # Email cliente
        email = billing.get('Email', '') or address.get('Email', '')
        
        return {
            'order_id': str(order.get('OrderNumber', '')),
            'source': 'CDiscount',
            'customer_name': f"{address.get('FirstName', '')} {address.get('LastName', '')}".strip(),
            'customer_email': email,
            'customer_phone': address.get('Phone', ''),
            'address': address.get('Address1', ''),
            'postal_code': address.get('ZipCode', ''),
            'city': address.get('City', ''),
            'country': address.get('CountryIsoCode', 'IT'),
            'total': float(order.get('TotalAmount', 0)),
            'shipping_cost': float(order.get('ShippingCost', 0)),
            'date': order.get('OrderDate', ''),
            'status': order.get('OrderState', ''),
            'items': items
        }
    except Exception as e:
        logger.error(f"Errore normalizzazione CDiscount: {str(e)}")
        return None


def get_pending_orders(bm_client, rf_client, oct_client):
    """
    Recupera ordini pendenti da tutti i marketplace
    """
    all_orders = []
    
    # BackMarket
    try:
        bm_orders = bm_client.get_orders()
        for order in bm_orders:
            normalized = normalize_backmarket_order(order)
            if normalized:
                all_orders.append(normalized)
    except Exception as e:
        logger.error(f"Errore recupero ordini BackMarket: {str(e)}")
    
    # Refurbed
    try:
        rf_orders = rf_client.get_orders()
        for order in rf_orders:
            normalized = normalize_refurbed_order(order)
            if normalized:
                all_orders.append(normalized)
    except Exception as e:
        logger.error(f"Errore recupero ordini Refurbed: {str(e)}")
    
    # CDiscount
    try:
        cd_orders = oct_client.get_orders()
        for order in cd_orders:
            normalized = normalize_cdiscount_order(order)
            if normalized:
                all_orders.append(normalized)
    except Exception as e:
        logger.error(f"Errore recupero ordini CDiscount: {str(e)}")
    
    return all_orders


def disable_product_on_channels(sku, listing_id, bm_client, rf_client, oct_client):
    """
    Disabilita un prodotto su tutti i canali marketplace
    """
    results = {}
    
    # BackMarket
    try:
        if listing_id:
            bm_client.disable_listing(listing_id)
            results['backmarket'] = True
    except Exception as e:
        logger.error(f"Errore disabilitazione BackMarket: {str(e)}")
        results['backmarket'] = False
    
    # Refurbed
    try:
        rf_client.disable_product(sku)
        results['refurbed'] = True
    except Exception as e:
        logger.error(f"Errore disabilitazione Refurbed: {str(e)}")
        results['refurbed'] = False
    
    # CDiscount
    try:
        oct_client.disable_product(sku)
        results['cdiscount'] = True
    except Exception as e:
        logger.error(f"Errore disabilitazione CDiscount: {str(e)}")
        results['cdiscount'] = False
    
    return results
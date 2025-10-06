from typing import List, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class MagentoService:
    """Service per normalizzare ordini Magento nel formato unificato"""
    
    def __init__(self, magento_client):
        self.client = magento_client
    
    def normalize_order(self, order_data: Dict) -> Optional[Dict]:
        """
        Normalizza un ordine Magento nel formato standard ReflexMania
        
        Formato output:
        {
            'channel': 'magento',
            'order_id': str,
            'order_date': str,
            'payment_method': str,
            'customer': {
                'name': str,
                'surname': str,
                'email': str,
                'phone': str,
                'address': str,
                'city': str,
                'zip': str,
                'country': str
            },
            'items': [
                {
                    'sku': str,
                    'name': str,
                    'quantity': int,
                    'price': float,
                    'serial': str (optional)
                }
            ],
            'total': float,
            'status': str
        }
        """
        try:
            # Estrai dati billing address
            billing = order_data.get('billing_address', {})
            
            # Nome e cognome
            firstname = billing.get('firstname', '')
            lastname = billing.get('lastname', '')
            
            # Indirizzo completo
            street = billing.get('street', [])
            address_line = street[0] if street else ''
            
            # Email e telefono
            email = order_data.get('customer_email', '')
            phone = billing.get('telephone', '')
            
            # Città, CAP, paese
            city = billing.get('city', '')
            postcode = billing.get('postcode', '')
            country = billing.get('country_id', '')
            
            # Estrai metodo di pagamento
            payment_info = order_data.get('payment', {})
            payment_method = payment_info.get('method', 'unknown')
            
            # Items dell'ordine
            items = []
            for item in order_data.get('items', []):
                # Salta item virtuali o bundle parent
                if item.get('product_type') in ['virtual', 'bundle']:
                    continue
                
                # Salta se è un child di un bundle
                if item.get('parent_item_id'):
                    continue
                
                items.append({
                    'sku': item.get('sku', ''),
                    'name': item.get('name', ''),
                    'quantity': int(item.get('qty_ordered', 1)),
                    'price': float(item.get('price', 0)),
                    'serial': None
                })
            
            # Se non ci sono items validi, skip
            if not items:
                logger.warning(f"Ordine Magento #{order_data.get('entity_id')} senza items validi")
                return None
            
            # Totale ordine
            total = float(order_data.get('grand_total', 0))
            
            # Data ordine
            order_date = order_data.get('created_at', '')
            
            # Stato
            status = order_data.get('status', '')
            
            normalized = {
                'channel': 'magento',
                'order_id': str(order_data.get('increment_id', order_data.get('entity_id'))),
                'entity_id': order_data.get('entity_id'),
                'order_date': order_date,
                'payment_method': payment_method,
                'customer': {
                    'name': firstname,
                    'surname': lastname,
                    'email': email,
                    'phone': phone,
                    'address': address_line,
                    'city': city,
                    'zip': postcode,
                    'country': country
                },
                'items': items,
                'total': total,
                'status': status
            }
            
            logger.info(f"Ordine Magento #{normalized['order_id']} normalizzato - Payment: {payment_method}")
            return normalized
            
        except Exception as e:
            logger.error(f"Errore normalizzazione ordine Magento: {str(e)}")
            return None
    
    def get_all_pending_orders(self) -> List[Dict]:
        """
        Recupera e normalizza tutti gli ordini Magento in stato 'processing'
        """
        orders = self.client.get_all_orders_with_details()
        normalized_orders = []
        
        for order in orders:
            normalized = self.normalize_order(order)
            if normalized:
                normalized_orders.append(normalized)
        
        logger.info(f"Totale {len(normalized_orders)} ordini Magento normalizzati")
        return normalized_orders
    
    def mark_order_as_completed(self, entity_id: int) -> bool:
        """
        Marca un ordine come completato dopo creazione DDT
        """
        return self.client.update_order_status(entity_id, 'complete')
    
    def get_order_by_id(self, order_id: str) -> Optional[Dict]:
        """
        Recupera un singolo ordine per ID (increment_id)
        """
        orders = self.get_all_pending_orders()
        
        for order in orders:
            if order['order_id'] == order_id:
                return order
        
        logger.warning(f"Ordine Magento #{order_id} non trovato")
        return None
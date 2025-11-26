import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class MagentoAPIClient:
    """Client per interagire con Magento REST API"""
    
    # Mapping corrieri supportati
    CARRIERS = {
        'BRT': 'custom',
        'UPS': 'ups',
        'DHL': 'dhl',
        'FEDEX': 'fedex',
        'TNT': 'tnt',
        'GLS': 'custom'
    }
    
    def __init__(self, base_url: str = None, token: str = None):
        from config import MAGENTO_URL, MAGENTO_TOKEN
        self.base_url = (base_url or MAGENTO_URL).rstrip('/')
        self.token = token or MAGENTO_TOKEN
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """Esegue una richiesta HTTP all'API Magento"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                timeout=30,
                **kwargs
            )
            response.raise_for_status()
            
            if response.status_code == 200 and response.text:
                return response.json()
            elif response.status_code in [200, 201]:
                return {'success': True}
            
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Errore chiamata Magento API {endpoint}: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None
    
    def get_processing_orders(self) -> List[Dict]:
        """Recupera tutti gli ordini in stato 'processing'"""
        endpoint = "/rest/V1/orders"
        
        params = {
            'searchCriteria[filter_groups][0][filters][0][field]': 'status',
            'searchCriteria[filter_groups][0][filters][0][value]': 'processing',
            'searchCriteria[filter_groups][0][filters][0][condition_type]': 'eq'
        }
        
        result = self._make_request('GET', endpoint, params=params)
        
        if result and 'items' in result:
            logger.info(f"Recuperati {len(result['items'])} ordini Magento in processing")
            return result['items']
        
        logger.warning("Nessun ordine Magento trovato")
        return []
    
    def get_pending_orders(self) -> List[Dict]:
        """Recupera tutti gli ordini in stato 'pending' (in attesa di pagamento)"""
        endpoint = "/rest/V1/orders"
        
        params = {
            'searchCriteria[filter_groups][0][filters][0][field]': 'status',
            'searchCriteria[filter_groups][0][filters][0][value]': 'pending',
            'searchCriteria[filter_groups][0][filters][0][condition_type]': 'eq'
        }
        
        result = self._make_request('GET', endpoint, params=params)
        
        if result and 'items' in result:
            logger.info(f"Recuperati {len(result['items'])} ordini Magento in pending")
            return result['items']
        
        logger.warning("Nessun ordine Magento pending trovato")
        return []

    def update_order_to_processing(self, entity_id: int) -> bool:
        """
        Aggiorna un ordine da 'pending' a 'processing' creando una invoice.
        """
        try:
            # Prima recupera i dettagli dell'ordine per avere gli items
            order = self.get_order_details(entity_id)
            if not order:
                logger.error(f"❌ Impossibile recuperare ordine #{entity_id}")
                return False
            
            # Prepara gli items per l'invoice
            invoice_items = []
            for item in order.get('items', []):
                # Salta item virtuali e child di bundle
                if item.get('product_type') in ['virtual', 'downloadable']:
                    continue
                if item.get('parent_item_id'):
                    continue
                
                invoice_items.append({
                    "order_item_id": item['item_id'],
                    "qty": item.get('qty_ordered', 1)
                })
            
            if not invoice_items:
                logger.error(f"❌ Nessun item da fatturare per ordine #{entity_id}")
                return False
            
            # Crea invoice
            endpoint = f"/rest/V1/order/{entity_id}/invoice"
            
            payload = {
                "capture": True,
                "notify": False,
                "items": invoice_items
            }
            
            logger.info(f"📄 Creazione invoice per ordine #{entity_id} con {len(invoice_items)} items")
            
            result = self._make_request('POST', endpoint, json=payload)
            
            if result:
                logger.info(f"✅ Invoice creata per ordine #{entity_id} - stato ora 'processing'")
                return True
            
            logger.error(f"❌ Errore creazione invoice per ordine #{entity_id}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Errore update_order_to_processing: {e}")
            return False
    
    def get_order_details(self, entity_id: int) -> Optional[Dict]:
        """Recupera i dettagli completi di un ordine specifico"""
        endpoint = f"/rest/V1/orders/{entity_id}"
        
        result = self._make_request('GET', endpoint)
        
        if result:
            logger.info(f"Dettagli ordine Magento #{entity_id} recuperati")
            return result
        
        logger.error(f"Impossibile recuperare dettagli ordine #{entity_id}")
        return None
    
    def get_all_orders_with_details(self) -> List[Dict]:
        """Recupera tutti gli ordini in processing con dettagli completi"""
        orders = self.get_processing_orders()
        detailed_orders = []
        
        for order in orders:
            entity_id = order.get('entity_id')
            if entity_id:
                details = self.get_order_details(entity_id)
                if details:
                    detailed_orders.append(details)
        
        return detailed_orders
    
    def update_order_status(self, entity_id: int, status: str) -> bool:
        """Aggiorna lo stato di un ordine"""
        endpoint = f"/rest/V1/orders/{entity_id}"
        
        payload = {
            "entity": {
                "entity_id": entity_id,
                "status": status
            }
        }
        
        result = self._make_request('PUT', endpoint, json=payload)
        
        if result:
            logger.info(f"Stato ordine #{entity_id} aggiornato a '{status}'")
            return True
        
        logger.error(f"Errore aggiornamento stato ordine #{entity_id}")
        return False
    
    def disable_product(self, sku: str) -> bool:
        """Disabilita un prodotto su Magento e imposta qty = 0"""
        try:
            from urllib.parse import quote
            sku_encoded = quote(sku, safe='')
            
            logger.info(f"🔄 Disabilitazione prodotto Magento: {sku}")
            
            # Disabilita prodotto su scope DEFAULT/ALL
            endpoint_default = f"/rest/all/V1/products/{sku_encoded}"
            payload_disable = {
                "product": {
                    "sku": sku,
                    "status": 2  # Disabled
                }
            }
            
            result_default = self._make_request('PUT', endpoint_default, json=payload_disable)
            if result_default:
                logger.info(f"✅ Prodotto {sku} disabilitato su vista GENERALE (scope: all)")
            else:
                logger.warning(f"⚠️ Errore disabilitazione vista generale per {sku}")
                return False
            
            # Imposta quantità a 0
            endpoint_stock = f"/rest/V1/products/{sku_encoded}/stockItems/1"
            payload_stock = {
                "stockItem": {
                    "qty": 0,
                    "is_in_stock": False
                }
            }
            
            result_stock = self._make_request('PUT', endpoint_stock, json=payload_stock)
            if result_stock:
                logger.info(f"✅ Prodotto {sku} quantità impostata a 0")
            else:
                logger.warning(f"⚠️ Errore impostazione qty=0 per {sku}")
            
            logger.info(f"✅ Disabilitazione completa prodotto Magento {sku}")
            return True
                
        except Exception as e:
            logger.error(f"❌ Errore disable_product Magento: {e}")
            return False
    
    def create_shipment(
        self, 
        order_id: int, 
        tracking_number: str, 
        carrier_code: str = 'custom',
        carrier_title: str = 'BRT'
    ) -> Optional[int]:
        """
        Crea una spedizione per un ordine Magento
        
        Args:
            order_id: Entity ID dell'ordine (NON increment_id)
            tracking_number: Numero di tracking
            carrier_code: Codice corriere ('custom', 'ups', 'dhl', etc.)
            carrier_title: Nome corriere per visualizzazione ('BRT', 'UPS', 'DHL')
            
        Returns:
            Shipment ID se successo, None altrimenti
        """
        try:
            logger.info(f"📦 create_shipment chiamato con order_id={order_id}, tracking={tracking_number}")
            
            # Recupera dettagli ordine
            order = self.get_order_details(order_id)
            
            if not order:
                logger.error(f"❌ Impossibile recuperare ordine #{order_id} per shipment")
                return None
            
            # Prepara items per shipment
            items = []
            for item in order.get('items', []):
                # Salta item virtuali/bundle parents
                if item.get('product_type') in ['virtual', 'downloadable']:
                    continue
                if item.get('parent_item_id'):
                    continue
                
                qty_ordered = float(item.get('qty_ordered', 0))
                qty_shipped = float(item.get('qty_shipped', 0))
                qty_to_ship = qty_ordered - qty_shipped
                
                if qty_to_ship > 0:
                    items.append({
                        "order_item_id": item['item_id'],
                        "qty": qty_to_ship
                    })
            
            if not items:
                logger.error(f"❌ Nessun item spedibile trovato per ordine #{order_id}")
                return None
            
            logger.info(f"📦 Items da spedire: {items}")
            
            # Crea shipment con tracking
            endpoint = f"/rest/V1/order/{order_id}/ship"
            
            payload = {
                "items": items,
                "tracks": [{
                    "track_number": tracking_number,
                    "carrier_code": carrier_code,
                    "title": carrier_title
                }],
                "notify": True
            }
            
            logger.info(f"📤 Payload shipment: {payload}")
            
            result = self._make_request('POST', endpoint, json=payload)
            
            if result:
                shipment_id = result if isinstance(result, int) else result.get('success', True)
                logger.info(f"✅ Shipment creato per ordine #{order_id} - Tracking: {tracking_number} ({carrier_title})")
                return shipment_id
            else:
                logger.error(f"❌ Errore creazione shipment per ordine #{order_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Errore create_shipment Magento: {e}")
            logger.exception(e)
            return None
    
    def get_carrier_code(self, carrier_name: str) -> str:
        """Converte nome corriere in carrier_code Magento"""
        return self.CARRIERS.get(carrier_name.upper(), 'custom')
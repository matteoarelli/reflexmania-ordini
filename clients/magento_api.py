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
            
            # Alcune chiamate Magento ritornano 200 senza body
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
        """
        Recupera tutti gli ordini in stato 'processing'
        Filtro: status=processing
        """
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
    
    def get_order_details(self, entity_id: int) -> Optional[Dict]:
        """
        Recupera i dettagli completi di un ordine specifico
        """
        endpoint = f"/rest/V1/orders/{entity_id}"
        
        result = self._make_request('GET', endpoint)
        
        if result:
            logger.info(f"Dettagli ordine Magento #{entity_id} recuperati")
            return result
        
        logger.error(f"Impossibile recuperare dettagli ordine #{entity_id}")
        return None
    
    def get_all_orders_with_details(self) -> List[Dict]:
        """
        Recupera tutti gli ordini in processing con dettagli completi
        """
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
        """
        Aggiorna lo stato di un ordine
        Utile per marcare ordini come 'complete' dopo creazione DDT
        """
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
        """
        Disabilita un prodotto su Magento (status = 2) e imposta qty = 0
        - Disabilita su TUTTE le store views (default scope + ogni store)
        - Imposta quantità a 0
        
        Status: 1 = Enabled, 2 = Disabled
        """
        try:
            from urllib.parse import quote
            sku_encoded = quote(sku, safe='')
            
            logger.info(f"🔄 Disabilitazione prodotto Magento: {sku}")
            
            # STEP 1: Disabilita prodotto su scope DEFAULT (vista generale)
            endpoint_default = f"/rest/default/V1/products/{sku_encoded}"
            payload_disable = {
                "product": {
                    "sku": sku,
                    "status": 2  # Disabled
                }
            }
            
            result_default = self._make_request('PUT', endpoint_default, json=payload_disable)
            if result_default:
                logger.info(f"✅ Prodotto {sku} disabilitato su vista DEFAULT")
            else:
                logger.warning(f"⚠️ Errore disabilitazione vista DEFAULT per {sku}")
            
            # STEP 2: Disabilita su TUTTE le altre store views
            # Magento generalmente ha: default, it, en, de, fr, etc.
            store_views = ['all', 'it', 'en', 'de']  # Aggiungi altre viste se necessario
            
            for store in store_views:
                endpoint_store = f"/rest/{store}/V1/products/{sku_encoded}"
                result_store = self._make_request('PUT', endpoint_store, json=payload_disable)
                if result_store:
                    logger.info(f"✅ Prodotto {sku} disabilitato su vista '{store}'")
            
            # STEP 3: Imposta quantità a 0 (usa API stock items)
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
            order_id: Entity ID dell'ordine
            tracking_number: Numero di tracking
            carrier_code: Codice corriere ('custom', 'ups', 'dhl', etc.)
            carrier_title: Nome corriere per visualizzazione ('BRT', 'UPS', 'DHL')
            
        Returns:
            Shipment ID se successo, None altrimenti
        """
        try:
            # Step 1: Recupera dettagli ordine per ottenere gli items
            order = self.get_order_details(order_id)
            
            if not order:
                logger.error(f"Impossibile recuperare ordine #{order_id} per shipment")
                return None
            
            # Step 2: Prepara items per shipment (tutti gli item ordinati)
            items = []
            for item in order.get('items', []):
                # Salta item virtuali/bundle parents
                if item.get('product_type') in ['virtual', 'downloadable']:
                    continue
                if item.get('parent_item_id'):
                    continue
                
                items.append({
                    "order_item_id": item['item_id'],
                    "qty": item['qty_ordered']
                })
            
            if not items:
                logger.error(f"Nessun item spedibile trovato per ordine #{order_id}")
                return None
            
            # Step 3: Crea shipment con tracking
            endpoint = f"/rest/V1/order/{order_id}/ship"
            
            payload = {
                "items": items,
                "tracks": [{
                    "track_number": tracking_number,
                    "carrier_code": carrier_code,
                    "title": carrier_title
                }],
                "notify": True  # Invia email al cliente
            }
            
            result = self._make_request('POST', endpoint, json=payload)
            
            if result:
                shipment_id = result if isinstance(result, int) else result.get('success')
                logger.info(f"✅ Shipment creato per ordine #{order_id} - Tracking: {tracking_number} ({carrier_title})")
                return shipment_id
            else:
                logger.error(f"❌ Errore creazione shipment per ordine #{order_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Errore create_shipment Magento: {e}")
            return None
    
    def get_carrier_code(self, carrier_name: str) -> str:
        """
        Converte nome corriere in carrier_code Magento
        
        Args:
            carrier_name: Nome corriere ('BRT', 'UPS', 'DHL', etc.)
            
        Returns:
            Carrier code corrispondente
        """
        return self.CARRIERS.get(carrier_name.upper(), 'custom')
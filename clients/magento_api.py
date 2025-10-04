import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class MagentoAPIClient:
    """Client per interagire con Magento REST API"""
    
    def __init__(self, base_url: str = None, token: str = None):
        from config import MAGENTO_URL, MAGENTO_TOKEN
        self.base_url = (base_url or MAGENTO_URL).rstrip('/')
        self.token = token or MAGENTO_TOKEN
        self.headers = {
            'Authorization': f'Bearer {token}',
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
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Errore chiamata Magento API {endpoint}: {str(e)}")
            if hasattr(e.response, 'text'):
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

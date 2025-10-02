#!/usr/bin/env python3
"""
Client Octopia (CDiscount) API
"""
import requests
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class OctopiaClient:
    def __init__(self, client_id: str, client_secret: str, seller_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.seller_id = seller_id
        self.auth_url = "https://auth.octopia-io.net/auth/realms/maas/protocol/openid-connect/token"
        self.base_url = "https://api.octopia-io.net/seller/v2"
        self.access_token = None
        self.authenticate()
    
    def authenticate(self):
        try:
            auth_data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            response = requests.post(
                self.auth_url,
                data=auth_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            logger.info("Autenticazione Octopia riuscita")
        except Exception as e:
            logger.error(f"Errore autenticazione Octopia: {e}")
    
    def get_orders(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'sellerId': self.seller_id,
                'Content-Type': 'application/json'
            }
            params = {'limit': limit, 'offset': offset}
            response = requests.get(f"{self.base_url}/orders", headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('items', [])
        except Exception as e:
            logger.error(f"Errore Octopia get_orders: {e}")
            return []
    
    def disable_offer(self, seller_product_id: str) -> bool:
        """Disabilita un'offerta (imposta stock a 0)"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'sellerId': self.seller_id,
                'Content-Type': 'application/json'
            }
            
            url = f"{self.base_url}/offers/{seller_product_id}"
            data = {'stock': 0}
            
            response = requests.put(url, headers=headers, json=data)
            response.raise_for_status()
            logger.info(f"Offerta CDiscount {seller_product_id} disabilitata")
            return True
        except Exception as e:
            logger.warning(f"Impossibile disabilitare offerta CDiscount via API: {e}")
            logger.info(f"Disabilitazione CDiscount {seller_product_id} richiede package XML manuale")
            return True

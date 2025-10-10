#!/usr/bin/env python3
"""
Client BackMarket API
"""
import requests
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class BackMarketClient:
    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url
        self.headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def get_orders(self, status: str = None, limit: int = 100) -> List[Dict]:
        try:
            url = f"{self.base_url}/ws/orders"
            params = {'limit': limit}
            if status:
                params['status'] = status
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except Exception as e:
            logger.error(f"Errore BackMarket get_orders: {e}")
            return []
    
    def accept_order(self, order_id: str) -> bool:
        """Accetta un ordine su BackMarket aggiornando le orderlines allo stato 2"""
        try:
            order_url = f"{self.base_url}/ws/orders/{order_id}"
            order_response = requests.get(order_url, headers=self.headers)
            
            if order_response.status_code != 200:
                logger.error(f"Impossibile recuperare dettagli ordine {order_id}")
                return False
            
            order_data = order_response.json()
            orderlines = order_data.get('orderlines', [])
            
            if not orderlines:
                logger.error(f"Nessuna orderline trovata per ordine {order_id}")
                return False
            
            success_count = 0
            for orderline in orderlines:
                sku = orderline.get('listing') or orderline.get('serial_number')
                
                if not sku:
                    logger.warning(f"SKU mancante per orderline in ordine {order_id}")
                    continue
                
                update_url = f"{self.base_url}/ws/orders/{order_id}"
                data = {
                    "order_id": int(order_id),
                    "new_state": 2,
                    "sku": sku
                }
                
                response = requests.post(update_url, headers=self.headers, json=data)
                
                if response.status_code == 200:
                    logger.info(f"Orderline {sku} accettata per ordine {order_id}")
                    success_count += 1
                else:
                    logger.error(f"Errore accettazione orderline {sku}: {response.status_code} - {response.text}")
            
            if success_count > 0:
                logger.info(f"Ordine {order_id} accettato: {success_count}/{len(orderlines)} orderlines")
                return True
            else:
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Errore connessione BackMarket API: {e}")
            return False
        except Exception as e:
            logger.error(f"Errore imprevisto: {e}")
            return False
    
    def disable_listing(self, listing_id: str) -> bool:
        """
        Disabilita un listing su BackMarket
        Prova prima DELETE, poi PUT con stock=0 come fallback
        """
        try:
            url = f"{self.base_url}/ws/listings/{listing_id}"
            
            # TENTATIVO 1: DELETE (metodo preferito da BackMarket)
            response = requests.delete(url, headers=self.headers)
            
            if response.status_code in [200, 204]:
                logger.info(f"✅ Listing BackMarket {listing_id} disabilitato (DELETE)")
                return True
            elif response.status_code == 404:
                logger.warning(f"⚠️ Listing BackMarket {listing_id} non trovato - già disabilitato")
                return True
            
            # TENTATIVO 2: PUT con stock=0 (fallback)
            logger.info(f"⚠️ DELETE fallito (HTTP {response.status_code}), provo PUT con stock=0")
            data = {'stock': 0}
            response = requests.put(url, headers=self.headers, json=data)
            
            if response.status_code in [200, 204]:
                logger.info(f"✅ Listing BackMarket {listing_id} disabilitato (PUT stock=0)")
                return True
            elif response.status_code == 404:
                logger.warning(f"⚠️ Listing BackMarket {listing_id} non trovato")
                return True
            else:
                logger.warning(f"❌ BackMarket {listing_id}: HTTP {response.status_code} - {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Errore disabilitazione listing BackMarket: {e}")
            return False
    
    def mark_as_shipped(self, order_id: str, tracking_number: str, tracking_url: str = '') -> bool:
        """Marca un ordine come spedito"""
        try:
            order_url = f"{self.base_url}/ws/orders/{order_id}"
            order_response = requests.get(order_url, headers=self.headers)
            
            if order_response.status_code != 200:
                return False
            
            order_data = order_response.json()
            orderlines = order_data.get('orderlines', [])
            
            if not orderlines:
                return False
            
            sku = orderlines[0].get('listing') or orderlines[0].get('serial_number')
            
            update_url = f"{self.base_url}/ws/orders/{order_id}"
            update_data = {
                "order_id": int(order_id),
                "new_state": 3,
                "sku": sku,
                "tracking_number": tracking_number,
                "tracking_url": tracking_url
            }
            
            response = requests.post(update_url, headers=self.headers, json=update_data)
            
            if response.status_code == 200:
                logger.info(f"Ordine {order_id} marcato come spedito su BackMarket")
                return True
            else:
                logger.error(f"Errore BackMarket mark shipped: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Errore mark_as_shipped BackMarket: {e}")
            return False
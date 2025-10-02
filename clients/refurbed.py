#!/usr/bin/env python3
"""
Client Refurbed API
"""
import requests
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class RefurbishedClient:
    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url
        self.headers = {
            'Authorization': f'Plain {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def get_orders(self, state: str = None, limit: int = 100, sort_desc: bool = True) -> List[Dict]:
        """Recupera ordini da Refurbed - gRPC style API (POST method)"""
        try:
            url = f"{self.base_url}/refb.merchant.v1.OrderService/ListOrders"
            
            body = {
                "pagination": {"limit": limit},
                "sort": {
                    "field": "CREATED_AT",
                    "order": "DESC" if sort_desc else "ASC"
                }
            }
            
            if state:
                body["state_filters"] = [state]
            
            response = requests.post(url, headers=self.headers, json=body)
            response.raise_for_status()
            
            data = response.json()
            orders = data.get('orders', [])
            
            logger.info(f"Refurbed: recuperati {len(orders)} ordini")
            return orders
            
        except Exception as e:
            logger.error(f"Errore Refurbed get_orders: {e}")
            return []
    
    def accept_order(self, order_id: str) -> bool:
        """Accetta un ordine su Refurbed aggiornando lo stato a ACCEPTED"""
        try:
            url = f"{self.base_url}/refb.merchant.v1.OrderItemService/BatchUpdateOrderItemsState"
            
            list_url = f"{self.base_url}/refb.merchant.v1.OrderItemService/ListOrderItemsByOrder"
            list_body = {"order_id": order_id}
            
            list_response = requests.post(list_url, headers=self.headers, json=list_body)
            
            if list_response.status_code != 200:
                logger.error(f"Impossibile recuperare order items per ordine Refurbed {order_id}")
                return False
            
            list_data = list_response.json()
            order_items = list_data.get('order_items', [])
            
            if not order_items:
                logger.error(f"Nessun order_item trovato per ordine Refurbed {order_id}")
                return False
            
            updates = []
            for item in order_items:
                item_id = item.get('id')
                if item_id:
                    updates.append({"order_item_id": item_id, "state": "ACCEPTED"})
            
            if not updates:
                return False
            
            update_body = {"updates": updates}
            response = requests.post(url, headers=self.headers, json=update_body)
            
            if response.status_code == 200:
                logger.info(f"Ordine Refurbed {order_id} accettato: {len(updates)} items")
                return True
            else:
                logger.error(f"Errore accettazione Refurbed {order_id}: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Errore accept_order Refurbed: {e}")
            return False
    
    def disable_offer(self, sku: str) -> bool:
        """Disabilita offerta (stock = 0)"""
        try:
            url = f"{self.base_url}/refb.merchant.v1.OfferService/UpdateOffer"
            body = {"identifier": {"sku": sku}, "stock": 0}
            
            response = requests.post(url, headers=self.headers, json=body)
            
            if response.status_code == 200:
                logger.info(f"Offerta Refurbed SKU {sku} disabilitata")
                return True
            else:
                logger.warning(f"Refurbed {sku}: {response.status_code}")
                return False
            
        except Exception as e:
            logger.error(f"Errore disable_offer Refurbed: {e}")
            return False

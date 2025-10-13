#!/usr/bin/env python3
"""
Client Refurbed API - Conforme alla documentazione ufficiale
Gestione corretta degli stati: NEW → ACCEPTED → SHIPPED
"""
import requests
import logging
from typing import List, Dict, Tuple, Optional

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
            
            logger.info(f"🔍 Refurbed: richiesta ordini (stato={state or 'ALL'})")
            response = requests.post(url, headers=self.headers, json=body, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            orders = data.get('orders', [])
            
            logger.info(f"✅ Refurbed: recuperati {len(orders)} ordini")
            return orders
            
        except requests.exceptions.Timeout:
            logger.error(f"⏱️ Timeout recupero ordini Refurbed")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Errore HTTP Refurbed get_orders: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Errore generico Refurbed get_orders: {e}")
            return []
    
    def accept_order(self, order_id: str) -> Tuple[bool, str]:
        """
        Accetta un ordine su Refurbed seguendo le regole di transizione:
        - NEW → ACCEPTED (valido)
        - PENDING → ACCEPTED (valido se supportato)
        - Altri stati → errore
        
        Returns:
            Tuple[bool, str]: (success, detailed_message)
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"📦 REFURBED: Accettazione ordine {order_id}")
            logger.info(f"{'='*60}")
            
            # Step 1: Recupera gli order items
            items, error = self._get_order_items(order_id)
            if error:
                return False, error
            
            if not items:
                return False, "Nessun order_item trovato per questo ordine"
            
            logger.info(f"✅ Trovati {len(items)} items")
            
            # Step 2: Analizza gli stati e prepara gli update
            updates = []
            already_accepted = []
            not_acceptable = []
            
            for item in items:
                item_id = item.get('id')
                current_state = item.get('state', 'UNKNOWN')
                sku = item.get('sku', 'N/A')
                
                # Log TUTTO il contenuto dell'item per debug
                logger.info(f"  📦 Item completo: {item}")
                logger.info(f"  📦 Item {item_id} (type: {type(item_id).__name__})")
                logger.info(f"     └─ SKU: {sku}")
                logger.info(f"     └─ Stato attuale: {current_state}")
                
                # Regole di transizione dalla documentazione ufficiale
                if current_state in ['NEW', 'PENDING']:
                    # IMPORTANTE: Includi order_id nell'update
                    updates.append({
                        "order_id": order_id,  # ← AGGIUNTO!
                        "order_item_id": str(item_id), 
                        "state": "ACCEPTED"
                    })
                    logger.info(f"     └─ ✅ Sarà accettato (transizione valida)")
                    
                elif current_state == 'ACCEPTED':
                    already_accepted.append(sku)
                    logger.info(f"     └─ ℹ️  Già in stato ACCEPTED")
                    
                elif current_state in ['SHIPPED', 'RETURNED', 'REJECTED', 'CANCELLED']:
                    not_acceptable.append((sku, current_state))
                    logger.info(f"     └─ ⚠️  Stato finale: {current_state} (non modificabile)")
                    
                else:
                    logger.warning(f"     └─ ⚠️  Stato sconosciuto: {current_state}")
            
            # Step 3: Valuta se procedere
            if not updates and not already_accepted:
                # Nessun item accettabile
                states_summary = ", ".join([f"{sku}={state}" for sku, state in not_acceptable])
                error_msg = f"Nessun item accettabile. Stati: {states_summary}"
                logger.error(f"❌ {error_msg}")
                return False, error_msg
            
            if not updates and already_accepted:
                # Tutti già accettati
                msg = f"✅ Ordine già completamente accettato ({len(already_accepted)} items)"
                logger.info(f"ℹ️  {msg}")
                return True, msg
            
            # Step 4: Esegui update con formato corretto
            logger.info(f"\n🚀 Esecuzione update per {len(updates)} items...")
            
            if len(updates) == 1:
                # Singolo item: usa UpdateOrderItemState con "id"
                logger.info(f"📝 Usando UpdateOrderItemState (singolo item)...")
                success = self._update_single_item_state(updates[0])
            else:
                # Multipli items: usa BatchUpdateOrderItemsState con "order_item_id"
                logger.info(f"📝 Usando BatchUpdateOrderItemsState ({len(updates)} items)...")
                success = self._batch_update_items_state(updates)
            
            if not success:
                return False, "Errore durante l'update su Refurbed API"
            
            # Step 4.5: VERIFICA che l'update sia andato a buon fine
            logger.info(f"🔍 Verifica stato items dopo batch update...")
            import time
            time.sleep(2)  # Aspetta 2 secondi per propagazione
            
            items_after, error_after = self._get_order_items(order_id)
            if items_after:
                logger.info(f"📊 STATO ITEMS DOPO L'UPDATE:")
                for item in items_after:
                    item_id = item.get('id')
                    new_state = item.get('state', 'UNKNOWN')
                    sku = item.get('sku', 'N/A')
                    logger.info(f"  📦 Item {item_id}: SKU={sku}, NUOVO STATO={new_state}")
                    
                    # Controlla se qualche item è rimasto in NEW
                    if item_id in [u['order_item_id'] for u in updates] and new_state == 'NEW':
                        logger.error(f"  ❌ Item {item_id} ancora in stato NEW dopo l'update!")
                        return False, f"L'update API è stato accettato ma l'item {sku} è rimasto in stato NEW. Possibile problema con Refurbed API."
            
            # Step 5: Costruisci messaggio di successo
            success_parts = []
            if updates:
                success_parts.append(f"{len(updates)} items accettati")
            if already_accepted:
                success_parts.append(f"{len(already_accepted)} già accettati")
            
            success_msg = "✅ " + ", ".join(success_parts)
            
            # Verifica stato finale
            final_state = self._verify_order_state(order_id)
            if final_state:
                success_msg += f" (Stato ordine: {final_state})"
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ {success_msg}")
            logger.info(f"{'='*60}\n")
            
            return True, success_msg
                
        except Exception as e:
            error_msg = f"Errore imprevisto: {str(e)}"
            logger.error(f"❌ {error_msg}")
            logger.exception(e)
            return False, error_msg
    
    def _get_order_items(self, order_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Recupera gli order items di un ordine"""
        try:
            url = f"{self.base_url}/refb.merchant.v1.OrderItemService/ListOrderItemsByOrder"
            body = {"order_id": order_id}
            
            logger.info(f"🔍 Recupero items per ordine {order_id}...")
            response = requests.post(url, headers=self.headers, json=body, timeout=30)
            
            if response.status_code != 200:
                error = f"HTTP {response.status_code}: {response.text[:300]}"
                logger.error(f"❌ {error}")
                return None, error
            
            data = response.json()
            items = data.get('order_items', [])
            return items, None
            
        except requests.exceptions.Timeout:
            return None, "Timeout durante il recupero items"
        except Exception as e:
            return None, f"Errore recupero items: {str(e)}"
    
    def _update_single_item_state(self, update: Dict) -> bool:
        """
        Esegue update singolo di un item
        IMPORTANTE: Refurbed richiede "id" NON "order_item_id"!
        """
        try:
            url = f"{self.base_url}/refb.merchant.v1.OrderItemService/UpdateOrderItemState"
            
            # FORMATO CORRETTO secondo supporto Refurbed: usa "id" invece di "order_item_id"
            body = {
                "id": update['order_item_id'],  # Il campo si chiama "id" nell'API!
                "state": update['state']
            }
            
            logger.info(f"📤 Request URL: {url}")
            logger.info(f"📤 Request body (formato corretto): {body}")
            
            response = requests.post(url, headers=self.headers, json=body, timeout=30)
            
            logger.info(f"📥 Response status: {response.status_code}")
            logger.info(f"📥 Response body: {response.text[:1000]}")
            
            if response.status_code == 200:
                logger.info(f"✅ Update singolo completato con successo")
                return True
            else:
                logger.error(f"❌ Update fallito: HTTP {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Errore update singolo: {e}")
            return False
    
    def _batch_update_items_state(self, updates: List[Dict]) -> bool:
        """
        Esegue batch update degli stati items
        IMPORTANTE: Batch usa "order_item_id", singolo usa "id"!
        """
        try:
            url = f"{self.base_url}/refb.merchant.v1.OrderItemService/BatchUpdateOrderItemsState"
            
            # Per batch update, il campo rimane "order_item_id" (non "id")
            body = {"updates": updates}
            
            logger.info(f"📤 Request URL: {url}")
            logger.info(f"📤 Request body: {body}")
            logger.info(f"📤 Headers: {self.headers}")
            
            response = requests.post(url, headers=self.headers, json=body, timeout=30)
            
            logger.info(f"📥 Response status: {response.status_code}")
            logger.info(f"📥 Response headers: {dict(response.headers)}")
            logger.info(f"📥 Response body: {response.text[:1000]}")
            
            # Controlla se ci sono errori nella risposta
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    results = response_data.get('results', [])
                    
                    # Verifica se ci sono errori nei risultati
                    errors = []
                    for idx, result in enumerate(results):
                        status = result.get('status', {})
                        code = status.get('code', 0)
                        message = status.get('message', '')
                        
                        if code != 0:  # code 0 = success in gRPC
                            errors.append(f"Item {idx}: {message} (code {code})")
                            logger.error(f"❌ Errore item {idx}: {message}")
                    
                    if errors:
                        logger.error(f"❌ Batch update ha restituito errori: {'; '.join(errors)}")
                        return False
                    
                    logger.info(f"✅ Batch update completato con successo")
                    return True
                except:
                    # Se non riusciamo a parsare JSON, assumiamo successo
                    logger.info(f"✅ Batch update completato (response non JSON)")
                    return True
            else:
                logger.error(f"❌ Batch update fallito: HTTP {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Errore batch update: {e}")
            return False
    
    def _verify_order_state(self, order_id: str) -> str:
        """Verifica lo stato finale dell'ordine"""
        try:
            url = f"{self.base_url}/refb.merchant.v1.OrderService/GetOrder"
            body = {"order_id": order_id}
            
            response = requests.post(url, headers=self.headers, json=body, timeout=10)
            if response.status_code == 200:
                data = response.json()
                order = data.get('order', {})
                state = order.get('state', 'UNKNOWN')
                logger.info(f"📊 Stato ordine verificato: {state}")
                return state
            return ""
        except Exception as e:
            logger.warning(f"⚠️  Impossibile verificare stato: {e}")
            return ""
    
    def mark_as_shipped(self, order_item_id: str, tracking_url: str) -> Tuple[bool, str]:
        """
        Marca un order item come spedito con tracking URL
        
        Args:
            order_item_id: ID dell'order item
            tracking_url: URL completo di tracking (es: https://www.ups.com/track?...)
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            logger.info(f"📦 REFURBED: Marcatura spedizione item {order_item_id}")
            logger.info(f"🔗 Tracking URL: {tracking_url}")
            
            url = f"{self.base_url}/refb.merchant.v1.OrderItemService/UpdateOrderItemState"
            
            # Formato corretto: "id" (non "order_item_id")
            body = {
                "id": str(order_item_id),
                "state": "SHIPPED",
                "parcel_tracking_url": tracking_url
            }
            
            logger.info(f"📤 Request: {body}")
            
            response = requests.post(url, headers=self.headers, json=body, timeout=30)
            
            logger.info(f"📥 Response status: {response.status_code}")
            logger.info(f"📥 Response: {response.text[:500]}")
            
            if response.status_code == 200:
                logger.info(f"✅ Item {order_item_id} marcato come spedito")
                return True, f"Item spedito con successo (tracking: {tracking_url[:50]}...)"
            else:
                error = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"❌ {error}")
                return False, error
                
        except Exception as e:
            logger.error(f"❌ Errore mark_as_shipped: {e}")
            return False, str(e)
    
    def disable_offer(self, sku: str) -> bool:
        """Disabilita offerta (stock = 0)"""
        try:
            logger.info(f"🔧 Refurbed: disabilitazione offerta SKU {sku}")
            url = f"{self.base_url}/refb.merchant.v1.OfferService/UpdateOffer"
            body = {"identifier": {"sku": sku}, "stock": 0}
            
            response = requests.post(url, headers=self.headers, json=body, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"✅ Offerta SKU {sku} disabilitata")
                return True
            else:
                logger.warning(f"⚠️  SKU {sku}: HTTP {response.status_code}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Errore disable_offer: {e}")
            return False
    
    def get_order_details(self, order_id: str) -> Dict:
        """Recupera dettagli completi di un ordine (per debug)"""
        try:
            url = f"{self.base_url}/refb.merchant.v1.OrderService/GetOrder"
            body = {"order_id": order_id}
            
            response = requests.post(url, headers=self.headers, json=body, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('order', {})
            else:
                logger.error(f"❌ Errore dettagli ordine {order_id}: HTTP {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"❌ Errore get_order_details: {e}")
            return {}
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
        Disabilita un listing su BackMarket impostando quantity a 0
        
        Usa l'endpoint POST /ws/listings con formato CSV batch.
        Secondo il supporto BackMarket: "This endpoint has very few required fields, 
        and you could update a listing with only its SKU and quantity."
        
        Documentazione: https://api.backmarket.dev/#/paths/ws-listings/post
        
        Args:
            listing_id: SKU del prodotto da disabilitare
            
        Returns:
            True se successo o listing non trovato, False se errore critico
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"[BACKMARKET-DISABLE] 🔧 Disabilitazione listing BackMarket")
            logger.info(f"[BACKMARKET-DISABLE] SKU: '{listing_id}'")
            logger.info(f"{'='*60}")
            
            if not listing_id or listing_id.strip() == '':
                logger.error(f"[BACKMARKET-DISABLE] ❌ SKU vuoto!")
                return False
            
            sku = listing_id.strip()
            
            # Crea CSV con header e una riga: sku,quantity
            # Usa \r\n per line endings come nell'esempio BackMarket
            csv_content = f"sku,quantity\r\n{sku},0"
            
            url = f"{self.base_url}/ws/listings"
            data = {
                "catalog": csv_content,
                "delimiter": ",",
                "quotechar": "\"",
                "encoding": "utf-8"
            }
            
            logger.info(f"[BACKMARKET-DISABLE] POST {url}")
            logger.info(f"[BACKMARKET-DISABLE] CSV Content: {repr(csv_content)}")
            logger.info(f"[BACKMARKET-DISABLE] Body: {data}")
            
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            
            logger.info(f"[BACKMARKET-DISABLE] Status: {response.status_code}")
            logger.info(f"[BACKMARKET-DISABLE] Response: {response.text[:500]}")
            
            # 200 = success, 201 = created (shouldn't happen), 202 = accepted (async processing)
            if response.status_code in [200, 201, 202]:
                logger.info(f"✅ Listing BackMarket con SKU {sku} disabilitato con successo")
                return True
            elif response.status_code == 404:
                logger.warning(f"⚠️ Listing con SKU {sku} non trovato su BackMarket")
                logger.warning(f"⚠️ Il prodotto potrebbe non essere presente su questo marketplace")
                return True  # Non blocchiamo il flusso
            elif response.status_code == 400:
                response_text = response.text[:300]
                logger.warning(f"⚠️ Errore 400 per SKU {sku}")
                logger.warning(f"⚠️ Response: {response_text}")
                
                # Controlla se è un errore "listing non trovato"
                if any(err in response_text.lower() for err in ['not found', 'non trouvé', 'does not exist', 'n\'existe pas']):
                    logger.warning(f"⚠️ Il listing non esiste su BackMarket")
                    return True  # Non blocchiamo il flusso
                
                # Altri errori 400 sono problemi di formato/validazione
                logger.error(f"❌ Errore di validazione BackMarket (possibile problema formato CSV)")
                return False
            else:
                logger.error(f"❌ Disabilitazione fallita - HTTP {response.status_code}")
                logger.error(f"❌ Response: {response.text[:300]}")
                return False
        
        except requests.exceptions.Timeout:
            logger.error(f"[BACKMARKET-DISABLE] ⏱️ Timeout durante disabilitazione")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"[BACKMARKET-DISABLE] ❌ Errore richiesta HTTP: {e}")
            return False
        except Exception as e:
            logger.error(f"[BACKMARKET-DISABLE] ❌ Errore generico: {e}")
            logger.exception(e)
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
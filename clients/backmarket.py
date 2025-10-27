#!/usr/bin/env python3
"""
Client BackMarket API
"""
import requests
import logging
from typing import List, Dict, Tuple

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
        
        Strategia a 3 step:
        1. Prova disabilitazione diretta con POST
        2. Se riceve 404 o 400 "Listing ID must be...", prova GET diretta
        3. Riprova disabilitazione con il listing_id corretto trovato
        
        Args:
            listing_id: Può essere sia listing_id numerico/UUID che SKU
            
        Returns:
            True se successo o listing non trovato, False se errore critico
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"[BACKMARKET-DISABLE] 🔧 Disabilitazione listing BackMarket")
            logger.info(f"[BACKMARKET-DISABLE] Input ricevuto: '{listing_id}'")
            logger.info(f"{'='*60}")
            
            if not listing_id or listing_id.strip() == '':
                logger.error(f"[BACKMARKET-DISABLE] ❌ Input vuoto!")
                return False
            
            listing_id = listing_id.strip()
            
            # STEP 1: Prova disabilitazione diretta
            logger.info(f"[BACKMARKET-DISABLE] STEP 1: Tentativo disabilitazione diretta")
            success, needs_search = self._try_disable_listing(listing_id)
            
            if success:
                logger.info(f"✅ Listing BackMarket {listing_id} disabilitato con successo (tentativo diretto)")
                return True
            
            if not needs_search:
                # Errore diverso da 404/400, non proviamo la ricerca
                logger.error(f"❌ Disabilitazione fallita con errore critico, interrompo")
                return False
            
            # STEP 2: Listing non trovato o SKU non valido, prova GET diretta
            logger.info(f"[BACKMARKET-DISABLE] STEP 2: Listing non trovato o SKU non valido come listing_id")
            logger.info(f"[BACKMARKET-DISABLE] 🔍 Provo GET diretta su /ws/listings/{listing_id}")
            
            try:
                # Prova GET diretta - BackMarket potrebbe accettare SKU nel path per GET
                get_url = f"{self.base_url}/ws/listings/{listing_id}"
                
                logger.info(f"[BACKMARKET-DISABLE] GET {get_url}")
                
                get_response = requests.get(
                    get_url, 
                    headers=self.headers, 
                    timeout=10
                )
                
                logger.info(f"[BACKMARKET-DISABLE] GET Status: {get_response.status_code}")
                logger.info(f"[BACKMARKET-DISABLE] GET Response: {get_response.text[:500]}")
                
                if get_response.status_code == 200:
                    listing_data = get_response.json()
                    
                    # Estrai il listing_id dalla risposta
                    actual_listing_id = (
                        listing_data.get('id') or 
                        listing_data.get('listing_id')
                    )
                    
                    if actual_listing_id:
                        logger.info(f"[BACKMARKET-DISABLE] ✅ Listing trovato tramite GET diretta!")
                        logger.info(f"[BACKMARKET-DISABLE]    Listing ID: {actual_listing_id}")
                        logger.info(f"[BACKMARKET-DISABLE]    SKU: {listing_data.get('sku')}")
                        logger.info(f"[BACKMARKET-DISABLE]    Titolo: {listing_data.get('title', '')[:60]}")
                        logger.info(f"[BACKMARKET-DISABLE]    Quantity attuale: {listing_data.get('quantity')}")
                        
                        # STEP 3: Riprova disabilitazione con listing_id corretto
                        logger.info(f"[BACKMARKET-DISABLE] STEP 3: Riprovo con listing_id {actual_listing_id}")
                        success, _ = self._try_disable_listing(str(actual_listing_id))
                        
                        if success:
                            logger.info(f"✅ Listing BackMarket {actual_listing_id} (SKU: {listing_id}) disabilitato con successo")
                            return True
                        else:
                            logger.error(f"❌ Disabilitazione fallita anche con listing_id corretto")
                            return False
                    else:
                        logger.warning(f"⚠️ GET riuscita ma listing_id non trovato nella risposta")
                        return True  # Non blocchiamo
                
                elif get_response.status_code == 404:
                    logger.warning(f"⚠️ GET diretta restituisce 404 - listing non trovato")
                    logger.warning(f"⚠️ Il prodotto potrebbe non essere su BackMarket o già disabilitato")
                    return True  # Non blocchiamo il flusso
                
                elif get_response.status_code == 400:
                    logger.warning(f"⚠️ GET diretta restituisce 400 - SKU non valido anche per GET")
                    logger.warning(f"⚠️ Il prodotto potrebbe non essere su BackMarket")
                    return True  # Non blocchiamo il flusso
                
                else:
                    logger.warning(f"⚠️ GET fallita con status {get_response.status_code}")
                    return True  # Non blocchiamo il flusso
                    
            except requests.exceptions.Timeout:
                logger.error(f"[BACKMARKET-DISABLE] ⏱️ Timeout durante GET diretta")
                return True  # Non blocchiamo il flusso
            except Exception as e:
                logger.error(f"[BACKMARKET-DISABLE] ❌ Errore durante GET diretta: {e}")
                return True  # Non blocchiamo il flusso
        
        except Exception as e:
            logger.error(f"[BACKMARKET-DISABLE] ❌ Errore generico: {e}")
            logger.exception(e)
            return False
    
    def _try_disable_listing(self, listing_id: str) -> Tuple[bool, bool]:
        """
        Tenta di disabilitare un listing con POST
        
        Args:
            listing_id: ID del listing da disabilitare (deve essere numerico o UUID)
            
        Returns:
            Tupla (success, needs_search):
            - success: True se disabilitato con successo
            - needs_search: True se ha ricevuto 404/400 e dovrebbe fare ulteriori tentativi
        """
        try:
            url = f"{self.base_url}/ws/listings/{listing_id}"
            data = {"quantity": 0}
            
            logger.info(f"[BACKMARKET-DISABLE]   POST {url}")
            logger.info(f"[BACKMARKET-DISABLE]   Body: {data}")
            
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            
            logger.info(f"[BACKMARKET-DISABLE]   Status: {response.status_code}")
            logger.info(f"[BACKMARKET-DISABLE]   Response: {response.text[:200]}")
            
            if response.status_code in [200, 204]:
                return (True, False)  # Success, no need to search
            elif response.status_code == 404:
                logger.info(f"[BACKMARKET-DISABLE]   Listing non trovato (404)")
                return (False, True)  # Failed, needs search
            elif response.status_code == 400 and "Listing ID must be" in response.text:
                # SKU alfanumerico non valido come listing_id, prova GET per recuperare l'ID
                logger.info(f"[BACKMARKET-DISABLE]   SKU non valido come listing_id (400)")
                return (False, True)  # Failed, needs search
            else:
                logger.error(f"[BACKMARKET-DISABLE]   Errore HTTP {response.status_code}")
                return (False, False)  # Other error, don't search
        
        except requests.exceptions.Timeout:
            logger.error(f"[BACKMARKET-DISABLE]   ⏱️ Timeout")
            return (False, False)
        except Exception as e:
            logger.error(f"[BACKMARKET-DISABLE]   Errore: {e}")
            return (False, False)
    
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
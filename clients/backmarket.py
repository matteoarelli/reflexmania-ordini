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
        
        Gestisce due scenari:
        1. Se listing_id è numerico (>= 6 cifre) → usa direttamente
        2. Se listing_id è uno SKU → cerca prima il listing_id tramite API
        
        Args:
            listing_id: Può essere sia SKU che listing_id numerico
            
        Returns:
            True se successo o listing non trovato, False se errore critico
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"[BACKMARKET-DISABLE] 🔧 Disabilitazione listing BackMarket")
            logger.info(f"[BACKMARKET-DISABLE] Input ricevuto: '{listing_id}'")
            logger.info(f"[BACKMARKET-DISABLE] Tipo: {type(listing_id)}")
            
            if not listing_id or listing_id.strip() == '':
                logger.error(f"[BACKMARKET-DISABLE] ❌ Input vuoto!")
                return False
            
            listing_id = listing_id.strip()
            actual_listing_id = listing_id
            
            # STEP 1: Determina se è uno SKU o un listing_id
            # Euristica: se non è numerico puro o ha meno di 6 cifre, è probabilmente uno SKU
            is_likely_sku = not listing_id.isdigit() or len(listing_id) < 6
            
            logger.info(f"[BACKMARKET-DISABLE] È probabilmente uno SKU: {is_likely_sku}")
            
            if is_likely_sku:
                # Cerca il listing tramite SKU
                logger.info(f"[BACKMARKET-DISABLE] 🔍 Ricerca listing con SKU '{listing_id}'...")
                
                try:
                    search_url = f"{self.base_url}/ws/listings"
                    params = {'sku': listing_id}
                    
                    logger.info(f"[BACKMARKET-DISABLE] URL ricerca: {search_url}")
                    logger.info(f"[BACKMARKET-DISABLE] Params: {params}")
                    
                    search_response = requests.get(
                        search_url, 
                        headers=self.headers, 
                        params=params, 
                        timeout=10
                    )
                    
                    logger.info(f"[BACKMARKET-DISABLE] Response ricerca: {search_response.status_code}")
                    
                    if search_response.status_code == 200:
                        listings = search_response.json()
                        logger.info(f"[BACKMARKET-DISABLE] Listings trovati: {len(listings) if isinstance(listings, list) else 'N/A'}")
                        
                        if isinstance(listings, list) and len(listings) > 0:
                            # Cerca il listing_id nella risposta
                            first_listing = listings[0]
                            actual_listing_id = (
                                first_listing.get('id') or 
                                first_listing.get('listing_id') or
                                listing_id
                            )
                            
                            logger.info(f"[BACKMARKET-DISABLE] ✅ Listing trovato!")
                            logger.info(f"[BACKMARKET-DISABLE] Listing ID estratto: {actual_listing_id}")
                            logger.info(f"[BACKMARKET-DISABLE] SKU: {first_listing.get('sku')}")
                            logger.info(f"[BACKMARKET-DISABLE] Titolo: {first_listing.get('title', '')[:50]}")
                        else:
                            logger.warning(f"[BACKMARKET-DISABLE] ⚠️ Nessun listing trovato con SKU '{listing_id}'")
                            logger.warning(f"[BACKMARKET-DISABLE] Il prodotto potrebbe non essere su BackMarket o già disabilitato")
                            return True  # Non blocchiamo il flusso
                    else:
                        logger.warning(f"[BACKMARKET-DISABLE] ⚠️ Ricerca fallita: HTTP {search_response.status_code}")
                        logger.warning(f"[BACKMARKET-DISABLE] Response: {search_response.text[:200]}")
                        # Proviamo comunque con l'input originale
                        
                except requests.exceptions.Timeout:
                    logger.error(f"[BACKMARKET-DISABLE] ⏱️ Timeout durante ricerca listing")
                    return True  # Non blocchiamo
                except Exception as e:
                    logger.error(f"[BACKMARKET-DISABLE] ❌ Errore durante ricerca: {e}")
                    # Proviamo comunque con l'input originale
            
            # STEP 2: Disabilita il listing
            logger.info(f"[BACKMARKET-DISABLE] 🎯 Listing ID finale: '{actual_listing_id}'")
            logger.info(f"{'='*60}")
            
            url = f"{self.base_url}/ws/listings/{actual_listing_id}"
            data = {"quantity": 0}
            
            logger.info(f"[BACKMARKET-DISABLE] POST {url}")
            logger.info(f"[BACKMARKET-DISABLE] Body: {data}")
            
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            
            logger.info(f"[BACKMARKET-DISABLE] Response Status: {response.status_code}")
            logger.info(f"[BACKMARKET-DISABLE] Response: {response.text[:300]}")
            
            if response.status_code in [200, 204]:
                logger.info(f"✅ Listing BackMarket disabilitato con successo")
                logger.info(f"   Listing ID: {actual_listing_id}")
                if is_likely_sku:
                    logger.info(f"   SKU originale: {listing_id}")
                return True
            elif response.status_code == 404:
                logger.warning(f"⚠️ Listing {actual_listing_id} non trovato (404)")
                logger.warning(f"   Potrebbe essere già disabilitato o non esistere")
                return True  # Non blocchiamo
            else:
                logger.error(f"❌ Disabilitazione fallita - HTTP {response.status_code}")
                logger.error(f"   Response: {response.text[:300]}")
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
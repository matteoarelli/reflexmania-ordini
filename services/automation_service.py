#!/usr/bin/env python3
"""
Servizio di automazione ordini
Accetta ordini e crea DDT automaticamente
"""
import logging
from datetime import datetime
from typing import List, Dict
import requests
import os

logger = logging.getLogger(__name__)


class AutomationService:
    def __init__(
        self,
        backmarket_client,
        refurbed_client,
        magento_service,
        ddt_service,
        order_service
    ):
        self.backmarket = backmarket_client
        self.refurbed = refurbed_client
        self.magento = magento_service
        self.ddt_service = ddt_service
        self.order_service = order_service
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        logger.info("🤖 AutomationService inizializzato")
    
    def process_all_pending_orders(self) -> Dict:
        """
        Processa automaticamente tutti gli ordini pendenti:
        1. Accetta ordini su marketplace
        2. Crea DDT su InvoiceX
        3. Notifica Telegram
        
        Returns:
            Statistiche di elaborazione
        """
        logger.info("=" * 60)
        logger.info("🤖 [AUTOMATION] INIZIO PROCESSO AUTOMATICO")
        logger.info("=" * 60)
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "orders_processed": 0,
            "orders_accepted": [],
            "ddts_created": [],
            "errors": []
        }
        
        try:
            # 1. RECUPERA ORDINI PENDENTI
            pending_orders = self._get_all_pending_orders()
            
            if not pending_orders:
                logger.info("✅ [AUTOMATION] Nessun ordine da processare")
                return results
            
            logger.info(f"📦 [AUTOMATION] Trovati {len(pending_orders)} ordini da processare")
            
            # 2. ACCETTA ORDINI E CREA DDT
            for order in pending_orders:
                try:
                    channel = order.get('channel', 'unknown')
                    order_id = order.get('order_id', 'unknown')
                    
                    logger.info(f"🔄 [AUTOMATION] Processo ordine {order_id} ({channel})")
                    
                    # Accetta ordine
                    accepted = self._accept_order(order)
                    
                    if accepted:
                        results['orders_accepted'].append({
                            'order_id': order_id,
                            'marketplace': channel
                        })
                        logger.info(f"✅ [AUTOMATION] Ordine {order_id} accettato")
                        
                        # Crea DDT
                        try:
                            ddt_id = self._create_ddt(order)
                            
                            # ✅ Non aggiungere a results se è stato skippato
                            if ddt_id != "SKIP":
                                results['ddts_created'].append({
                                    'order_id': order_id,
                                    'ddt_id': ddt_id,
                                    'marketplace': channel
                                })
                                logger.info(f"📄 [AUTOMATION] DDT {ddt_id} creato per ordine {order_id}")
                            else:
                                logger.info(f"ℹ️ [AUTOMATION] DDT già esistente per ordine {order_id}, skippato")
                                
                        except Exception as e:
                            error_msg = f"DDT fallito per {order_id}: {str(e)}"
                            logger.error(f"❌ [AUTOMATION] {error_msg}")
                            results['errors'].append(error_msg)
                    else:
                        error_msg = f"Accettazione fallita per {order_id}"
                        logger.error(f"❌ [AUTOMATION] {error_msg}")
                        results['errors'].append(error_msg)
                        
                except Exception as e:
                    error_msg = f"Errore ordine {order.get('order_id', 'unknown')}: {str(e)}"
                    logger.error(f"❌ [AUTOMATION] {error_msg}")
                    logger.exception(e)
                    results['errors'].append(error_msg)
            
            results['orders_processed'] = len(results['orders_accepted'])
            
            # 3. NOTIFICA TELEGRAM
            self._send_telegram_notification(results)
            
            logger.info("=" * 60)
            logger.info(f"✅ [AUTOMATION] COMPLETATO: {results['orders_processed']} ordini processati")
            logger.info("=" * 60)
            
        except Exception as e:
            error_msg = f"Errore generale automazione: {str(e)}"
            logger.error(f"❌ [AUTOMATION] {error_msg}")
            logger.exception(e)
            results['errors'].append(error_msg)
        
        return results
    
    def _get_all_pending_orders(self) -> List[Dict]:
        """Recupera tutti gli ordini pendenti da tutti i marketplace"""
        all_orders = []
        
        # BackMarket
        try:
            bm_orders = self.order_service.get_backmarket_pending_orders()
            logger.info(f"📦 [AUTOMATION] BackMarket: {len(bm_orders)} ordini pendenti")
            all_orders.extend(bm_orders)
        except Exception as e:
            logger.error(f"❌ [AUTOMATION] Errore recupero BackMarket: {e}")
        
        # Refurbed
        try:
            rf_orders = self.order_service.get_refurbed_pending_orders()
            logger.info(f"📦 [AUTOMATION] Refurbed: {len(rf_orders)} ordini pendenti")
            all_orders.extend(rf_orders)
        except Exception as e:
            logger.error(f"❌ [AUTOMATION] Errore recupero Refurbed: {e}")
        
        # Magento
        try:
            mg_orders = self.order_service.get_magento_pending_orders()
            logger.info(f"📦 [AUTOMATION] Magento: {len(mg_orders)} ordini pendenti")
            all_orders.extend(mg_orders)
        except Exception as e:
            logger.error(f"❌ [AUTOMATION] Errore recupero Magento: {e}")
        
        return all_orders
    
    def _accept_order(self, order: Dict) -> bool:
        """Accetta un ordine sul marketplace"""
        marketplace = order.get('channel', 'unknown')
        order_id = order['order_id']
        
        try:
            if marketplace == 'backmarket':
                return self.backmarket.accept_order(order_id)
            elif marketplace == 'refurbed':
                return self.refurbed.accept_order(order_id)
            elif marketplace == 'magento':
                # Magento non ha accettazione esplicita
                return True
            else:
                logger.warning(f"⚠️ [AUTOMATION] Marketplace sconosciuto: {marketplace}")
                return False
        except Exception as e:
            logger.error(f"❌ [AUTOMATION] Errore accettazione {marketplace} {order_id}: {e}")
            return False
    
    def _create_ddt(self, order: Dict) -> str:
        """Crea DDT su InvoiceX"""
        try:
            # Usa il metodo corretto del DDTService
            result = self.ddt_service.crea_ddt_da_ordine_marketplace(
                ordine=order,
                marketplace=order.get('channel', 'unknown')
            )
            
            # ✅ Gestisci caso DDT già esistente
            if result.get('skip'):
                logger.info(f"ℹ️ [AUTOMATION] DDT già esistente per ordine {order['order_id']}, skip")
                # Ritorna un ID fittizio per non far fallire il processo
                return "SKIP"
            
            if result.get('success'):
                ddt_id = result.get('ddt_id')
                logger.info(f"✅ [AUTOMATION] DDT {ddt_id} creato con successo")
                return ddt_id
            else:
                error_msg = result.get('error', 'Errore sconosciuto')
                logger.error(f"❌ [AUTOMATION] Errore creazione DDT: {error_msg}")
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"❌ [AUTOMATION] Errore creazione DDT: {e}")
            raise
    
    def _send_telegram_notification(self, results: Dict):
        """Invia notifica Telegram con riepilogo"""
        if not self.telegram_token or not self.telegram_chat_id:
            logger.info("ℹ️ [AUTOMATION] Telegram non configurato, skip notifica")
            return
        
        try:
            # Costruisci messaggio
            message = "🤖 *Automazione Ordini Completata*\n\n"
            message += f"📦 Ordini processati: *{results['orders_processed']}*\n"
            message += f"✅ Ordini accettati: *{len(results['orders_accepted'])}*\n"
            message += f"📄 DDT creati: *{len(results['ddts_created'])}*\n"
            
            # Dettagli DDT creati
            if results['ddts_created']:
                message += "\n*DDT creati:*\n"
                for ddt in results['ddts_created'][:5]:  # Max 5
                    marketplace = ddt['marketplace'].upper()
                    message += f"• {marketplace} {ddt['order_id']}: DDT #{ddt['ddt_id']}\n"
            
            # Errori
            if results['errors']:
                message += f"\n⚠️ Errori: *{len(results['errors'])}*\n"
                for error in results['errors'][:3]:  # Max 3
                    message += f"• {error}\n"
            
            message += f"\n🕐 {datetime.now().strftime('%H:%M:%S')}"
            
            # Invia a Telegram
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            response = requests.post(url, json={
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=10)
            
            if response.status_code == 200:
                logger.info("📱 [AUTOMATION] Notifica Telegram inviata")
            else:
                logger.warning(f"⚠️ [AUTOMATION] Notifica Telegram fallita: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ [AUTOMATION] Errore invio Telegram: {e}")
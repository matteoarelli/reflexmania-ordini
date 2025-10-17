"""
Service per creazione DDT usando API InvoiceX
"""

from clients.invoicex_api import InvoiceXAPIClient
from typing import Dict, List, Optional
import logging
import json


# Mappatura metodi pagamento Magento -> InvoiceX
MAGENTO_PAYMENT_MAP = {
    'paypal_express': 'PAYPAL',
    'paypal_standard': 'PAYPAL',
    'paypal': 'PAYPAL',
    'checkmo': 'BONIFICO BANCARIO',
    'banktransfer': 'BONIFICO BANCARIO',
    'cashondelivery': 'CONTRASSEGNO',
    'cashondelivery_fee': 'CONTRASSEGNO',
    'ccsave': 'CARTA DI CREDITO',
    'authorizenet': 'CARTA DI CREDITO',
    'stripe': 'CARTA DI CREDITO',
    'braintree': 'CARTA DI CREDITO',
    'free': 'PERMUTA',
}


class DDTService:
    """Service per gestione DDT vendita tramite API InvoiceX"""
    
    def __init__(self, api_client: InvoiceXAPIClient):
        self.api = api_client
        self.logger = logging.getLogger(__name__)
    
    def _get_invoicex_payment_method(self, ordine: Dict, marketplace: str) -> str:
        """
        Determina il metodo di pagamento corretto per InvoiceX
        
        Args:
            ordine: Ordine normalizzato
            marketplace: Nome marketplace ('backmarket', 'refurbed', 'cdiscount', 'magento')
        
        Returns:
            Codice metodo pagamento InvoiceX
        """
        marketplace_lower = marketplace.lower()
        
        # Marketplace con metodo fisso
        if marketplace_lower == 'backmarket':
            return 'BACKMARKET'
        elif marketplace_lower == 'refurbed':
            return 'REFURBED'
        elif marketplace_lower == 'cdiscount':
            return 'CDISCOUNT'
        
        # Magento: mappa dal payment_method dell'ordine
        elif marketplace_lower == 'magento':
            magento_method = ordine.get('payment_method', '').lower()
            
            # Cerca nella mappa
            mapped_method = MAGENTO_PAYMENT_MAP.get(magento_method)
            
            if mapped_method:
                self.logger.info(f"[PAYMENT] Magento '{magento_method}' -> '{mapped_method}'")
                return mapped_method
            else:
                self.logger.warning(f"[PAYMENT] Metodo Magento '{magento_method}' non mappato, uso CARTA DI CREDITO")
                return 'CARTA DI CREDITO'
        
        # Fallback generico
        self.logger.warning(f"[PAYMENT] Marketplace '{marketplace}' sconosciuto, uso CARTA DI CREDITO")
        return 'CARTA DI CREDITO'
    
    def crea_ddt_da_ordine_marketplace(
        self, 
        ordine: Dict,
        marketplace: str
    ) -> Dict:
        """
        Crea DDT completo da ordine marketplace
        
        Args:
            ordine: Dizionario ordine normalizzato
            marketplace: 'backmarket', 'refurbed', 'cdiscount', 'magento'
            
        Returns:
            Dict con success, ddt_id, codice_cliente, prodotti_ok, prodotti_errore, payment_method
        """
        try:
            self.logger.info(
                f"Creazione DDT per ordine {ordine.get('order_id')} da {marketplace}"
            )
            
            self.logger.info(f"Ordine ricevuto: email={ordine.get('customer_email')}, items={len(ordine.get('items', []))}")
            
            # 1. Estrai dati cliente
            cliente = self._estrai_dati_cliente(ordine, marketplace)
            if not cliente or not cliente.get('email'):
                return {'success': False, 'error': 'Dati cliente mancanti o email invalida'}
            
            self.logger.info(f"Cliente estratto: {cliente['email']}, nome={cliente.get('firstname')} {cliente.get('lastname')}")
            
            # 2. Assicura cliente esista
            codice_cliente = self.api.assicura_cliente_esista(cliente)
            if not codice_cliente:
                return {'success': False, 'error': 'Errore creazione/ricerca cliente'}
            
            self.logger.info(f"Codice cliente: {codice_cliente}")
            
            # 3. Determina metodo pagamento InvoiceX
            payment_method = self._get_invoicex_payment_method(ordine, marketplace)
            
            # 4. Prepara dati ordine con metodo pagamento
            order_id = ordine.get('order_id', '')
            order_data = {
                'riferimento': f"{marketplace.upper()}-{order_id}",
                'metodo_pagamento': payment_method
            }
            
            # 5. Crea DDT con metodo pagamento
            id_ddt = self.api.crea_ddt_vendita(codice_cliente, order_data)
            
            if not id_ddt:
                return {'success': False, 'error': 'Errore creazione DDT'}
            
            self.logger.info(f"DDT creato: {id_ddt} con metodo pagamento: {payment_method}")
            
            # 6. Movimenta prodotti
            prodotti = ordine.get('items', [])
            if not prodotti:
                return {'success': False, 'error': 'Nessun prodotto nell\'ordine'}
            
            # 🆕 LOG DETTAGLIATO DEGLI ITEMS
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"[DDT-DEBUG] INIZIO MOVIMENTAZIONE PRODOTTI")
            self.logger.info(f"[DDT-DEBUG] Ordine ID: {ordine.get('order_id')}")
            self.logger.info(f"[DDT-DEBUG] Marketplace: {marketplace}")
            self.logger.info(f"[DDT-DEBUG] Numero items nell'ordine: {len(prodotti)}")
            self.logger.info(f"[DDT-DEBUG] Items completi:")
            for idx, p in enumerate(prodotti):
                self.logger.info(f"[DDT-DEBUG]   Item #{idx+1}: {json.dumps(p, indent=4, default=str)}")
            self.logger.info(f"{'='*80}\n")
            
            prodotti_ok = []
            prodotti_errore = []
            
            riga = 2
            
            # 🆕 CONTATORE CHIAMATE API
            chiamate_api = 0
            
            for idx, prodotto in enumerate(prodotti):
                seriale = prodotto.get('sku', '')
                prezzo = float(prodotto.get('price', 0))
                
                if prezzo == 0:
                    prezzo = float(prodotto.get('unit_price', 0))
                
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"[DDT-LOOP] Iterazione #{idx+1} di {len(prodotti)}")
                self.logger.info(f"[DDT-LOOP] SKU: {seriale}")
                self.logger.info(f"[DDT-LOOP] Prezzo: {prezzo}")
                self.logger.info(f"[DDT-LOOP] Riga DDT: {riga}")
                self.logger.info(f"{'='*60}")
                
                if not seriale:
                    prodotti_errore.append(f"Riga {riga} - seriale mancante")
                    riga += 1
                    continue
                
                if prezzo == 0:
                    self.logger.warning(f"Prezzo 0 per prodotto {seriale}")
                
                # 🆕 LOG PRIMA DELLA CHIAMATA API
                self.logger.info(f"[DDT-API] ⏳ STO PER CHIAMARE movimenta_prodotto_ddt()")
                self.logger.info(f"[DDT-API]    DDT ID: {id_ddt}")
                self.logger.info(f"[DDT-API]    Seriale: {seriale}")
                self.logger.info(f"[DDT-API]    Prezzo: {prezzo}")
                self.logger.info(f"[DDT-API]    Riga: {riga}")
                
                chiamate_api += 1
                
                if self.api.movimenta_prodotto_ddt(id_ddt, seriale, prezzo, riga):
                    prodotti_ok.append(seriale)
                    self.logger.info(f"[DDT-API] ✅ Chiamata #{chiamate_api} SUCCESSO")
                else:
                    prodotti_errore.append(seriale)
                    self.logger.error(f"[DDT-API] ❌ Chiamata #{chiamate_api} FALLITA")
                
                riga += 1
            
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"[DDT-DEBUG] FINE MOVIMENTAZIONE PRODOTTI")
            self.logger.info(f"[DDT-DEBUG] Totale chiamate API effettuate: {chiamate_api}")
            self.logger.info(f"[DDT-DEBUG] Prodotti OK: {len(prodotti_ok)}")
            self.logger.info(f"[DDT-DEBUG] Prodotti ERRORE: {len(prodotti_errore)}")
            self.logger.info(f"{'='*80}\n")
            
            return {
                'success': True,
                'ddt_id': id_ddt,
                'codice_cliente': codice_cliente,
                'prodotti_ok': prodotti_ok,
                'prodotti_errore': prodotti_errore,
                'payment_method': payment_method,
                'warning': None if not prodotti_errore else 'Alcuni prodotti non movimentati'
            }
            
        except Exception as e:
            self.logger.error(f"Errore creazione DDT: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _estrai_dati_cliente(self, ordine: Dict, marketplace: str) -> Dict:
        """Estrae dati cliente da ordine già normalizzato"""
        
        # Per Magento (struttura diversa con customer object)
        if 'customer' in ordine and isinstance(ordine['customer'], dict):
            customer = ordine['customer']
            return {
                'email': customer.get('email', ''),
                'firstname': customer.get('name', ''),
                'lastname': customer.get('surname', ''),
                'street': customer.get('address', ''),
                'postcode': customer.get('zip', ''),
                'city': customer.get('city', ''),
                'region': customer.get('country', 'IT')[:2],
                'telephone': customer.get('phone', '')
            }
        
        # Per Marketplace (BackMarket, Refurbed, CDiscount)
        customer_name = ordine.get('customer_name', '')
        
        # Split solo al primo spazio
        if customer_name:
            name_parts = customer_name.split(' ', 1)
            firstname = name_parts[0] if name_parts else ''
            lastname = name_parts[1] if len(name_parts) > 1 else ''
        else:
            firstname = ''
            lastname = ''
        
        return {
            'email': ordine.get('customer_email', ''),
            'firstname': firstname,
            'lastname': lastname,
            'street': ordine.get('address', ''),
            'postcode': ordine.get('postal_code', ''),
            'city': ordine.get('city', ''),
            'region': ordine.get('country', 'IT')[:2],
            'telephone': ordine.get('customer_phone', '')
        }
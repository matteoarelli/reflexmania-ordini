"""
Service per creazione DDT usando API InvoiceX
"""

from clients.invoicex_api import InvoiceXAPIClient
from typing import Dict, List, Optional
import logging


class DDTService:
    """Service per gestione DDT vendita tramite API InvoiceX"""
    
    def __init__(self, api_client: InvoiceXAPIClient):
        self.api = api_client
        self.logger = logging.getLogger(__name__)
    
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
            Dict con success, ddt_id, codice_cliente, prodotti_ok, prodotti_errore
        """
        try:
            self.logger.info(
                f"Creazione DDT per ordine {ordine.get('order_id')} da {marketplace}"
            )
            
            # Debug: stampa l'ordine
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
            
            # 3. Prepara dati ordine con metodo pagamento
            order_data = self._prepara_dati_ordine(ordine, marketplace)
            
            # 4. Crea DDT vuoto
            id_ddt = self.api.crea_ddt_vendita(codice_cliente, order_data['riferimento'])
            
            if not id_ddt:
                return {'success': False, 'error': 'Errore creazione DDT'}
            
            self.logger.info(f"DDT creato: {id_ddt}")
            
            # 5. Movimenta prodotti
            prodotti = ordine.get('items', [])
            if not prodotti:
                return {'success': False, 'error': 'Nessun prodotto nell\'ordine'}
            
            prodotti_ok = []
            prodotti_errore = []
            
            riga = 2  # Inizio riga prodotti
            
            for prodotto in prodotti:
                seriale = prodotto.get('sku', '')
                prezzo = float(prodotto.get('price', 0))
                
                # Se il prezzo è 0, prova altri campi
                if prezzo == 0:
                    prezzo = float(prodotto.get('unit_price', 0))
                
                self.logger.info(f"Prodotto riga {riga}: sku={seriale}, prezzo={prezzo}")
                
                if not seriale:
                    prodotti_errore.append(f"Riga {riga} - seriale mancante")
                    riga += 1
                    continue
                
                if prezzo == 0:
                    self.logger.warning(f"Prezzo 0 per prodotto {seriale}")
                
                if self.api.movimenta_prodotto_ddt(id_ddt, seriale, prezzo, riga):
                    prodotti_ok.append(seriale)
                else:
                    prodotti_errore.append(seriale)
                
                riga += 1
            
            # 6. Aggiungi metodo di pagamento come nota al DDT
            payment_method = order_data['payment_method']
            self._aggiungi_metodo_pagamento(id_ddt, payment_method)
            
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
        name_parts = ordine.get('customer_name', '').split()
        firstname = name_parts[0] if name_parts else ''
        lastname = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        
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
    
    def _prepara_dati_ordine(self, ordine: Dict, marketplace: str) -> Dict:
        """Prepara dati ordine includendo metodo di pagamento"""
        
        # Mappa marketplace → metodo pagamento
        payment_methods = {
            'backmarket': 'BACKMARKET',
            'refurbed': 'REFURBED',
            'cdiscount': 'CDISCOUNT',
            'magento': 'MAGENTO'
        }
        
        payment_method = payment_methods.get(marketplace.lower(), marketplace.upper())
        order_id = ordine.get('order_id', '')
        
        return {
            'riferimento': f"{marketplace.upper()}-{order_id}",
            'payment_method': payment_method
        }
    
    def _aggiungi_metodo_pagamento(self, ddt_id: str, payment_method: str):
        """Aggiungi metodo di pagamento come nota al DDT"""
        try:
            # Questa è una chiamata opzionale - se l'API InvoiceX supporta note/metadati
            # Altrimenti il payment_method è già nel riferimento
            self.logger.info(f"DDT {ddt_id} - Metodo pagamento: {payment_method}")
        except Exception as e:
            self.logger.warning(f"Non è stato possibile aggiungere nota pagamento: {e}")
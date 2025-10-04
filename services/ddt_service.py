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
            
            # 1. Estrai dati cliente
            cliente = self._estrai_dati_cliente(ordine, marketplace)
            if not cliente or not cliente.get('email'):
                return {'success': False, 'error': 'Dati cliente mancanti'}
            
            # 2. Assicura cliente esista
            codice_cliente = self.api.assicura_cliente_esista(cliente)
            if not codice_cliente:
                return {'success': False, 'error': 'Errore creazione/ricerca cliente'}
            
            self.logger.info(f"Codice cliente: {codice_cliente}")
            
            # 3. Crea DDT vuoto
            riferimento = str(ordine.get('order_id', ''))
            id_ddt = self.api.crea_ddt_vendita(codice_cliente, riferimento)
            
            if not id_ddt:
                return {'success': False, 'error': 'Errore creazione DDT'}
            
            self.logger.info(f"DDT creato: {id_ddt}")
            
            # 4. Movimenta prodotti
            prodotti = ordine.get('products', [])
            if not prodotti:
                return {'success': False, 'error': 'Nessun prodotto nell\'ordine'}
            
            prodotti_ok = []
            prodotti_errore = []
            
            for idx, prodotto in enumerate(prodotti, start=2):
                seriale = prodotto.get('serial') or prodotto.get('sku', '')
                prezzo = float(prodotto.get('price', 0))
                
                if not seriale:
                    prodotti_errore.append(f"Riga {idx} - seriale mancante")
                    continue
                
                if self.api.movimenta_prodotto_ddt(id_ddt, seriale, prezzo, idx):
                    prodotti_ok.append(seriale)
                else:
                    prodotti_errore.append(seriale)
            
            tutti_ok = len(prodotti_errore) == 0
            
            return {
                'success': True,
                'ddt_id': id_ddt,
                'codice_cliente': codice_cliente,
                'prodotti_ok': prodotti_ok,
                'prodotti_errore': prodotti_errore,
                'warning': None if tutti_ok else 'Alcuni prodotti non movimentati'
            }
            
        except Exception as e:
            self.logger.error(f"Errore creazione DDT: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _estrai_dati_cliente(self, ordine: Dict, marketplace: str) -> Dict:
        """Estrae dati cliente da ordine marketplace"""
        
        if marketplace == 'backmarket':
            shipping = ordine.get('shipping_address', {})
            return {
                'email': ordine.get('customer_email') or f"{ordine.get('order_id')}@backmarket.local",
                'firstname': shipping.get('first_name', ''),
                'lastname': shipping.get('last_name', ''),
                'street': shipping.get('street', ''),
                'postcode': shipping.get('zip_code', ''),
                'city': shipping.get('city', ''),
                'region': shipping.get('state') or shipping.get('country', ''),
                'telephone': shipping.get('phone', '')
            }
        
        elif marketplace == 'refurbed':
            return {
                'email': ordine.get('email') or f"{ordine.get('id')}@refurbed.local",
                'firstname': ordine.get('shipping_first_name', ''),
                'lastname': ordine.get('shipping_last_name', ''),
                'street': ordine.get('shipping_street', ''),
                'postcode': ordine.get('shipping_zip', ''),
                'city': ordine.get('shipping_city', ''),
                'region': ordine.get('shipping_country', ''),
                'telephone': ordine.get('shipping_phone', '')
            }
        
        elif marketplace == 'cdiscount':
            return {
                'email': ordine.get('BuyerEmail') or f"{ordine.get('OrderNumber')}@cdiscount.local",
                'firstname': ordine.get('ShippingFirstName', ''),
                'lastname': ordine.get('ShippingLastName', ''),
                'street': ordine.get('ShippingAddress1', ''),
                'postcode': ordine.get('ShippingZipCode', ''),
                'city': ordine.get('ShippingCity', ''),
                'region': ordine.get('ShippingCountry', ''),
                'telephone': ordine.get('ShippingPhone', '')
            }
        
        elif marketplace == 'magento':
            shipping = ordine.get('shipping_address', {})
            return {
                'email': ordine.get('customer_email', ''),
                'firstname': shipping.get('first_name', ''),
                'lastname': shipping.get('last_name', ''),
                'street': shipping.get('street', ''),
                'postcode': shipping.get('zip_code', ''),
                'city': shipping.get('city', ''),
                'region': shipping.get('state') or shipping.get('country', ''),
                'telephone': shipping.get('phone', '')
            }
        
        return {}

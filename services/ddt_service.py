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
            
            # 3. Crea DDT vuoto
            riferimento = str(ordine.get('order_id', ''))
            id_ddt = self.api.crea_ddt_vendita(codice_cliente, riferimento)
            
            if not id_ddt:
                return {'success': False, 'error': 'Errore creazione DDT'}
            
            self.logger.info(f"DDT creato: {id_ddt}")
            
            # 4. Movimenta prodotti
            prodotti = ordine.get('items', [])
            if not prodotti:
                return {'success': False, 'error': 'Nessun prodotto nell\'ordine'}
            
            prodotti_ok = []
            prodotti_errore = []
            
            for idx, prodotto in enumerate(prodotti, start=2):
                seriale = prodotto.get('sku', '')
                prezzo = float(prodotto.get('price', 0))
                
                self.logger.info(f"Prodotto riga {idx}: sku={seriale}, prezzo={prezzo}")
                
                if not seriale:
                    prodotti_errore.append(f"Riga {idx} - seriale mancante")
                    continue
                
                if self.api.movimenta_prodotto_ddt(id_ddt, seriale, prezzo, idx):
                    prodotti_ok.append(seriale)
                else:
                    prodotti_errore.append(seriale)
            
            return {
                'success': True,
                'ddt_id': id_ddt,
                'codice_cliente': codice_cliente,
                'prodotti_ok': prodotti_ok,
                'prodotti_errore': prodotti_errore,
                'warning': None if not prodotti_errore else 'Alcuni prodotti non movimentati'
            }
            
        except Exception as e:
            self.logger.error(f"Errore creazione DDT: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _estrai_dati_cliente(self, ordine: Dict, marketplace: str) -> Dict:
        """Estrae dati cliente da ordine già normalizzato"""
        
        # Gli ordini sono già normalizzati da order_service
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
            'region': ordine.get('country', ''),
            'telephone': ordine.get('customer_phone', '')
        }
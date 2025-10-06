"""
Client per API InvoiceX - Versione con supporto metodo_pagamento
"""

import requests
from typing import Dict, List, Optional
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class InvoiceXAPIClient:
    """
    Client per API InvoiceX esterne (api.reflexmania.it)
    Gestisce creazione clienti, DDT e movimentazione prodotti
    """
    
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        
        # Configura sessione con retry automatici
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Headers comuni
        self.session.headers.update({
            'Apikey': api_key,
            'Content-Type': 'application/json'
        })
    
    def cerca_cliente_per_email(self, email: str) -> bool:
        """
        Verifica se un cliente esiste per email
        
        Args:
            email: Email cliente da cercare
            
        Returns:
            True se cliente esiste, False altrimenti
        """
        try:
            response = requests.get(
                f"{self.base_url}/cercapermail/{email}",
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            return data is not None and len(data) > 0
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Errore ricerca cliente {email}: {e}")
            return False
    
    def get_codice_cliente(self, email: str) -> Optional[str]:
        """
        Recupera codice cliente da email
        
        Args:
            email: Email cliente
            
        Returns:
            Codice cliente o None se non trovato
        """
        try:
            response = requests.get(
                f"{self.base_url}/recuperacodicedaemail/{email}",
                timeout=self.timeout
            )
            response.raise_for_status()
            
            codice = response.text.strip()
            if codice and codice != "0" and codice != "":
                return codice
            return None
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Errore recupero codice per {email}: {e}")
            return None
    
    def crea_cliente(self, dati_cliente: Dict) -> Optional[str]:
        """
        Crea nuovo cliente su InvoiceX
        
        Args:
            dati_cliente: Dict con chiavi:
                - firstname: Nome
                - lastname: Cognome
                - street: Indirizzo
                - postcode: CAP
                - city: Città
                - region: Provincia/Stato (primi 2 caratteri)
                - telephone: Telefono
                - email: Email (REQUIRED)
                - tax_code: Codice fiscale (opzionale)
                
        Returns:
            Codice cliente creato o None in caso di errore
        """
        payload = {
            'nome': dati_cliente.get('firstname', ''),
            'cognome': dati_cliente.get('lastname', ''),
            'indirizzo': dati_cliente.get('street', ''),
            'cap': dati_cliente.get('postcode', ''),
            'comune': dati_cliente.get('city', ''),
            'provincia': str(dati_cliente.get('region', ''))[:2].upper(),
            'telefono': dati_cliente.get('telephone', ''),
            'email': dati_cliente['email'],
            'cfiscale': dati_cliente.get('tax_code', '')
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/inserisci-cliente-da-magento",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            codice = str(data) if data else None
            
            if codice and codice != "0":
                self.logger.info(f"Cliente creato: {codice} ({payload['email']})")
                return codice
            
            self.logger.error(f"API ritornò codice invalido: {data}")
            return None
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Errore creazione cliente: {e}")
            return None
    
    def crea_ddt_vendita(
        self, 
        codice_cliente: str, 
        order_data: Dict
    ) -> Optional[str]:
        """
        Crea DDT vendita con riferimento e metodo pagamento
        
        Args:
            codice_cliente: Codice cliente InvoiceX
            order_data: Dict con 'riferimento' e 'metodo_pagamento'
            
        Returns:
            ID DDT creato o None in caso di errore
            
        Note:
            Questa API usa GET con body JSON
        """
        payload = {
            'riferimento': order_data.get('riferimento', ''),
            'metodo_pagamento': order_data.get('metodo_pagamento', '')
        }
        
        try:
            response = self.session.request(
                'GET',
                f"{self.base_url}/crea-ddt-vendita-codice/{codice_cliente}",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            ddt_id = response.text.strip()
            if ddt_id and ddt_id.isdigit():
                self.logger.info(
                    f"DDT creato: {ddt_id} (Cliente: {codice_cliente}, "
                    f"Rif: {payload['riferimento']}, Payment: {payload['metodo_pagamento']})"
                )
                return ddt_id
            
            self.logger.error(f"API ritornò ID DDT invalido: {response.text}")
            return None
            
        except requests.exceptions.RequestException as e:
            self.logger.error(
                f"Errore creazione DDT per cliente {codice_cliente}: {e}"
            )
            return None
    
    def movimenta_prodotto_ddt(
        self, 
        id_ddt: str, 
        matricola: str, 
        prezzo: float, 
        riga: int
    ) -> bool:
        """
        Aggiunge prodotto al DDT e crea movimento magazzino
        
        Args:
            id_ddt: ID DDT padre
            matricola: Seriale/SKU prodotto
            prezzo: Prezzo prodotto
            riga: Numero riga DDT
            
        Returns:
            True se successo, False altrimenti
        """
        payload = {
            'idPadreDDT': str(id_ddt),
            'matricola': str(matricola),
            'riga': str(riga),
            'prezzo': f"{float(prezzo):.2f}"
        }
        
        try:
            response = self.session.request(
                'GET',
                f"{self.base_url}/movimenta-ddt-vendita",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.text.strip()
            
            if result != "0":
                self.logger.info(
                    f"Prodotto movimentato: {matricola} (DDT: {id_ddt}, "
                    f"Riga: {riga})"
                )
                return True
            else:
                self.logger.warning(
                    f"Prodotto non trovato in magazzino: {matricola}"
                )
                return False
            
        except requests.exceptions.RequestException as e:
            self.logger.error(
                f"Errore movimentazione prodotto {matricola}: {e}"
            )
            return False
    
    def assicura_cliente_esista(self, dati_cliente: Dict) -> Optional[str]:
        """
        Verifica che cliente esista, creandolo se necessario
        
        Args:
            dati_cliente: Dati cliente (vedere crea_cliente per formato)
            
        Returns:
            Codice cliente o None se errore
        """
        email = dati_cliente.get('email')
        if not email:
            self.logger.error("Email mancante nei dati cliente")
            return None
        
        # Verifica se esiste
        if self.cerca_cliente_per_email(email):
            codice = self.get_codice_cliente(email)
            if codice:
                self.logger.info(f"Cliente esistente trovato: {codice}")
                return codice
        
        # Crea nuovo
        self.logger.info(f"Creazione nuovo cliente: {email}")
        return self.crea_cliente(dati_cliente)
    
    def health_check(self) -> bool:
        """
        Verifica connessione API
        
        Returns:
            True se API raggiungibile, False altrimenti
        """
        try:
            response = requests.get(
                f"{self.base_url}/cercapermail/test@healthcheck.com",
                timeout=5
            )
            return response.status_code in [200, 404]
        except Exception as e:
            self.logger.error(f"Health check fallito: {e}")
            return False
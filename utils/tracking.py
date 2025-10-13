#!/usr/bin/env python3
"""
Generatore URL di tracking per diversi corrieri
Da aggiungere in un nuovo file: utils/tracking.py
"""

def generate_tracking_url(carrier: str, tracking_number: str) -> str:
    """
    Genera l'URL di tracking completo basato sul corriere
    
    Args:
        carrier: Nome del corriere (UPS, DHL, BRT, GLS, TNT, FEDEX)
        tracking_number: Codice di tracking
    
    Returns:
        URL completo di tracking
    """
    carrier = carrier.upper().strip()
    tracking_number = tracking_number.strip()
    
    tracking_urls = {
        'UPS': f'https://www.ups.com/track?loc=en_US&tracknum={tracking_number}',
        'DHL': f'https://mydhl.express.dhl/it/it/tracking.html#/results?id={tracking_number}',
        'BRT': f'https://vas.brt.it/vas/sped_det_show.hsm?chisono={tracking_number}',
        'GLS': f'https://gls-group.eu/IT/it/ricerca-pacchi?match={tracking_number}',
        'TNT': f'https://www.tnt.com/express/it_it/site/tracking.html?searchType=con&cons={tracking_number}',
        'FEDEX': f'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
        'POSTE': f'https://www.poste.it/cerca/index.html#/risultati-spedizioni/{tracking_number}',
        'SDA': f'https://www.sda.it/wps/portal/Servizi_online/dettaglio-spedizione?locale=it&tracing.letteraVettura={tracking_number}'
    }
    
    url = tracking_urls.get(carrier)
    
    if not url:
        # Fallback: ritorna il numero senza URL
        return tracking_number
    
    return url


def get_supported_carriers():
    """Ritorna la lista dei corrieri supportati"""
    return ['UPS', 'DHL', 'BRT', 'GLS', 'TNT', 'FEDEX', 'POSTE', 'SDA']
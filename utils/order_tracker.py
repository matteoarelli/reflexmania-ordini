#!/usr/bin/env python3
"""
Tracker ordini processati usando file JSON locale
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)

TRACKER_FILE = "/tmp/ordini_processati.json"


class OrderTracker:
    """Traccia ordini già processati per evitare duplicati"""
    
    def __init__(self):
        self.data = self._load_data()
        logger.info("✅ OrderTracker inizializzato")
    
    def _load_data(self) -> Dict[str, Dict]:
        """Carica dati da file JSON"""
        if not os.path.exists(TRACKER_FILE):
            return {}
        
        try:
            with open(TRACKER_FILE, 'r') as f:
                data = json.load(f)
            
            # Pulisci ordini vecchi (più di 7 giorni)
            self._cleanup_old_orders(data)
            
            logger.info(f"📂 Caricati {self._count_orders(data)} ordini dal tracker")
            return data
        except Exception as e:
            logger.error(f"❌ Errore caricamento tracker: {e}")
            return {}
    
    def _save_data(self):
        """Salva dati su file JSON"""
        try:
            with open(TRACKER_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
            logger.debug(f"💾 Tracker salvato ({self._count_orders(self.data)} ordini)")
        except Exception as e:
            logger.error(f"❌ Errore salvataggio tracker: {e}")
    
    def _count_orders(self, data: Dict) -> int:
        """Conta totale ordini nel tracker"""
        count = 0
        for marketplace in data.values():
            count += len(marketplace)
        return count
    
    def _cleanup_old_orders(self, data: Dict):
        """Rimuove ordini più vecchi di 7 giorni"""
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        
        for marketplace in list(data.keys()):
            for order_id in list(data[marketplace].keys()):
                processed_at = data[marketplace][order_id].get('processed_at', '')
                if processed_at < cutoff:
                    del data[marketplace][order_id]
            
            # Rimuovi marketplace vuoti
            if not data[marketplace]:
                del data[marketplace]
    
    def is_processed(self, marketplace: str, order_id: str) -> bool:
        """
        Verifica se ordine è già stato processato
        
        Args:
            marketplace: 'backmarket', 'refurbed', 'magento'
            order_id: ID ordine
            
        Returns:
            True se già processato
        """
        if marketplace not in self.data:
            return False
        
        is_processed = order_id in self.data[marketplace]
        
        if is_processed:
            logger.info(f"⏭️ Ordine {marketplace} {order_id} già processato, skip")
        
        return is_processed
    
    def mark_processed(self, marketplace: str, order_id: str, ddt_id: str = None):
        """
        Segna ordine come processato
        
        Args:
            marketplace: 'backmarket', 'refurbed', 'magento'
            order_id: ID ordine
            ddt_id: ID DDT creato (opzionale)
        """
        if marketplace not in self.data:
            self.data[marketplace] = {}
        
        self.data[marketplace][order_id] = {
            'processed_at': datetime.now().isoformat(),
            'ddt_id': ddt_id
        }
        
        self._save_data()
        logger.info(f"✅ Ordine {marketplace} {order_id} segnato come processato (DDT: {ddt_id})")
    
    def get_stats(self) -> Dict:
        """Ritorna statistiche tracker"""
        stats = {}
        for marketplace, orders in self.data.items():
            stats[marketplace] = len(orders)
        return stats
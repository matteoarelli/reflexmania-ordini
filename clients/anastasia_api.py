#!/usr/bin/env python3
"""
Client per interrogare il database Anastasia (MySQL A2Hosting)
Sistema di ticketing valutazioni materiale fotografico
"""

import mysql.connector
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class AnastasiaClient:
    """Client per connessione database Anastasia"""
    
    def __init__(self, config: Dict):
        """
        Inizializza client Anastasia
        
        Args:
            config: Dict con host, port, database, user, password
        """
        self.config = config
        self._test_connection()
    
    def _test_connection(self):
        """Testa la connessione al database"""
        try:
            conn = self._get_connection()
            conn.close()
            logger.info("✅ Connessione Anastasia database OK")
        except Exception as e:
            logger.error(f"❌ Errore connessione Anastasia: {e}")
            raise
    
    def _get_connection(self):
        """Crea nuova connessione MySQL"""
        return mysql.connector.connect(**self.config)
    
    def get_ticket_stats(self) -> Dict:
        """
        Recupera statistiche globali ticket
        
        Returns:
            Dict con: total, open, closed, today_closed
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 0 
                        AND (
                            (last_update >= UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 6 MONTH)))
                            OR 
                            (last_update >= UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 6 MONTH)) AND last_update REGEXP '^[0-9]+
            
            cursor.execute(query)
            stats = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return {
                'total': stats['total'] or 0,
                'open': stats['open'] or 0,
                'closed': stats['closed'] or 0,
                'today_closed': stats['today_closed'] or 0
            }
            
        except Exception as e:
            logger.error(f"Errore get_ticket_stats: {e}")
            return {'total': 0, 'open': 0, 'closed': 0, 'today_closed': 0}
    
    def get_open_tickets(self, limit: int = 10) -> List[Dict]:
        """
        Recupera ultimi ticket aperti
        
        Args:
            limit: Numero massimo ticket da recuperare
            
        Returns:
            Lista di dict con info ticket
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    t.id,
                    t.email,
                    t.title,
                    t.creation_date,
                    t.last_update,
                    t.status,
                    t.blue_tick,
                    c.nome,
                    c.cognome,
                    c.phone
                FROM ticket t
                LEFT JOIN customer c ON t.user_id_id = c.id
                WHERE t.status = 0 
                  AND (t.is_auto = 0 OR t.is_auto IS NULL)
                  AND (
                    (t.last_update >= UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 6 MONTH)))
                    OR 
                    (t.last_update >= UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 6 MONTH)) AND t.last_update REGEXP '^[0-9]+
            
            cursor.execute(query, (limit,))
            tickets = cursor.fetchall()
            
            # Formatta i risultati
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'id': ticket['id'],
                    'email': ticket['email'],
                    'title': ticket['title'] or 'Senza titolo',
                    'customer_name': f"{ticket['nome'] or ''} {ticket['cognome'] or ''}".strip() or 'N/A',
                    'phone': ticket['phone'],
                    'creation_date': self._format_timestamp(ticket['creation_date']),
                    'last_update': self._format_timestamp(ticket['last_update']),
                    'last_update_raw': ticket['last_update'],
                    'blue_tick': ticket['blue_tick'] or 0
                })
            
            cursor.close()
            conn.close()
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Errore get_open_tickets: {e}")
            return []
    
    def get_recent_closed_tickets(self, limit: int = 5) -> List[Dict]:
        """
        Recupera ultimi ticket chiusi oggi
        
        Args:
            limit: Numero massimo ticket da recuperare
            
        Returns:
            Lista di dict con info ticket chiusi
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    t.id,
                    t.email,
                    t.title,
                    t.last_update,
                    c.nome,
                    c.cognome
                FROM ticket t
                LEFT JOIN customer c ON t.user_id_id = c.id
                WHERE t.status = 1
                  AND (t.is_auto = 0 OR t.is_auto IS NULL)
                  AND DATE(FROM_UNIXTIME(t.last_update)) = CURDATE()
                ORDER BY t.last_update DESC
                LIMIT %s
            """
            
            cursor.execute(query, (limit,))
            tickets = cursor.fetchall()
            
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'id': ticket['id'],
                    'email': ticket['email'],
                    'title': ticket['title'] or 'Senza titolo',
                    'customer_name': f"{ticket['nome'] or ''} {ticket['cognome'] or ''}".strip() or 'N/A',
                    'last_update': self._format_timestamp(ticket['last_update'])
                })
            
            cursor.close()
            conn.close()
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Errore get_recent_closed_tickets: {e}")
            return []
    
    def _format_timestamp(self, timestamp) -> str:
        """
        Converte timestamp (Unix o stringa MySQL) in stringa leggibile
        
        Args:
            timestamp: Timestamp Unix (int/str) o stringa MySQL datetime
            
        Returns:
            Stringa formattata (es: "2 ore fa", "15/10/2025 14:30")
        """
        if not timestamp:
            return 'N/A'
        
        try:
            # Se è un intero, è un timestamp Unix
            if isinstance(timestamp, int):
                dt = datetime.fromtimestamp(timestamp)
            # Se è stringa, prova diversi formati
            elif isinstance(timestamp, str):
                # Prova prima a convertirlo in int (timestamp Unix come stringa)
                try:
                    unix_timestamp = int(timestamp)
                    dt = datetime.fromtimestamp(unix_timestamp)
                except ValueError:
                    # Non è un numero, prova formati MySQL datetime
                    if ' ' in timestamp:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    else:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d")
            else:
                return 'N/A'
            
            now = datetime.now()
            diff = now - dt
            
            # Meno di 1 ora
            if diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes} min fa" if minutes > 0 else "Ora"
            
            # Meno di 24 ore
            elif diff.total_seconds() < 86400:
                hours = int(diff.total_seconds() / 3600)
                return f"{hours}h fa"
            
            # Meno di 7 giorni
            elif diff.days < 7:
                return f"{diff.days}g fa"
            
            # Formato data completa
            else:
                return dt.strftime("%d/%m/%Y %H:%M")
                
        except Exception as e:
            logger.error(f"Errore format timestamp: {e}")
            # Mostra il valore raw per debug
            return str(timestamp)[:10] if timestamp else 'N/A'
    
    def health_check(self) -> bool:
        """
        Verifica salute connessione database
        
        Returns:
            True se connessione OK, False altrimenti
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False)
                  )
                ORDER BY t.last_update DESC
                LIMIT %s
            """
            
            cursor.execute(query, (limit,))
            tickets = cursor.fetchall()
            
            # Formatta i risultati
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'id': ticket['id'],
                    'email': ticket['email'],
                    'title': ticket['title'] or 'Senza titolo',
                    'customer_name': f"{ticket['nome'] or ''} {ticket['cognome'] or ''}".strip() or 'N/A',
                    'phone': ticket['phone'],
                    'creation_date': self._format_timestamp(ticket['creation_date']),
                    'last_update': self._format_timestamp(ticket['last_update']),
                    'last_update_raw': ticket['last_update'],
                    'blue_tick': ticket['blue_tick'] or 0
                })
            
            cursor.close()
            conn.close()
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Errore get_open_tickets: {e}")
            return []
    
    def get_recent_closed_tickets(self, limit: int = 5) -> List[Dict]:
        """
        Recupera ultimi ticket chiusi oggi
        
        Args:
            limit: Numero massimo ticket da recuperare
            
        Returns:
            Lista di dict con info ticket chiusi
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    t.id,
                    t.email,
                    t.title,
                    t.last_update,
                    c.nome,
                    c.cognome
                FROM ticket t
                LEFT JOIN customer c ON t.user_id_id = c.id
                WHERE t.status = 1
                  AND (t.is_auto = 0 OR t.is_auto IS NULL)
                  AND DATE(FROM_UNIXTIME(t.last_update)) = CURDATE()
                ORDER BY t.last_update DESC
                LIMIT %s
            """
            
            cursor.execute(query, (limit,))
            tickets = cursor.fetchall()
            
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'id': ticket['id'],
                    'email': ticket['email'],
                    'title': ticket['title'] or 'Senza titolo',
                    'customer_name': f"{ticket['nome'] or ''} {ticket['cognome'] or ''}".strip() or 'N/A',
                    'last_update': self._format_timestamp(ticket['last_update'])
                })
            
            cursor.close()
            conn.close()
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Errore get_recent_closed_tickets: {e}")
            return []
    
    def _format_timestamp(self, timestamp) -> str:
        """
        Converte timestamp (Unix o stringa MySQL) in stringa leggibile
        
        Args:
            timestamp: Timestamp Unix (int/str) o stringa MySQL datetime
            
        Returns:
            Stringa formattata (es: "2 ore fa", "15/10/2025 14:30")
        """
        if not timestamp:
            return 'N/A'
        
        try:
            # Se è un intero, è un timestamp Unix
            if isinstance(timestamp, int):
                dt = datetime.fromtimestamp(timestamp)
            # Se è stringa, prova diversi formati
            elif isinstance(timestamp, str):
                # Prova prima a convertirlo in int (timestamp Unix come stringa)
                try:
                    unix_timestamp = int(timestamp)
                    dt = datetime.fromtimestamp(unix_timestamp)
                except ValueError:
                    # Non è un numero, prova formati MySQL datetime
                    if ' ' in timestamp:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    else:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d")
            else:
                return 'N/A'
            
            now = datetime.now()
            diff = now - dt
            
            # Meno di 1 ora
            if diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes} min fa" if minutes > 0 else "Ora"
            
            # Meno di 24 ore
            elif diff.total_seconds() < 86400:
                hours = int(diff.total_seconds() / 3600)
                return f"{hours}h fa"
            
            # Meno di 7 giorni
            elif diff.days < 7:
                return f"{diff.days}g fa"
            
            # Formato data completa
            else:
                return dt.strftime("%d/%m/%Y %H:%M")
                
        except Exception as e:
            logger.error(f"Errore format timestamp: {e}")
            # Mostra il valore raw per debug
            return str(timestamp)[:10] if timestamp else 'N/A'
    
    def health_check(self) -> bool:
        """
        Verifica salute connessione database
        
        Returns:
            True se connessione OK, False altrimenti
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False)
                        )
                        THEN 1 ELSE 0 END) as open,
                    SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as closed,
                    SUM(CASE 
                        WHEN status = 1 
                        AND DATE(FROM_UNIXTIME(CAST(last_update AS UNSIGNED))) = CURDATE() 
                        THEN 1 ELSE 0 
                    END) as today_closed
                FROM ticket
                WHERE (is_auto = 0 OR is_auto IS NULL)
            """
            
            cursor.execute(query)
            stats = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return {
                'total': stats['total'] or 0,
                'open': stats['open'] or 0,
                'closed': stats['closed'] or 0,
                'today_closed': stats['today_closed'] or 0
            }
            
        except Exception as e:
            logger.error(f"Errore get_ticket_stats: {e}")
            return {'total': 0, 'open': 0, 'closed': 0, 'today_closed': 0}
    
    def get_open_tickets(self, limit: int = 10) -> List[Dict]:
        """
        Recupera ultimi ticket aperti
        
        Args:
            limit: Numero massimo ticket da recuperare
            
        Returns:
            Lista di dict con info ticket
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    t.id,
                    t.email,
                    t.title,
                    t.creation_date,
                    t.last_update,
                    t.status,
                    t.blue_tick,
                    c.nome,
                    c.cognome,
                    c.phone
                FROM ticket t
                LEFT JOIN customer c ON t.user_id_id = c.id
                WHERE t.status = 0 
                  AND (t.is_auto = 0 OR t.is_auto IS NULL)
                  AND (
                    (t.last_update >= UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 6 MONTH)))
                    OR 
                    (t.last_update >= UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 6 MONTH)) AND t.last_update REGEXP '^[0-9]+
            
            cursor.execute(query, (limit,))
            tickets = cursor.fetchall()
            
            # Formatta i risultati
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'id': ticket['id'],
                    'email': ticket['email'],
                    'title': ticket['title'] or 'Senza titolo',
                    'customer_name': f"{ticket['nome'] or ''} {ticket['cognome'] or ''}".strip() or 'N/A',
                    'phone': ticket['phone'],
                    'creation_date': self._format_timestamp(ticket['creation_date']),
                    'last_update': self._format_timestamp(ticket['last_update']),
                    'last_update_raw': ticket['last_update'],
                    'blue_tick': ticket['blue_tick'] or 0
                })
            
            cursor.close()
            conn.close()
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Errore get_open_tickets: {e}")
            return []
    
    def get_recent_closed_tickets(self, limit: int = 5) -> List[Dict]:
        """
        Recupera ultimi ticket chiusi oggi
        
        Args:
            limit: Numero massimo ticket da recuperare
            
        Returns:
            Lista di dict con info ticket chiusi
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    t.id,
                    t.email,
                    t.title,
                    t.last_update,
                    c.nome,
                    c.cognome
                FROM ticket t
                LEFT JOIN customer c ON t.user_id_id = c.id
                WHERE t.status = 1
                  AND (t.is_auto = 0 OR t.is_auto IS NULL)
                  AND DATE(FROM_UNIXTIME(t.last_update)) = CURDATE()
                ORDER BY t.last_update DESC
                LIMIT %s
            """
            
            cursor.execute(query, (limit,))
            tickets = cursor.fetchall()
            
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'id': ticket['id'],
                    'email': ticket['email'],
                    'title': ticket['title'] or 'Senza titolo',
                    'customer_name': f"{ticket['nome'] or ''} {ticket['cognome'] or ''}".strip() or 'N/A',
                    'last_update': self._format_timestamp(ticket['last_update'])
                })
            
            cursor.close()
            conn.close()
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Errore get_recent_closed_tickets: {e}")
            return []
    
    def _format_timestamp(self, timestamp) -> str:
        """
        Converte timestamp (Unix o stringa MySQL) in stringa leggibile
        
        Args:
            timestamp: Timestamp Unix (int/str) o stringa MySQL datetime
            
        Returns:
            Stringa formattata (es: "2 ore fa", "15/10/2025 14:30")
        """
        if not timestamp:
            return 'N/A'
        
        try:
            # Se è un intero, è un timestamp Unix
            if isinstance(timestamp, int):
                dt = datetime.fromtimestamp(timestamp)
            # Se è stringa, prova diversi formati
            elif isinstance(timestamp, str):
                # Prova prima a convertirlo in int (timestamp Unix come stringa)
                try:
                    unix_timestamp = int(timestamp)
                    dt = datetime.fromtimestamp(unix_timestamp)
                except ValueError:
                    # Non è un numero, prova formati MySQL datetime
                    if ' ' in timestamp:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    else:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d")
            else:
                return 'N/A'
            
            now = datetime.now()
            diff = now - dt
            
            # Meno di 1 ora
            if diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes} min fa" if minutes > 0 else "Ora"
            
            # Meno di 24 ore
            elif diff.total_seconds() < 86400:
                hours = int(diff.total_seconds() / 3600)
                return f"{hours}h fa"
            
            # Meno di 7 giorni
            elif diff.days < 7:
                return f"{diff.days}g fa"
            
            # Formato data completa
            else:
                return dt.strftime("%d/%m/%Y %H:%M")
                
        except Exception as e:
            logger.error(f"Errore format timestamp: {e}")
            # Mostra il valore raw per debug
            return str(timestamp)[:10] if timestamp else 'N/A'
    
    def health_check(self) -> bool:
        """
        Verifica salute connessione database
        
        Returns:
            True se connessione OK, False altrimenti
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False)
                  )
                ORDER BY t.last_update DESC
                LIMIT %s
            """
            
            cursor.execute(query, (limit,))
            tickets = cursor.fetchall()
            
            # Formatta i risultati
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'id': ticket['id'],
                    'email': ticket['email'],
                    'title': ticket['title'] or 'Senza titolo',
                    'customer_name': f"{ticket['nome'] or ''} {ticket['cognome'] or ''}".strip() or 'N/A',
                    'phone': ticket['phone'],
                    'creation_date': self._format_timestamp(ticket['creation_date']),
                    'last_update': self._format_timestamp(ticket['last_update']),
                    'last_update_raw': ticket['last_update'],
                    'blue_tick': ticket['blue_tick'] or 0
                })
            
            cursor.close()
            conn.close()
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Errore get_open_tickets: {e}")
            return []
    
    def get_recent_closed_tickets(self, limit: int = 5) -> List[Dict]:
        """
        Recupera ultimi ticket chiusi oggi
        
        Args:
            limit: Numero massimo ticket da recuperare
            
        Returns:
            Lista di dict con info ticket chiusi
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    t.id,
                    t.email,
                    t.title,
                    t.last_update,
                    c.nome,
                    c.cognome
                FROM ticket t
                LEFT JOIN customer c ON t.user_id_id = c.id
                WHERE t.status = 1
                  AND (t.is_auto = 0 OR t.is_auto IS NULL)
                  AND DATE(FROM_UNIXTIME(t.last_update)) = CURDATE()
                ORDER BY t.last_update DESC
                LIMIT %s
            """
            
            cursor.execute(query, (limit,))
            tickets = cursor.fetchall()
            
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'id': ticket['id'],
                    'email': ticket['email'],
                    'title': ticket['title'] or 'Senza titolo',
                    'customer_name': f"{ticket['nome'] or ''} {ticket['cognome'] or ''}".strip() or 'N/A',
                    'last_update': self._format_timestamp(ticket['last_update'])
                })
            
            cursor.close()
            conn.close()
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Errore get_recent_closed_tickets: {e}")
            return []
    
    def _format_timestamp(self, timestamp) -> str:
        """
        Converte timestamp (Unix o stringa MySQL) in stringa leggibile
        
        Args:
            timestamp: Timestamp Unix (int/str) o stringa MySQL datetime
            
        Returns:
            Stringa formattata (es: "2 ore fa", "15/10/2025 14:30")
        """
        if not timestamp:
            return 'N/A'
        
        try:
            # Se è un intero, è un timestamp Unix
            if isinstance(timestamp, int):
                dt = datetime.fromtimestamp(timestamp)
            # Se è stringa, prova diversi formati
            elif isinstance(timestamp, str):
                # Prova prima a convertirlo in int (timestamp Unix come stringa)
                try:
                    unix_timestamp = int(timestamp)
                    dt = datetime.fromtimestamp(unix_timestamp)
                except ValueError:
                    # Non è un numero, prova formati MySQL datetime
                    if ' ' in timestamp:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    else:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d")
            else:
                return 'N/A'
            
            now = datetime.now()
            diff = now - dt
            
            # Meno di 1 ora
            if diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes} min fa" if minutes > 0 else "Ora"
            
            # Meno di 24 ore
            elif diff.total_seconds() < 86400:
                hours = int(diff.total_seconds() / 3600)
                return f"{hours}h fa"
            
            # Meno di 7 giorni
            elif diff.days < 7:
                return f"{diff.days}g fa"
            
            # Formato data completa
            else:
                return dt.strftime("%d/%m/%Y %H:%M")
                
        except Exception as e:
            logger.error(f"Errore format timestamp: {e}")
            # Mostra il valore raw per debug
            return str(timestamp)[:10] if timestamp else 'N/A'
    
    def health_check(self) -> bool:
        """
        Verifica salute connessione database
        
        Returns:
            True se connessione OK, False altrimenti
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
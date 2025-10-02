#!/usr/bin/env python3
"""
Servizio per gestione DDT e clienti InvoiceX
"""
import mysql.connector
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def get_or_create_cliente(order: Dict, db_config: Dict) -> int:
    """Cerca o crea un cliente nel database InvoiceX e ritorna l'ID"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        name_parts = order['customer_name'].split(maxsplit=1)
        nome = name_parts[0] if name_parts else 'Cliente'
        cognome = name_parts[1] if len(name_parts) > 1 else 'Marketplace'
        
        # Cerca prima per email (più affidabile)
        if order['customer_email']:
            cursor.execute(
                "SELECT id FROM clie_forn WHERE email = %s LIMIT 1",
                (order['customer_email'],)
            )
            result = cursor.fetchone()
            if result:
                cliente_id = result[0]
                logger.info(f"Cliente trovato per email: ID {cliente_id}")
                cursor.close()
                conn.close()
                return cliente_id
        
        # Cerca per nome completo
        cursor.execute(
            "SELECT id FROM clie_forn WHERE ragione_sociale = %s LIMIT 1",
            (order['customer_name'],)
        )
        result = cursor.fetchone()
        
        if result:
            cliente_id = result[0]
            logger.info(f"Cliente trovato per nome: ID {cliente_id}")
        else:
            # Crea nuovo cliente
            insert_query = """
            INSERT INTO clie_forn 
            (ragione_sociale, nome, cognome, indirizzo, cap, localita, 
             provincia, paese, telefono, cellulare, email, tipo_clifor)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            provincia = ''
            paese = order['country'][:2].upper() if order['country'] else 'IT'
            
            values = (
                order['customer_name'],
                nome,
                cognome,
                order['address'][:50] if order['address'] else '',
                order['postal_code'][:10] if order['postal_code'] else '',
                order['city'][:30] if order['city'] else '',
                provincia,
                paese,
                order['customer_phone'][:20] if order['customer_phone'] else '',
                order['customer_phone'][:20] if order['customer_phone'] else '',
                order['customer_email'][:100] if order['customer_email'] else '',
                'C'
            )
            
            cursor.execute(insert_query, values)
            conn.commit()
            cliente_id = cursor.lastrowid
            logger.info(f"Nuovo cliente creato: ID {cliente_id} - {order['customer_name']}")
        
        cursor.close()
        conn.close()
        return cliente_id
        
    except mysql.connector.Error as e:
        logger.error(f"Errore MySQL get_or_create_cliente: {e}")
        return 1
    except Exception as e:
        logger.error(f"Errore generico get_or_create_cliente: {e}")
        return 1


def create_ddt_invoicex(order: Dict, db_config: Dict) -> Optional[str]:
    """Crea DDT su InvoiceX e ritorna il numero DDT"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Recupera il prossimo numero DDT progressivo per l'anno corrente
        query_num = """
        SELECT MAX(numero) as max_num 
        FROM test_ddt 
        WHERE anno = YEAR(CURDATE())
        """
        cursor.execute(query_num)
        result = cursor.fetchone()
        max_num = result[0] if result[0] else 0
        ddt_number = max_num + 1
        
        # Cerca o crea cliente
        cliente_id = get_or_create_cliente(order, db_config)
        
        # Inserisci testata DDT
        query_header = """
        INSERT INTO test_ddt 
        (serie, numero, anno, cliente, data, pagamento, note, 
         totale_imponibile, totale_iva, totale, 
         sconto1, sconto2, sconto3, stato, codice_listino, stampato,
         prezzi_ivati, sconto, totale_imponibile_pre_sconto, totale_ivato_pre_sconto,
         deposito, mail_inviata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        values_header = (
            '',
            ddt_number,
            datetime.now().year,
            cliente_id,
            datetime.now().date(),
            'MARKETPLACE',
            f"Ordine {order['source']} #{order['order_id']}\n\nOperazione soggetta al regime speciale\nex art. 36 e successivi ( art. 38 D.L. 41/1995)\n",
            float(order['total']),
            0.00,
            float(order['total']),
            0.00,
            0.00,
            0.00,
            'P',
            1,
            datetime(1, 1, 1, 0, 0),
            'N',
            0.00,
            float(order['total']),
            float(order['total']),
            0,
            0
        )
        
        cursor.execute(query_header, values_header)
        ddt_id = cursor.lastrowid
        
        # Inserisci righe DDT
        query_lines = """
        INSERT INTO righ_ddt
        (id_padre, serie, numero, anno, riga, data, codice_articolo, descrizione,
         um, quantita, prezzo, iva, sconto1, sconto2, stato, is_descrizione,
         prezzo_ivato, totale_ivato, totale_imponibile, prezzo_netto_unitario, 
         prezzo_ivato_netto_unitario, prezzo_netto_totale, prezzo_ivato_netto_totale)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        for idx, item in enumerate(order['items'], start=1):
            prezzo_unitario = float(order['total']) / len(order['items'])
            qta = float(item['quantity'])
            
            # Cerca se il prodotto esiste in magazzino usando lo SKU
            sku_to_search = item['sku']
            cursor.execute("SELECT codice FROM articoli WHERE codice = %s LIMIT 1", (sku_to_search,))
            product_result = cursor.fetchone()
            
            # Se prodotto trovato usa il codice, altrimenti usa SKU troncato
            codice_articolo = product_result[0] if product_result else sku_to_search[:20]
            
            values_line = (
                ddt_id,
                '',
                ddt_number,
                datetime.now().year,
                idx,
                datetime.now().date(),
                codice_articolo,
                item['name'],
                '',
                qta,
                prezzo_unitario,
                '36',
                0.00,
                0.00,
                'P',
                'N',
                prezzo_unitario,
                prezzo_unitario * qta,
                prezzo_unitario * qta,
                prezzo_unitario,
                prezzo_unitario,
                prezzo_unitario * qta,
                prezzo_unitario * qta
            )
            cursor.execute(query_lines, values_line)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        ddt_number_formatted = str(ddt_number).zfill(4)
        logger.info(f"DDT {ddt_number_formatted}/{datetime.now().year} creato (ID: {ddt_id}, Cliente: {cliente_id})")
        return ddt_number_formatted
        
    except mysql.connector.Error as e:
        logger.error(f"Errore MySQL creazione DDT: {e}")
        return None
    except Exception as e:
        logger.error(f"Errore generico creazione DDT: {e}")
        return None

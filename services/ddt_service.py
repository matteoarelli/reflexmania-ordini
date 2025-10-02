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
        
        # LOG DEBUG
        logger.info(f"🔍 Ricerca cliente: nome='{order['customer_name']}', email='{order['customer_email']}'")
        
        name_parts = order['customer_name'].split(maxsplit=1)
        nome = name_parts[0] if name_parts else 'Cliente'
        cognome = name_parts[1] if len(name_parts) > 1 else 'Marketplace'
        
        # La prima colonna è l'ID (posizione 0)
        # Cerca prima per email (più affidabile)
        if order['customer_email']:
            query = "SELECT * FROM clie_forn WHERE email = %s LIMIT 1"
            logger.info(f"📧 Query ricerca per email: {query} | email={order['customer_email']}")
            cursor.execute(query, (order['customer_email'],))
            result = cursor.fetchone()
            if result:
                cliente_id = result[0]  # Prima colonna = ID
                logger.info(f"✓ Cliente trovato per email: ID {cliente_id}")
                cursor.close()
                conn.close()
                return cliente_id
            else:
                logger.info(f"✗ Nessun cliente trovato per email {order['customer_email']}")
        
        # Cerca per ragione_sociale
        query = "SELECT * FROM clie_forn WHERE ragione_sociale = %s LIMIT 1"
        logger.info(f"👤 Query ricerca per nome: {query} | nome={order['customer_name']}")
        cursor.execute(query, (order['customer_name'],))
        result = cursor.fetchone()
        
        if result:
            cliente_id = result[0]
            logger.info(f"✓ Cliente trovato per nome: ID {cliente_id}")
        else:
            logger.info(f"✗ Nessun cliente trovato, procedo con creazione nuovo cliente")
            
            # Crea nuovo cliente - SOLO CAMPI ESISTENTI
            insert_query = """
            INSERT INTO clie_forn 
            (ragione_sociale, nome, cognome, indirizzo, cap, localita, 
             telefono, cellulare, email, paese)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            paese = order['country'][:2].upper() if order['country'] else 'IT'
            
            # LOG DEBUG valori da inserire
            logger.info(f"📝 Preparazione INSERT nuovo cliente:")
            logger.info(f"   - ragione_sociale: {order['customer_name'][:100]}")
            logger.info(f"   - nome: {nome[:50]}")
            logger.info(f"   - cognome: {cognome[:50]}")
            logger.info(f"   - email: {order['customer_email'][:100] if order['customer_email'] else 'N/A'}")
            logger.info(f"   - indirizzo: {order['address'][:100] if order['address'] else 'N/A'}")
            logger.info(f"   - cap: {order['postal_code'][:10] if order['postal_code'] else 'N/A'}")
            logger.info(f"   - localita: {order['city'][:50] if order['city'] else 'N/A'}")
            logger.info(f"   - paese: {paese}")
            
            values = (
                order['customer_name'][:100],  # ragione_sociale
                nome[:50],  # nome
                cognome[:50],  # cognome
                order['address'][:100] if order['address'] else '',  # indirizzo
                order['postal_code'][:10] if order['postal_code'] else '',  # cap
                order['city'][:50] if order['city'] else '',  # localita
                order['customer_phone'][:20] if order['customer_phone'] else '',  # telefono
                order['customer_phone'][:20] if order['customer_phone'] else '',  # cellulare
                order['customer_email'][:100] if order['customer_email'] else '',  # email
                paese  # paese
            )
            
            cursor.execute(insert_query, values)
            conn.commit()
            cliente_id = cursor.lastrowid
            logger.info(f"✓ Nuovo cliente creato con successo: ID {cliente_id} - {order['customer_name']}")
        
        cursor.close()
        conn.close()
        return cliente_id
        
    except mysql.connector.Error as e:
        logger.error(f"❌ Errore MySQL get_or_create_cliente: {e}")
        logger.error(f"   Query fallita, ritorno cliente ID=1 di default")
        return 1
    except Exception as e:
        logger.error(f"❌ Errore generico get_or_create_cliente: {e}")
        logger.error(f"   Ritorno cliente ID=1 di default")
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
        
        # Note SOLO con regime speciale
        note_regime = "Operazione soggetta al regime speciale\nex art. 36 e successivi ( art. 38 D.L. 41/1995)"
        
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
            note_regime,
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
            
            # Cerca prodotto con SKU esatto
            sku_to_search = str(item['sku']).strip()
            
            # LOG DEBUG
            logger.info(f"🔍 Ricerca prodotto magazzino: SKU={sku_to_search}")
            
            cursor.execute("SELECT codice FROM articoli WHERE codice = %s LIMIT 1", (sku_to_search,))
            product_result = cursor.fetchone()
            
            codice_articolo = product_result[0] if product_result else sku_to_search
            descrizione_pulita = item['name'][:200]
            
            # LOG DEBUG
            if product_result:
                logger.info(f"✓ Prodotto {sku_to_search} TROVATO in magazzino - scarico automatico attivo")
            else:
                logger.warning(f"✗ Prodotto {sku_to_search} NON TROVATO in magazzino - codice_articolo={codice_articolo}")
                logger.warning(f"   Per collegarlo al magazzino, aggiungi prodotto in tabella 'articoli' con codice='{sku_to_search}'")
            
            values_line = (
                ddt_id,
                '',
                ddt_number,
                datetime.now().year,
                idx,
                datetime.now().date(),
                codice_articolo,
                descrizione_pulita,
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
        logger.info(f"✅ DDT {ddt_number_formatted}/{datetime.now().year} creato con successo")
        logger.info(f"   - ID DDT: {ddt_id}")
        logger.info(f"   - Cliente ID: {cliente_id}")
        logger.info(f"   - Righe prodotto: {len(order['items'])}")
        return ddt_number_formatted
        
    except mysql.connector.Error as e:
        logger.error(f"Errore MySQL creazione DDT: {e}")
        return None
    except Exception as e:
        logger.error(f"Errore generico creazione DDT: {e}")
        return None
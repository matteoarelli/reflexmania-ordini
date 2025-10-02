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
        
        # La prima colonna è l'ID (posizione 0)
        # Cerca prima per email (più affidabile)
        if order['customer_email']:
            cursor.execute(
                "SELECT * FROM clie_forn WHERE email = %s LIMIT 1",
                (order['customer_email'],)
            )
            result = cursor.fetchone()
            if result:
                cliente_id = result[0]  # Prima colonna = ID
                logger.info(f"Cliente trovato per email: ID {cliente_id}")
                cursor.close()
                conn.close()
                return cliente_id
        
        # Cerca per ragione_sociale (colonna 4 nell'esempio)
        cursor.execute(
            "SELECT * FROM clie_forn WHERE ragione_sociale = %s LIMIT 1",
            (order['customer_name'],)
        )
        result = cursor.fetchone()
        
        if result:
            cliente_id = result[0]
            logger.info(f"Cliente trovato per nome: ID {cliente_id}")
        else:
            # Crea nuovo cliente - USA TUTTI I CAMPI RICHIESTI
            # Basato sull'esempio: 109 colonne totali
            insert_query = """
            INSERT INTO clie_forn 
            (piva, cod_fiscale, rea, ragione_sociale, pfis, nome, cognome, 
             indirizzo, cap, localita, provincia, telefono, cellulare, email, 
             codice_sdi, pec, paese, tipo_clifor, 
             sconto, sconto2, iban, banca, 
             cod_pagamento, gg_scadenza, note, fido, iva_inclusa, 
             split_payment, cod_esenzione, listino, codice_agente, 
             sito_web, escludi_magg, escludi_liq_iva, id_banca_appoggio,
             is_trasportatore, nascondi_scadenze, sconto3, esenzione_ritenuta,
             id_ritenuta, percentuale_ritenuta, categorie, data_nascita,
             luogo_nascita, sesso, acconto, attivo, bollo, ragsoc_agente,
             contributo_cassa, perc_contributo_cassa, imponibile_ritenuta,
             natura_iva, id_causale_ritenuta, tipo_cassa, giorni_fissi_pagamento,
             split_payment_detraibile, giorni_fine_mese, prezzo_trasporto,
             listino2, listino3, listino_tipo, enasarco, priorita, data_ultimo_doc,
             castelletto, sconto4, comune_nascita, nazione_nascita, cod_ateco,
             aliquota_inps, num_iscrizione_inps, sede_inps, matricola_inps,
             codice_posizione_inail, num_pat_inail, numero_iscrizione_albo)
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            """
            
            paese = order['country'][:2].upper() if order['country'] else 'IT'
            
            values = (
                '',  # piva
                '',  # cod_fiscale
                '',  # rea
                order['customer_name'][:100],  # ragione_sociale
                'N',  # pfis
                nome[:50],  # nome
                cognome[:50],  # cognome
                order['address'][:100] if order['address'] else '',  # indirizzo
                order['postal_code'][:10] if order['postal_code'] else '',  # cap
                order['city'][:50] if order['city'] else '',  # localita
                '',  # provincia
                order['customer_phone'][:20] if order['customer_phone'] else '',  # telefono
                order['customer_phone'][:20] if order['customer_phone'] else '',  # cellulare
                order['customer_email'][:100] if order['customer_email'] else '',  # email
                '',  # codice_sdi
                '',  # pec
                paese,  # paese
                'C',  # tipo_clifor (C=Cliente)
                0.0,  # sconto
                0.0,  # sconto2
                '',  # iban
                '',  # banca
                '',  # cod_pagamento
                0,  # gg_scadenza
                '',  # note
                0.0,  # fido
                'N',  # iva_inclusa
                'N',  # split_payment
                '',  # cod_esenzione
                1,  # listino
                0,  # codice_agente
                '',  # sito_web
                'N',  # escludi_magg
                'N',  # escludi_liq_iva
                0,  # id_banca_appoggio
                'N',  # is_trasportatore
                'N',  # nascondi_scadenze
                0.0,  # sconto3
                'N',  # esenzione_ritenuta
                None,  # id_ritenuta
                0.0,  # percentuale_ritenuta
                '',  # categorie
                None,  # data_nascita
                '',  # luogo_nascita
                '',  # sesso
                0.0,  # acconto
                'S',  # attivo
                'N',  # bollo
                '',  # ragsoc_agente
                'N',  # contributo_cassa
                0.0,  # perc_contributo_cassa
                'N',  # imponibile_ritenuta
                '',  # natura_iva
                None,  # id_causale_ritenuta
                '',  # tipo_cassa
                '',  # giorni_fissi_pagamento
                'N',  # split_payment_detraibile
                0,  # giorni_fine_mese
                0.0,  # prezzo_trasporto
                0,  # listino2
                0,  # listino3
                '',  # listino_tipo
                'N',  # enasarco
                0,  # priorita
                None,  # data_ultimo_doc
                'N',  # castelletto
                0.0,  # sconto4
                '',  # comune_nascita
                '',  # nazione_nascita
                '',  # cod_ateco
                0.0,  # aliquota_inps
                '',  # num_iscrizione_inps
                '',  # sede_inps
                '',  # matricola_inps
                '',  # codice_posizione_inail
                '',  # num_pat_inail
                ''   # numero_iscrizione_albo
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
            cursor.execute("SELECT codice FROM articoli WHERE codice = %s LIMIT 1", (sku_to_search,))
            product_result = cursor.fetchone()
            
            codice_articolo = product_result[0] if product_result else sku_to_search
            descrizione_pulita = item['name'][:200]
            
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
            
            if product_result:
                logger.info(f"Prodotto {sku_to_search} collegato a magazzino")
            else:
                logger.warning(f"Prodotto {sku_to_search} NON in magazzino - scarico manuale")
        
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
# ReflexMania - Sistema Gestione Ordini Marketplace

Sistema automatico per gestire ordini da BackMarket, Refurbed e CDiscount, con generazione CSV per Packlink Pro e creazione DDT su InvoiceX.

## 📋 Funzionalità

- ✅ Estrazione ordini da 3 marketplace (BackMarket, Refurbed, CDiscount/Octopia)
- ✅ Generazione CSV formato Packlink Pro per etichette spedizione
- ✅ Creazione automatica DDT su InvoiceX
- ✅ Dashboard web con pulsanti per operazioni manuali
- ✅ Deploy su Railway con IP statico

## 🚀 Deploy su Railway

### Step 1: Crea progetto su Railway

1. Vai su [railway.app](https://railway.app)
2. Clicca "New Project" → "Deploy from GitHub repo"
3. Collega il tuo repository GitHub con questi file

### Step 2: Configura IP Statico

**IMPORTANTE per InvoiceX**: Il database InvoiceX richiede IP whitelisting.

Su Railway:

1. Vai al tuo progetto
2. Clicca su "Settings" del servizio
3. Vai alla sezione "Networking"
4. Abilita **"TCP Proxy"** o **"Public Networking"**
5. Railway assegnerà un IP statico al deploy
6. **Copia l'IP statico** mostrato

### Step 3: Whitelist IP su InvoiceX

Contatta il supporto del tuo hosting (A2 Hosting) e richiedi:

```
Salve, vorrei aggiungere questo IP alla whitelist per accedere 
al database MySQL: [INSERISCI_IP_STATICO_RAILWAY]

Database: ilblogdi_invoicex2021
User: ilblogdi_inv2021
```

### Step 4: Configura Variabili d'Ambiente

Su Railway, vai su "Variables" e aggiungi:

```bash
# BackMarket
BACKMARKET_TOKEN=NDNjYzQzMDRmNGU2NTUzYzkzYjAwYjpCTVQtOTJhZjQ0MjU5YTlhMmYzMGRhMzA3YWJhZWMwZGI5YzUwMjAxMTdhYQ==

# Refurbed
REFURBED_TOKEN=277931ea-1ede-4a14-8aaa-41b2222d2aba

# CDiscount/Octopia
OCTOPIA_CLIENT_ID=reflexmania
OCTOPIA_CLIENT_SECRET=qTpoc2gd40Huhzi64FIKY6f9NoKac0C6
OCTOPIA_SELLER_ID=405765

# InvoiceX Database
INVOICEX_USER=ilblogdi_inv2021
INVOICEX_PASS=pWTrEKV}=fF-
INVOICEX_HOST=nl1-ts3.a2hosting.com
INVOICEX_DB=ilblogdi_invoicex2021

# Porta (Railway la imposta automaticamente)
PORT=5000
```

### Step 5: Deploy

Railway farà deploy automaticamente. Controlla i log per verificare:

```
✅ Autenticazione Octopia riuscita
✅ Server avviato su porta 5000
```

## 📱 Utilizzo

### Dashboard Web

Accedi all'URL del tuo deploy Railway (es: `https://your-app.railway.app`)

Vedrai una dashboard con 2 pulsanti:

#### 1️⃣ Scarica CSV Packlink

- Clicca il pulsante "Scarica CSV Packlink"
- Il sistema recupera ordini da tutti e 3 i marketplace
- Genera un CSV nel formato richiesto da Packlink Pro
- Il file viene scaricato automaticamente

**Formato CSV generato:**
```
Destinatario;Indirizzo;CAP;Città;Paese;Telefono;Email;Riferimento;Contenuto;Valore dichiarato;Peso (kg);Lunghezza (cm);Larghezza (cm);Altezza (cm)
```

#### 2️⃣ Genera DDT

- Clicca il pulsante "Genera DDT"
- Il sistema crea DDT su InvoiceX per tutti gli ordini
- Ricevi una risposta JSON con statistiche:
  ```json
  {
    "success": true,
    "total_orders": 25,
    "ddt_created": 25,
    "errors": 0
  }
  ```

### API Endpoints

Puoi anche chiamare le API direttamente:

**Genera CSV Packlink:**
```bash
curl https://your-app.railway.app/generate_packlink_csv > ordini.csv
```

**Genera DDT:**
```bash
curl -X POST https://your-app.railway.app/generate_ddt
```

**Health Check:**
```bash
curl https://your-app.railway.app/health
```

## 🗂️ Struttura File Progetto

```
reflexmania-ordini/
├── app.py                  # Applicazione principale
├── requirements.txt        # Dipendenze Python
├── railway.json           # Configurazione Railway
├── Procfile               # Comando di avvio
├── README.md              # Questa guida
└── .gitignore             # File da ignorare
```

## 🔧 Sviluppo Locale

Per testare in locale:

```bash
# Installa dipendenze
pip install -r requirements.txt

# Esporta variabili d'ambiente
export BACKMARKET_TOKEN="..."
export REFURBED_TOKEN="..."
# ... altre variabili

# Avvia app
python app.py
```

Accedi a: `http://localhost:5000`

## 📊 Flusso Operativo

```
┌─────────────────┐
│  BackMarket API │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│  Refurbed API   │─────►│   Flask App  │
└─────────────────┘      └──────┬───────┘
                                │
┌─────────────────┐             │
│ CDiscount API   │─────────────┘
└─────────────────┘
                                │
                    ┌───────────┴──────────┐
                    │                      │
                    ▼                      ▼
            ┌───────────────┐      ┌──────────────┐
            │ CSV Packlink  │      │ DDT InvoiceX │
            └───────────────┘      └──────────────┘
```

## 🛡️ Sicurezza

- ✅ Token API memorizzati come variabili d'ambiente
- ✅ Connessioni HTTPS per tutte le API
- ✅ IP statico whitelistato per database InvoiceX
- ✅ Credenziali database non hardcoded nel codice

## 🔍 Troubleshooting

### Errore connessione InvoiceX

**Problema:** `Access denied for user 'ilblogdi_inv2021'@'[IP]'`

**Soluzione:**
1. Verifica che l'IP statico di Railway sia whitelistato
2. Controlla che le credenziali siano corrette nelle variabili d'ambiente
3. Testa connessione da Railway con:
   ```bash
   mysql -h nl1-ts3.a2hosting.com -u ilblogdi_inv2021 -p ilblogdi_invoicex2021
   ```

### Errore API marketplace

**Problema:** Token scaduto o non valido

**Soluzione:**
1. Rigenera il token sul portale del marketplace
2. Aggiorna la variabile d'ambiente su Railway
3. Rideploy l'applicazione

### CSV vuoto

**Problema:** Nessun ordine trovato

**Soluzione:**
1. Verifica che ci siano ordini "da spedire" sui marketplace
2. Controlla i log Railway per errori API
3. Testa manualmente le API dei marketplace

## 📝 Note Tecniche

### Limitazioni Rate Limiting

- **BackMarket**: ~100 richieste/minuto
- **Refurbed**: ~60 richieste/minuto  
- **CDiscount**: Token JWT valido 1 ora

Il sistema gestisce automaticamente i rate limit con retry.

### Formato DDT InvoiceX

I DDT vengono creati nella tabella `documenti_vendita` con:
- `tipo`: DDT
- `numero`: Auto-incrementante per anno
- `cliente`: Nome destinatario
- `note`: Riferimento ordine marketplace

### Gestione Stock

Il sistema **NON** aggiorna automaticamente lo stock. 

Per integrare l'aggiornamento stock, aggiungi logica nel metodo `create_ddt()` per decrementare `movimenti_magazzino` dopo la creazione del DDT.

## 🆘 Supporto

Per problemi o domande:

1. Controlla i log su Railway Dashboard
2. Verifica variabili d'ambiente
3. Testa endpoint `/health` per status sistema

## 📄 License

Proprietario: ReflexMania
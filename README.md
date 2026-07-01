# Microservizi Libreria

Progetto d'esame (ITS) — gestione di una libreria con prestiti, realizzata come
**architettura a microservizi poliglotta** orchestrata con Docker Compose.
Il valore del progetto sta nell'**infrastruttura** (broker, registry, Portainer,
scaling), non nella logica di business, volutamente minima.

---

## Architettura

```
                       ┌──────────────┐
   browser  ──HTTP──▶  │  frontend    │  Nginx  (HTML+JS statico)
   :8080              └──────┬───────┘
                             │ fetch GET /libri, POST /prestiti
                             ▼
                       ┌──────────────┐        ┌──────────────┐
                       │     api      │──SQL──▶│  postgres    │  DB prestiti/libri
                       │  FastAPI     │        └──────────────┘
                       │  (Python)    │
                       └──────┬───────┘
                              │ publish JSON su coda "notifiche"
                              ▼
                       ┌──────────────┐
                       │  rabbitmq    │  broker (3-management)
                       └──────┬───────┘
                              │ consume (ack manuale)
                              ▼
                       ┌──────────────┐
                       │   worker     │  Node.js  → logga la notifica
                       │  (scalabile) │
                       └──────────────┘

   registry:2  (localhost:5000)   →  immagini di api/worker/frontend
   portainer   (localhost:9443)   →  monitoraggio dello stack
```

**Flusso asincrono**: `POST /prestiti` scrive sul DB, risponde **201 subito** e
pubblica un messaggio sulla coda `notifiche`. Il **worker** consuma in modo
indipendente e logga la notifica — l'invio NON è sincrono nell'endpoint.

Messaggio (JSON): `{ "tipo": "prestito.creato", "utente", "libro", "scadenza" }`
Coda `notifiche`: **durable** + **ack manuale** → sicura ai riavvii e scalabile.

---

## Servizi e porte

| Servizio   | Immagine                      | Porta host        | Ruolo                          |
|------------|-------------------------------|-------------------|--------------------------------|
| frontend   | localhost:5000/lib-frontend   | 8080 → 80         | UI (catalogo + form prestito)  |
| api        | localhost:5000/lib-api        | 8000 → 8000       | CRUD libri/prestiti + publisher|
| worker     | localhost:5000/lib-worker     | —                 | consumer notifiche (scalabile) |
| postgres   | postgres:16-alpine            | — (interno 5432)  | persistenza                    |
| rabbitmq   | rabbitmq:3-management         | 5672, 15672       | broker + management UI         |
| registry   | registry:2                    | 5000              | registro immagini locale       |
| portainer  | portainer-ce:2.21.4           | 9443              | monitoraggio                   |

---

## Prerequisiti

- **Docker Desktop** in esecuzione, modalità **container Linux**.
- **Windows + PowerShell** (i comandi sotto sono in sintassi PowerShell).
- Porte libere sull'host: `8080, 8000, 5672, 15672, 5000, 9443`.

---

## Setup DA ZERO

### 1. Variabili d'ambiente
Copia il template e personalizza le credenziali (il file `.env` NON è versionato):
```powershell
Copy-Item .env.example .env
# poi apri .env e imposta le password
```

### 2. Avvia il registry
Deve essere su prima di pushare le immagini:
```powershell
docker compose up -d registry
```

### 3. Build delle immagini
Vengono già taggate come `localhost:5000/lib-*:1.0` (grazie a `build:` + `image:`):
```powershell
docker compose build api worker frontend
```

### 4. Push sul registry
```powershell
docker compose push api worker frontend
```

Verifica che siano presenti:
```powershell
curl.exe http://localhost:5000/v2/_catalog
```

### 5. Avvia tutto lo stack
Il compose **pulla** le immagini dal registry e avvia i servizi nell'ordine
corretto (healthcheck su RabbitMQ e Postgres):
```powershell
docker compose up -d
```

### 6. Apri le interfacce
- **Frontend**: http://localhost:8080 (catalogo dal DB + form prestito)
- **RabbitMQ management**: http://localhost:15672 (login = credenziali `.env`)
- **Portainer**: https://localhost:9443 (al primo accesso crea l'utente admin)

---

## Verifica del flusso end-to-end

1. Apri http://localhost:8080 e invia un prestito.
2. La risposta è **201** e il prestito è salvato su Postgres:
   ```powershell
   docker exec -it lib-postgres psql -U libreria -d libreria -c "SELECT * FROM prestiti;"
   ```
3. Il worker consuma la notifica (ack manuale) e la logga:
   ```powershell
   docker compose logs -f worker
   # atteso: [worker] notifica ricevuta: { tipo: 'prestito.creato', ... }
   ```
4. Nella coda `notifiche` (UI :15672) la colonna **Ready** torna a 0 dopo il consumo.

---

## Scaling del worker (tramite il broker)

La scalabilità è gestita dal broker: più istanze del worker consumano dalla
stessa coda, una notifica per volta a istanza (`prefetch(1)`).
```powershell
docker compose up -d --scale worker=3
```
Verifica le 3 istanze attive in Portainer (Containers) o con:
```powershell
docker compose ps worker
```
Crea più prestiti e osserva nei log che le notifiche si distribuiscono tra le istanze.

> Nota: il worker NON espone `ports:` proprio per permettere `--scale` senza conflitti.

---

## Monitoraggio con Portainer

1. Apri https://localhost:9443 (certificato self-signed: prosegui).
2. Crea l'utente **admin** al primo accesso (se scade il tempo: `docker restart lib-portainer`).
3. Ambiente **local** → vedi container, immagini, volumi, log e stato di tutto lo stack.

---

## Teardown

```powershell
# ferma e rimuove i container, mantenendo i dati (volumi)
docker compose down

# rimuove ANCHE i volumi: dati DB, immagini del registry, config Portainer
docker compose down -v
```

---

## Consegna (pulizia)

Lo zip della consegna **non deve** contenere:
`node_modules/`, `__pycache__/`, `venv/`, volumi/dati del DB, immagini Docker, `.env`.
Sono tutti già esclusi da `.gitignore` e dai `.dockerignore`; il file `.env`
reale resta locale, nel repo c'è solo `.env.example`.

Comando di riferimento (PowerShell) per creare lo zip escludendo i superflui —
**da eseguire manualmente al momento della consegna**:
```powershell
# esempio: esclude le cartelle generate
Get-ChildItem -Recurse -Force `
  | Where-Object { $_.FullName -notmatch 'node_modules|__pycache__|\\.git\\|\.env$' } `
  | Compress-Archive -DestinationPath ..\libreria-microservizi.zip
```

---

## Comandi rapidi

| Azione              | Comando                                             |
|---------------------|-----------------------------------------------------|
| Avvio stack         | `docker compose up -d`                              |
| Build + push        | `docker compose build ; docker compose push`        |
| Scaling worker      | `docker compose up -d --scale worker=3`             |
| Log worker          | `docker compose logs -f worker`                     |
| Stato servizi       | `docker compose ps`                                 |
| Teardown (con dati) | `docker compose down -v`                            |

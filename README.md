# Microservizi Libreria

Applicazione Docker Compose per una libreria con due microservizi FastAPI,
RabbitMQ, due database PostgreSQL separati, frontend statico, worker Node.js,
registry locale e Portainer.

## Architettura

```text
Browser :8080
  |-- GET /libri, POST /prestiti ---------> prestito :8000 ---> postgres_prestito
  |                                             |
  |                                             | RabbitMQ topic exchange libreria.eventi
  |                                             | routing key prestito.creato
  |                                             v
  |-- GET/PATCH /prestiti ---------------> modifica :8001 ---> postgres_modifica
                                                |
                                                | RabbitMQ topic exchange libreria.eventi
                                                | routing key prestito.modificato
                                                v
                                          prestito aggiorna il proprio DB

prestito pubblica anche sulla coda durable notifiche, consumata dal worker Node.js.
```

La sincronizzazione tra i DB e' asincrona: ogni servizio scrive solo sul proprio
database e comunica gli eventi tramite RabbitMQ.

## Flussi

- `POST http://localhost:8000/prestiti`: il servizio `prestito` salva sul DB
  `postgres_prestito`, pubblica `prestito.creato` sull'exchange
  `libreria.eventi` e pubblica una notifica sulla coda `notifiche`.
- `modifica` consuma `prestito.creato` dalla coda `modifica.sync.prestiti` e
  aggiorna il DB `postgres_modifica`.
- `PATCH http://localhost:8001/prestiti/{id}`: il servizio `modifica` aggiorna
  la scadenza sul suo DB e pubblica `prestito.modificato`.
- `prestito` consuma `prestito.modificato` dalla coda `prestito.sync.modifiche`
  e aggiorna il DB `postgres_prestito`.
- `worker` consuma la coda `notifiche` con ack manuale e logga le notifiche.

## Servizi e porte

| Servizio          | Porta host  | Ruolo                                      |
|-------------------|-------------|--------------------------------------------|
| frontend          | 8080        | UI catalogo, creazione e modifica prestiti |
| prestito          | 8000        | Creazione prestiti, catalogo, sync modifiche |
| modifica          | 8001        | Modifica prestiti, DB separato, sync prestiti |
| rabbitmq          | 5672, 15672 | Broker + management UI                     |
| postgres_prestito | interna     | DB del microservizio prestito              |
| postgres_modifica | interna     | DB del microservizio modifica              |
| worker            | interna     | Consumer notifiche                         |
| registry          | 5000        | Registry Docker locale                     |
| portainer         | 9443        | Monitoraggio container                     |

## Avvio

```powershell
docker compose up -d --build
```

Interfacce:

- Frontend: http://localhost:8080
- Prestito API: http://localhost:8000/docs
- Modifica API: http://localhost:8001/docs
- RabbitMQ management: http://localhost:15672
- Portainer: https://localhost:9443

Le credenziali sono nel file `.env`.

## Verifica rapida

1. Apri http://localhost:8080 e crea un prestito.
2. Dopo pochi istanti il prestito appare nella sezione "Modifica prestiti",
   letta dal microservizio `modifica`.
3. Cambia la scadenza e salva.
4. Controlla che il DB di `prestito` sia aggiornato in modo asincrono:

```powershell
docker exec -it lib-postgres-prestito psql -U libreria -d libreria -c "SELECT id, utente, libro, scadenza FROM prestiti ORDER BY id DESC;"
docker exec -it lib-postgres-modifica psql -U libreria -d libreria_modifica -c "SELECT id, utente, libro, scadenza FROM prestiti_modificabili ORDER BY id DESC;"
```

Log utili:

```powershell
docker compose logs -f prestito modifica worker
```

## Build e registry locale

```powershell
docker compose up -d registry
docker compose build prestito modifica worker frontend
docker compose push prestito modifica worker frontend
curl.exe http://localhost:5000/v2/_catalog
```

## Scaling worker

Il worker non espone porte, quindi puo' essere scalato senza conflitti:

```powershell
docker compose up -d --scale worker=3
```

## Teardown

```powershell
docker compose down
docker compose down -v
```

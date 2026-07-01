

import json
import os

import pika
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Libreria API")

# CORS: il frontend gira nel browser su un'altra origine (Nginx, porta 8080)
# e chiama questa API su :8000 
_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:8080,http://127.0.0.1:8080",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Host e credenziali del broker: in compose l'host è il servizio "rabbitmq",
# user/pass arrivano dal .env 
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_DEFAULT_PASS", "guest")
CODA = "notifiche"

# Parametri di connessione a PostgreSQL.
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "libreria"),
    "user": os.getenv("POSTGRES_USER", "libreria"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}


def get_connection():
    """Apre una connessione a PostgreSQL.

    L'attesa che il DB sia pronto è gestita a livello di compose
    (healthcheck + depends_on), quindi qui non serve retry.
    """
    return psycopg2.connect(**DB_CONFIG)


class Prestito(BaseModel):
    """Dati minimi di un prestito ricevuti nel body della richiesta."""
    utente: str
    libro: str
    scadenza: str  # data in formato stringa, es. "2026-07-10"


def pubblica_notifica(messaggio: dict) -> None:
    """Apre una connessione al broker, dichiara la coda e pubblica il messaggio.

    La coda è dichiarata DURABLE e il messaggio PERSISTENTE: così sopravvivono
    al riavvio del broker (requisito d'esame).
    """
    connessione = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            credentials=pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS),
        )
    )
    canale = connessione.channel()
    canale.queue_declare(queue=CODA, durable=True)
    canale.basic_publish(
        exchange="",
        routing_key=CODA,
        body=json.dumps(messaggio),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,  # messaggio persistente su disco
        ),
    )
    connessione.close()


@app.get("/health")
def health():
    """Endpoint di servizio per verificare che l'api sia su."""
    return {"stato": "ok"}


@app.get("/libri")
def lista_libri():
    """Restituisce il catalogo leggendolo dal DB."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, titolo, autore FROM libri ORDER BY titolo;")
            return cur.fetchall()
    finally:
        conn.close()


@app.post("/prestiti", status_code=201)
def crea_prestito(prestito: Prestito):
    #  Il prestito viene salvato in modo asincrono su PostgreSQL.
    conn = get_connection()
    try:
        with conn:  # transazione: commit automatico se non solleva
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO prestiti (utente, libro, scadenza) "
                    "VALUES (%s, %s, %s) RETURNING id;",
                    (prestito.utente, prestito.libro, prestito.scadenza),
                )
                prestito_id = cur.fetchone()[0]
    except psycopg2.Error as err:
        raise HTTPException(status_code=500, detail=f"Errore DB: {err}")
    finally:
        conn.close()

    # Viene pubblicata la notifica sulla coda (asincrona, la consuma il worker).
    messaggio = {
        "tipo": "prestito.creato",
        "utente": prestito.utente,
        "libro": prestito.libro,
        "scadenza": prestito.scadenza,
    }
    pubblica_notifica(messaggio)

    #  Risposta 201: il prestito è salvato, la notifica viaggia in coda.
    return {
        "stato": "creato",
        "id": prestito_id,
        "notifica_pubblicata": True,
        "prestito": messaggio,
    }

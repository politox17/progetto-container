import json
import os
import threading
import time

import pika
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Libreria Prestito API")

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

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_DEFAULT_PASS", "guest")
CODA_NOTIFICHE = os.getenv("CODA_NOTIFICHE", "notifiche")
EVENT_EXCHANGE = os.getenv("EVENT_EXCHANGE", "libreria.eventi")
SYNC_QUEUE = os.getenv("PRESTITO_SYNC_QUEUE", "prestito.sync.modifiche")

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "libreria"),
    "user": os.getenv("POSTGRES_USER", "libreria"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}


class Prestito(BaseModel):
    utente: str
    libro: str
    scadenza: str


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def assicura_schema() -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE prestiti "
                    "ADD COLUMN IF NOT EXISTS aggiornato_at TIMESTAMPTZ NOT NULL DEFAULT now();"
                )
    finally:
        conn.close()


def rabbit_connection():
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            credentials=pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS),
        )
    )


def dichiara_topologia(canale) -> None:
    canale.queue_declare(queue=CODA_NOTIFICHE, durable=True)
    canale.exchange_declare(exchange=EVENT_EXCHANGE, exchange_type="topic", durable=True)


def pubblica_evento(routing_key: str, messaggio: dict) -> None:
    connessione = rabbit_connection()
    canale = connessione.channel()
    dichiara_topologia(canale)
    canale.basic_publish(
        exchange=EVENT_EXCHANGE,
        routing_key=routing_key,
        body=json.dumps(messaggio),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )
    connessione.close()


def pubblica_notifica(messaggio: dict) -> None:
    connessione = rabbit_connection()
    canale = connessione.channel()
    dichiara_topologia(canale)
    canale.basic_publish(
        exchange="",
        routing_key=CODA_NOTIFICHE,
        body=json.dumps(messaggio),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )
    connessione.close()


def applica_modifica_prestito(evento: dict) -> None:
    prestito_id = evento.get("id")
    scadenza = evento.get("scadenza")
    if not prestito_id or not scadenza:
        raise ValueError("evento prestito.modificato incompleto")

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE prestiti SET scadenza = %s, aggiornato_at = now() WHERE id = %s;",
                    (scadenza, prestito_id),
                )
    finally:
        conn.close()


def consuma_modifiche():
    while True:
        try:
            connessione = rabbit_connection()
            canale = connessione.channel()
            dichiara_topologia(canale)
            canale.queue_declare(queue=SYNC_QUEUE, durable=True)
            canale.queue_bind(
                exchange=EVENT_EXCHANGE,
                queue=SYNC_QUEUE,
                routing_key="prestito.modificato",
            )
            canale.basic_qos(prefetch_count=1)

            def callback(ch, method, properties, body):
                try:
                    evento = json.loads(body.decode("utf-8"))
                    applica_modifica_prestito(evento)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as err:
                    print(f"[prestito] errore sync modifica: {err}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            print(f'[prestito] in ascolto sulla coda "{SYNC_QUEUE}"')
            canale.basic_consume(queue=SYNC_QUEUE, on_message_callback=callback)
            canale.start_consuming()
        except Exception as err:
            print(f"[prestito] RabbitMQ non pronto o connessione persa: {err}. Riprovo...")
            time.sleep(3)


@app.on_event("startup")
def avvia_consumer_modifiche():
    assicura_schema()
    thread = threading.Thread(target=consuma_modifiche, daemon=True)
    thread.start()


@app.get("/health")
def health():
    return {"stato": "ok"}


@app.get("/libri")
def lista_libri():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, titolo, autore FROM libri ORDER BY titolo;")
            return cur.fetchall()
    finally:
        conn.close()


@app.get("/prestiti")
def lista_prestiti():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, utente, libro, scadenza, creato_at, aggiornato_at "
                "FROM prestiti ORDER BY id DESC;"
            )
            return cur.fetchall()
    finally:
        conn.close()


@app.post("/prestiti", status_code=201)
def crea_prestito(prestito: Prestito):
    conn = get_connection()
    try:
        with conn:
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

    messaggio = {
        "tipo": "prestito.creato",
        "id": prestito_id,
        "utente": prestito.utente,
        "libro": prestito.libro,
        "scadenza": prestito.scadenza,
    }
    pubblica_evento("prestito.creato", messaggio)
    pubblica_notifica(messaggio)

    return {
        "stato": "creato",
        "id": prestito_id,
        "evento_pubblicato": True,
        "notifica_pubblicata": True,
        "prestito": messaggio,
    }

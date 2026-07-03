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

app = FastAPI(title="Libreria Modifica API")

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
EVENT_EXCHANGE = os.getenv("EVENT_EXCHANGE", "libreria.eventi")
SYNC_QUEUE = os.getenv("MODIFICA_SYNC_QUEUE", "modifica.sync.prestiti")

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "libreria_modifica"),
    "user": os.getenv("POSTGRES_USER", "libreria"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}


class ModificaPrestito(BaseModel):
    scadenza: str


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def assicura_schema() -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS prestiti_modificabili (
                        id               INTEGER PRIMARY KEY,
                        utente           TEXT NOT NULL,
                        libro            TEXT NOT NULL,
                        scadenza         DATE NOT NULL,
                        modificato_at    TIMESTAMPTZ,
                        sincronizzato_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
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
    canale.exchange_declare(exchange=EVENT_EXCHANGE, exchange_type="topic", durable=True)


def upsert_prestito(evento: dict) -> None:
    prestito_id = evento.get("id")
    if not prestito_id:
        raise ValueError("evento prestito.creato senza id")

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO prestiti_modificabili
                        (id, utente, libro, scadenza, sincronizzato_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE SET
                        utente = EXCLUDED.utente,
                        libro = EXCLUDED.libro,
                        scadenza = EXCLUDED.scadenza,
                        sincronizzato_at = now();
                    """,
                    (
                        prestito_id,
                        evento.get("utente"),
                        evento.get("libro"),
                        evento.get("scadenza"),
                    ),
                )
    finally:
        conn.close()


def pubblica_modifica(evento: dict) -> None:
    connessione = rabbit_connection()
    canale = connessione.channel()
    dichiara_topologia(canale)
    canale.basic_publish(
        exchange=EVENT_EXCHANGE,
        routing_key="prestito.modificato",
        body=json.dumps(evento),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )
    connessione.close()


def consuma_prestiti_creati():
    while True:
        try:
            connessione = rabbit_connection()
            canale = connessione.channel()
            dichiara_topologia(canale)
            canale.queue_declare(queue=SYNC_QUEUE, durable=True)
            canale.queue_bind(
                exchange=EVENT_EXCHANGE,
                queue=SYNC_QUEUE,
                routing_key="prestito.creato",
            )
            canale.basic_qos(prefetch_count=1)

            def callback(ch, method, properties, body):
                try:
                    evento = json.loads(body.decode("utf-8"))
                    upsert_prestito(evento)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as err:
                    print(f"[modifica] errore sync prestito: {err}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            print(f'[modifica] in ascolto sulla coda "{SYNC_QUEUE}"')
            canale.basic_consume(queue=SYNC_QUEUE, on_message_callback=callback)
            canale.start_consuming()
        except Exception as err:
            print(f"[modifica] RabbitMQ non pronto o connessione persa: {err}. Riprovo...")
            time.sleep(3)


@app.on_event("startup")
def avvia_consumer_prestiti():
    assicura_schema()
    thread = threading.Thread(target=consuma_prestiti_creati, daemon=True)
    thread.start()


@app.get("/health")
def health():
    return {"stato": "ok"}


@app.get("/prestiti")
def lista_prestiti_modificabili():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, utente, libro, scadenza, modificato_at, sincronizzato_at "
                "FROM prestiti_modificabili ORDER BY id DESC;"
            )
            return cur.fetchall()
    finally:
        conn.close()


@app.patch("/prestiti/{prestito_id}")
def modifica_prestito(prestito_id: int, modifica: ModificaPrestito):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE prestiti_modificabili
                    SET scadenza = %s, modificato_at = now()
                    WHERE id = %s
                    RETURNING id, utente, libro, scadenza;
                    """,
                    (modifica.scadenza, prestito_id),
                )
                riga = cur.fetchone()
                if not riga:
                    raise HTTPException(
                        status_code=404,
                        detail="Prestito non ancora sincronizzato nel servizio modifica",
                    )
    except psycopg2.Error as err:
        raise HTTPException(status_code=500, detail=f"Errore DB: {err}")
    finally:
        conn.close()

    evento = {
        "tipo": "prestito.modificato",
        "id": riga[0],
        "utente": riga[1],
        "libro": riga[2],
        "scadenza": riga[3].isoformat(),
    }
    pubblica_modifica(evento)
    return {"stato": "modificato", "evento_pubblicato": True, "prestito": evento}

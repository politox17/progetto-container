
const amqp = require("amqplib");

const RABBITMQ_HOST = process.env.RABBITMQ_HOST || "localhost";
const RABBITMQ_USER = process.env.RABBITMQ_DEFAULT_USER || "guest";
const RABBITMQ_PASS = process.env.RABBITMQ_DEFAULT_PASS || "guest";
const CODA = "notifiche";

// Parametri di retry per la connessione iniziale al broker.
const MAX_TENTATIVI = 30;
const ATTESA_MS = 3000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Tenta la connessione al broker più volte  */
async function connettiConRetry() {
  for (let tentativo = 1; tentativo <= MAX_TENTATIVI; tentativo++) {
    try {
      const connessione = await amqp.connect(
        `amqp://${RABBITMQ_USER}:${RABBITMQ_PASS}@${RABBITMQ_HOST}`
      );
      console.log(`[worker] connesso a RabbitMQ (tentativo ${tentativo})`);
      return connessione;
    } catch (err) {
      console.log(
        `[worker] RabbitMQ non pronto (tentativo ${tentativo}/${MAX_TENTATIVI}): ${err.message}. Riprovo tra ${ATTESA_MS}ms...`
      );
      await sleep(ATTESA_MS);
    }
  }
  throw new Error("[worker] impossibile connettersi a RabbitMQ, esco.");
}

async function main() {
  const connessione = await connettiConRetry();
  const canale = await connessione.createChannel();

  await canale.assertQueue(CODA, { durable: true });

  canale.prefetch(1);

  console.log(`[worker] in ascolto sulla coda "${CODA}". In attesa di notifiche...`);

  canale.consume(
    CODA,
    (msg) => {
      if (msg === null) return; // coda cancellata dal broker

      try {
        const notifica = JSON.parse(msg.content.toString());
        console.log("[worker] notifica ricevuta:", notifica);

        canale.ack(msg);
      } catch (err) {
        console.error("[worker] errore nel gestire il messaggio:", err.message);
        // nack senza requeue: messaggio malformato, evito loop infiniti.
        canale.nack(msg, false, false);
      }
    },
    { noAck: false } // ack manuale attivo
  );

  // Chiusura pulita su stop del container.
  const chiudi = async () => {
    console.log("[worker] chiusura in corso...");
    try {
      await canale.close();
      await connessione.close();
    } finally {
      process.exit(0);
    }
  };
  process.on("SIGINT", chiudi);
  process.on("SIGTERM", chiudi);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});

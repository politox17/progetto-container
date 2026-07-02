-- Passo 4 — schema + seed della libreria.
-- Questo script viene eseguito da Postgres SOLO alla prima inizializzazione
-- del volume dati (cartella /docker-entrypoint-initdb.d). Sui riavvii
-- successivi, con il volume già popolato, NON viene rieseguito.

CREATE TABLE IF NOT EXISTS libri (
    id     SERIAL PRIMARY KEY,
    titolo TEXT NOT NULL,
    autore TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prestiti (
    id        SERIAL PRIMARY KEY,
    utente    TEXT NOT NULL,
    libro     TEXT NOT NULL,
    scadenza  DATE NOT NULL,
    creato_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed: qualche libro così il catalogo non è vuoto al primo avvio.
INSERT INTO libri (titolo, autore) VALUES
    ('Il nome della rosa',        'Umberto Eco'),
    ('1984',                      'George Orwell'),
    ('Il Signore degli Anelli',   'J.R.R. Tolkien'),
    ('Cent''anni di solitudine',  'Gabriel García Márquez'),
    ('Il Gattopardo',             'Giuseppe Tomasi di Lampedusa');

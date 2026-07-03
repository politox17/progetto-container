CREATE TABLE IF NOT EXISTS prestiti_modificabili (
    id               INTEGER PRIMARY KEY,
    utente           TEXT NOT NULL,
    libro            TEXT NOT NULL,
    scadenza         DATE NOT NULL,
    modificato_at    TIMESTAMPTZ,
    sincronizzato_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

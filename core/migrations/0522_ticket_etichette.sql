-- TKT-068: etichette colorate dei ticket. Al massimo 25 per server (nome ≤ 32), assegnate dal menu «Gestisci».
CREATE TABLE IF NOT EXISTS ticket_etichette (
    id       SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    nome     VARCHAR(32) NOT NULL,
    colore   INTEGER NOT NULL DEFAULT 5793266 CHECK (colore BETWEEN 0 AND 16777215),
    emoji    VARCHAR(64)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_etichette_nome ON ticket_etichette (guild_id, lower(nome));
CREATE TABLE IF NOT EXISTS ticket_etichette_assegnate (
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    etichetta_id INTEGER NOT NULL REFERENCES ticket_etichette(id) ON DELETE CASCADE,
    PRIMARY KEY (ticket_id, etichetta_id)
);

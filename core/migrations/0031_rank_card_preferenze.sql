-- #83 (NF-12): colore e tema scelti da ciascuno per la propria rank card.
-- Valgono in tutti i server. Il colore è un esadecimale "#RRGGBB"; non c'è
-- altro dato personale.
CREATE TABLE IF NOT EXISTS rank_card_prefs (
    user_id BIGINT PRIMARY KEY,
    colore  TEXT CHECK (colore IS NULL OR colore ~ '^#[0-9A-F]{6}$'),
    tema    TEXT CHECK (tema IS NULL OR tema IN ('scuro', 'chiaro', 'notte'))
);

-- M 9.13: /clan info mostra gli ultimi movimenti della tesoreria, senza
-- i tick vocali (uno al minuto per membro: sono quasi tutte le righe).
-- Questo indice parziale tiene veloce la lettura anche quando lo
-- storico di una gilda ha milioni di tick.
CREATE INDEX IF NOT EXISTS idx_clan_treasury_ledger_movimenti
    ON clan_treasury_ledger (clan_id, id DESC)
    WHERE reason <> 'voice_tick';

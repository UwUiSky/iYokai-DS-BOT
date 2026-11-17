-- STA-054, 055 (#130): le classifiche degli inviti del periodo leggono per data di ingresso.
CREATE INDEX IF NOT EXISTS idx_invite_joins_data ON invite_joins (guild_id, joined_at);

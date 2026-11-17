-- Catalogo #123 (RUO-027): avviso in un canale quando cambia l'argomento di un canale.
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS topic_notice_channel_id BIGINT;

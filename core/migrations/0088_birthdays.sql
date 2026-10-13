-- NF-26 (#97): compleanni. Solo giorno e mese (niente anno, meno dati personali).
CREATE TABLE IF NOT EXISTS birthdays (
    guild_id            BIGINT NOT NULL,
    user_id             BIGINT NOT NULL,
    day                 SMALLINT NOT NULL CHECK (day BETWEEN 1 AND 31),
    month               SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    last_announced_year SMALLINT,
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_birthdays_data ON birthdays (month, day);

CREATE TABLE IF NOT EXISTS birthday_config (
    guild_id   BIGINT PRIMARY KEY,
    channel_id BIGINT,
    role_id    BIGINT,
    message    TEXT NOT NULL DEFAULT '🎂 Buon compleanno {users}!' CHECK (char_length(message) <= 500),
    ping_ruoli BOOLEAN NOT NULL DEFAULT FALSE
);

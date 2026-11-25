-- D58 (#77): la lingua personale accetta tutte le lingue del bot, non solo italiano e inglese.
-- Gli stessi codici che core/i18n.py salva (en-US si salva come «en»). Rilanciarla non cambia nulla.
ALTER TABLE user_language DROP CONSTRAINT IF EXISTS user_language_language_check;
ALTER TABLE user_language ADD CONSTRAINT user_language_language_check
    CHECK (language IN ('it', 'en', 'de', 'es-ES', 'fr', 'ja', 'ko', 'ru', 'uk', 'zh-CN'));

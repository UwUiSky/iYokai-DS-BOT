-- Catalogo #123 (RUO-004, 007, 008, 010): opacità dello sfondo, allineamento e colore del nome,
-- testo libero sull'immagine e ordine tra immagine e testo.
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_opacity INTEGER NOT NULL DEFAULT 65;
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_text TEXT NOT NULL DEFAULT '';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_order TEXT NOT NULL DEFAULT 'insieme';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_align TEXT NOT NULL DEFAULT 'sinistra';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_name_color TEXT NOT NULL DEFAULT '';

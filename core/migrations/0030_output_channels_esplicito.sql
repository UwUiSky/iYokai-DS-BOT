-- #72: una riga nata dal ripiego (post del forum, avviso mandato) non e una
-- scelta di chi amministra il server: segue il canale generale. `esplicito`
-- e vero solo per le righe scritte da /log canale, /log crea-canali, /log crea-forum.
ALTER TABLE output_channels
    ADD COLUMN IF NOT EXISTS esplicito BOOLEAN NOT NULL DEFAULT TRUE;

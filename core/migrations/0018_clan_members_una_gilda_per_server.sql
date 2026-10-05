-- M 9.8: un utente sta in una sola gilda per server. Finora lo
-- controllava il codice con una lettura fatta prima della scrittura;
-- ora lo garantisce un vincolo unico, così due ingressi arrivati
-- insieme non passano tutti e due.
ALTER TABLE clan_members ADD COLUMN IF NOT EXISTS guild_id BIGINT;

-- Le righe già presenti prendono il server dalla loro gilda.
UPDATE clan_members m
SET guild_id = c.guild_id
FROM clans c
WHERE c.id = m.clan_id AND m.guild_id IS NULL;

-- Righe rimaste senza gilda (gilda cancellata): non servono più.
DELETE FROM clan_members WHERE guild_id IS NULL;

-- Doppioni nati prima del vincolo (stesso utente in più gilde dello
-- stesso server): resta l'appartenenza da capo; a parità, la più vecchia.
DELETE FROM clan_members m
USING clan_members k
WHERE m.guild_id = k.guild_id
  AND m.user_id = k.user_id
  AND m.clan_id <> k.clan_id
  AND (
      (k.role = 'owner' AND m.role <> 'owner')
      OR (
          (k.role = 'owner') = (m.role = 'owner')
          AND (k.joined_at, k.clan_id) < (m.joined_at, m.clan_id)
      )
  );

ALTER TABLE clan_members ALTER COLUMN guild_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_clan_members_server_utente
    ON clan_members (guild_id, user_id);

-- M 14.12 (DB-2): chiavi esterne dove un'eliminazione lascerebbe righe orfane.
-- Sciogliere un clan toglie anche membri, movimenti e XP mensile (l'attività vocale
-- resta senza chiave: il suo repository si prova con clan finti e la pulisce il registro);
-- togliere un giveaway toglie i suoi iscritti. Prima si eliminano le righe già orfane.
DELETE FROM clan_members WHERE clan_id NOT IN (SELECT id FROM clans);
DELETE FROM clan_treasury_ledger WHERE clan_id NOT IN (SELECT id FROM clans);
DELETE FROM clan_monthly_xp WHERE clan_id NOT IN (SELECT id FROM clans);
DELETE FROM giveaway_entries WHERE giveaway_id NOT IN (SELECT id FROM giveaways);

ALTER TABLE clan_members DROP CONSTRAINT IF EXISTS fk_clan_members_clan;
ALTER TABLE clan_members ADD CONSTRAINT fk_clan_members_clan
    FOREIGN KEY (clan_id) REFERENCES clans (id) ON DELETE CASCADE;
ALTER TABLE clan_treasury_ledger DROP CONSTRAINT IF EXISTS fk_clan_treasury_ledger_clan;
ALTER TABLE clan_treasury_ledger ADD CONSTRAINT fk_clan_treasury_ledger_clan
    FOREIGN KEY (clan_id) REFERENCES clans (id) ON DELETE CASCADE;
ALTER TABLE clan_monthly_xp DROP CONSTRAINT IF EXISTS fk_clan_monthly_xp_clan;
ALTER TABLE clan_monthly_xp ADD CONSTRAINT fk_clan_monthly_xp_clan
    FOREIGN KEY (clan_id) REFERENCES clans (id) ON DELETE CASCADE;
ALTER TABLE giveaway_entries DROP CONSTRAINT IF EXISTS fk_giveaway_entries_giveaway;
ALTER TABLE giveaway_entries ADD CONSTRAINT fk_giveaway_entries_giveaway
    FOREIGN KEY (giveaway_id) REFERENCES giveaways (id) ON DELETE CASCADE;

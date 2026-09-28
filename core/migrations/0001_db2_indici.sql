-- DB-2 (REVIEW.md): indici mancanti su query che girano ogni ora, e
-- rimozione dei due indici di event_log mai usati da nessuna query.
--
-- idx_event_log_guild_role / idx_event_log_guild_case: role_id e
-- case_number compaiono solo in log_event() (INSERT) dentro
-- core/repositories/event_log_repo.py, mai in una WHERE di nessun
-- metodo di lettura — costavano solo in scrittura sulla tabella più
-- trafficata del progetto. Rimossi anche dalla run_migrations() di
-- base (per un database nuovo, che non li crea più affatto).
DROP INDEX IF EXISTS idx_event_log_guild_role;
DROP INDEX IF EXISTS idx_event_log_guild_case;

-- clans.get_unofficialized_expired() (core/repositories/
-- guild_clan_repo.py) gira ogni ora dentro
-- core/guild_clan_expiry_worker.py: "WHERE officialized = false AND
-- officialize_deadline <= $1", senza nessun indice a coprirla —
-- scansione completa della tabella clans ad ogni giro. "officialized
-- = false" è normalmente una minoranza (solo le gilde in periodo di
-- prova), quindi un indice parziale resta piccolo ed economico.
CREATE INDEX IF NOT EXISTS idx_clans_unofficialized_deadline
    ON clans (officialize_deadline)
    WHERE officialized = false;

-- leveling_repo.list_users_needing_weekly_decay() (core/repositories/
-- leveling_repo.py) gira ogni ora dentro
-- core/weekly_personal_decay_worker.py: "WHERE coins_total > 1 AND
-- last_weekly_decay_period IS DISTINCT FROM $1", SENZA filtro su
-- guild_id — una scansione completa di leveling_totals ad ogni giro,
-- non coperta dagli indici esistenti (tutti con guild_id come prima
-- colonna).
CREATE INDEX IF NOT EXISTS idx_leveling_totals_weekly_decay_due
    ON leveling_totals (last_weekly_decay_period)
    WHERE coins_total > 1;

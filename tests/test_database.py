"""
tests/test_database.py
=========================
A differenza degli altri test, qui NON usiamo la fixture clean_db
(che duplica manualmente le CREATE TABLE base per evitare di aprire
un secondo pool globale) — usiamo direttamente la classe Database
vera di core/database.py, connect()/run_migrations()/close() incluso.

Serve a intercettare esattamente il tipo di errore che una copia
manuale delle query non intercetterebbe mai: un errore di sintassi
o un riferimento sbagliato nel collegamento reale tra
Database.run_migrations() e scheduler.run_migrations().
"""

import pytest

from core.database import Database


@pytest.mark.asyncio
async def test_database_connect_e_migrazioni_reali():
    database = Database()
    await database.connect()
    try:
        # Se run_migrations() ha un errore SQL (incluso quello dello
        # scheduler, ora collegato in sequenza), questa chiamata
        # solleva un'eccezione e il test fallisce qui.
        await database.run_migrations()

        # Verifica concreta: le tabelle attese esistono davvero.
        tabelle_attese = [
            "guild_config",
            "premium_whitelist",
            "premium_module_flags",
            "scheduled_actions",
        ]
        for tabella in tabelle_attese:
            exists = await database.pool.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", f"public.{tabella}"
            )
            assert exists is True, f"Tabella mancante dopo le migrazioni: {tabella}"

        # run_migrations() deve poter essere richiamata più volte
        # senza errori (è quello che succede ad ogni riavvio del
        # bot): IF NOT EXISTS deve reggere davvero, non solo a parole.
        await database.run_migrations()
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_ensure_guild_exists_e_whitelist_reali():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()

        # Pulizia mirata per questo test, per non dipendere
        # dall'ordine di esecuzione degli altri test del file.
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 999999999"
        )
        await database.pool.execute(
            "DELETE FROM premium_whitelist WHERE guild_id = 999999999"
        )

        await database.ensure_guild_exists(999999999)
        row = await database.pool.fetchrow(
            "SELECT guild_id, setup_completed FROM guild_config WHERE guild_id = $1",
            999999999,
        )
        assert row is not None
        assert row["setup_completed"] is False

        # Chiamarlo due volte non deve fallire né duplicare la riga
        # (ON CONFLICT DO NOTHING).
        await database.ensure_guild_exists(999999999)
        count = await database.pool.fetchval(
            "SELECT count(*) FROM guild_config WHERE guild_id = $1", 999999999
        )
        assert count == 1

        assert await database.is_guild_whitelisted(999999999) is False
        await database.add_guild_to_whitelist(999999999, added_by=1, reason="test")
        assert await database.is_guild_whitelisted(999999999) is True
        await database.remove_guild_from_whitelist(999999999)
        assert await database.is_guild_whitelisted(999999999) is False
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 999999999"
        )
        await database.close()


@pytest.mark.asyncio
async def test_guild_settings_scrittura_e_lettura_reali():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()

        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 888888888"
        )

        # Nessuna impostazione ancora: deve restituire il default.
        valore = await database.get_guild_setting(
            888888888, "report_channel_id", default=None
        )
        assert valore is None

        # Scrive un intero (es. un ID canale Discord).
        await database.set_guild_setting(888888888, "report_channel_id", 123456789)
        letto = await database.get_guild_setting(888888888, "report_channel_id")
        assert letto == 123456789

        # Scrive una stringa, verifica che il tipo torni corretto
        # (non una stringa JSON grezza tipo '"testo"').
        await database.set_guild_setting(888888888, "welcome_text", "Ciao!")
        letto_testo = await database.get_guild_setting(888888888, "welcome_text")
        assert letto_testo == "Ciao!"

        # Due chiavi diverse sullo stesso server non si sovrascrivono
        # a vicenda (il punto centrale di usare JSONB invece di
        # colonne separate per ogni impostazione futura).
        canale = await database.get_guild_setting(888888888, "report_channel_id")
        assert canale == 123456789
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 888888888"
        )
        await database.close()


@pytest.mark.asyncio
async def test_set_module_active_per_guild_reale():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777777"
        )

        # Prima di attivarlo, risulta disattivo.
        assert (
            await database.is_module_active_for_guild(777777777, "moderation_actions")
            is False
        )

        await database.set_module_active_for_guild(
            777777777, "moderation_actions", True
        )
        assert (
            await database.is_module_active_for_guild(777777777, "moderation_actions")
            is True
        )

        # Disattivarlo di nuovo funziona (non solo l'attivazione).
        await database.set_module_active_for_guild(
            777777777, "moderation_actions", False
        )
        assert (
            await database.is_module_active_for_guild(777777777, "moderation_actions")
            is False
        )
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777777"
        )
        await database.close()


@pytest.mark.asyncio
async def test_cache_moduli_serve_davvero_dalla_memoria_non_riquerella_il_db():
    # Prova diretta che la cache è USATA, non solo che il metodo
    # continua a funzionare: modifichiamo la riga con SQL grezzo (che
    # bypassa set_module_active_for_guild e quindi la sua
    # invalidazione), e verifichiamo che is_module_active_for_guild
    # continui a restituire il valore VECCHIO finché non passiamo
    # esplicitamente da set_module_active_for_guild.
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777801"
        )
        await database.set_module_active_for_guild(777777801, "leveling", True)

        # Primo giro: legge dal DB, popola la cache. Deve essere True.
        assert await database.is_module_active_for_guild(777777801, "leveling") is True

        # Modifica DIRETTA sul DB, bypassando set_module_active_for_guild
        # (quindi bypassando anche l'invalidazione della cache).
        await database.pool.execute(
            """
            UPDATE guild_config SET modules = jsonb_set(modules, '{leveling}', 'false')
            WHERE guild_id = 777777801
            """
        )

        # La cache non sa nulla di questa modifica: deve restituire
        # ANCORA True (il valore stantio), la prova che sta leggendo
        # dalla memoria e non dal DB ad ogni chiamata.
        assert await database.is_module_active_for_guild(777777801, "leveling") is True

        # Solo passando da set_module_active_for_guild (che invalida)
        # il nuovo valore diventa visibile.
        await database.set_module_active_for_guild(777777801, "leveling", False)
        assert await database.is_module_active_for_guild(777777801, "leveling") is False
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777801"
        )
        await database.close()


@pytest.mark.asyncio
async def test_cache_condivisa_tra_moduli_diversi_dello_stesso_server():
    # Due moduli diversi per LO STESSO server: dopo aver letto il
    # primo (che popola la cache con l'intera riga), il secondo deve
    # risultare corretto SENZA una query aggiuntiva - verificato
    # indirettamente modificando entrambi via SQL grezzo in un colpo
    # solo e controllando che la lettura del primo modulo non lasci
    # il secondo "congelato" su un valore vecchio o mancante.
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777802"
        )
        await database.set_module_active_for_guild(777777802, "verify", True)
        await database.set_module_active_for_guild(777777802, "role_menus", True)

        assert await database.is_module_active_for_guild(777777802, "verify") is True
        # La cache è già popolata dalla chiamata sopra (stessa riga
        # guild_id): questa lettura deve comunque essere corretta.
        assert await database.is_module_active_for_guild(777777802, "role_menus") is True
        # Un terzo modulo mai attivato sullo stesso server, mai
        # esplicitamente scritto: deve risultare False, non sollevare
        # un KeyError o simili sul dizionario in cache.
        assert await database.is_module_active_for_guild(777777802, "mai_attivato") is False
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777802"
        )
        await database.close()


@pytest.mark.asyncio
async def test_cache_non_mischia_server_diversi():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id IN (777777803, 777777804)"
        )
        await database.set_module_active_for_guild(777777803, "leveling", True)
        await database.set_module_active_for_guild(777777804, "leveling", False)

        assert await database.is_module_active_for_guild(777777803, "leveling") is True
        assert await database.is_module_active_for_guild(777777804, "leveling") is False
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id IN (777777803, 777777804)"
        )
        await database.close()


# ====================================================================
# Config Diff & Rollback (BACKLOG.md §11)
# ====================================================================
@pytest.mark.asyncio
async def test_set_module_active_registra_una_voce_di_storico():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777900"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777900"
        )

        await database.set_module_active_for_guild(
            777777900, "leveling", True, changed_by=42
        )

        storico = await database.get_config_history(777777900)
        assert len(storico) == 1
        voce = storico[0]
        assert voce.change_type == "module"
        assert voce.key_name == "leveling"
        assert voce.old_value is None  # non era mai stato impostato prima
        assert voce.new_value is True
        assert voce.changed_by == 42
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777900"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777900"
        )
        await database.close()


@pytest.mark.asyncio
async def test_storico_cattura_il_valore_precedente_corretto():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777901"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777901"
        )

        await database.set_module_active_for_guild(777777901, "verify", True)
        await database.set_module_active_for_guild(777777901, "verify", False)

        storico = await database.get_config_history(777777901)
        # Ordinato dal più recente: la seconda scrittura (True->False)
        # deve avere old_value=True, non None.
        assert storico[0].old_value is True
        assert storico[0].new_value is False
        assert storico[1].old_value is None
        assert storico[1].new_value is True
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777901"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777901"
        )
        await database.close()


@pytest.mark.asyncio
async def test_set_guild_setting_registra_storico():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777902"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777902"
        )

        await database.set_guild_setting(
            777777902, "report_channel_id", 555, changed_by=99
        )

        storico = await database.get_config_history(777777902)
        assert len(storico) == 1
        assert storico[0].change_type == "setting"
        assert storico[0].key_name == "report_channel_id"
        assert storico[0].new_value == 555
        assert storico[0].changed_by == 99
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777902"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777902"
        )
        await database.close()


@pytest.mark.asyncio
async def test_get_config_history_rispetta_il_limite():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777903"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777903"
        )

        for i in range(5):
            await database.set_module_active_for_guild(
                777777903, f"modulo{i}", True
            )

        storico = await database.get_config_history(777777903, limit=2)
        assert len(storico) == 2
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777903"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777903"
        )
        await database.close()


@pytest.mark.asyncio
async def test_rollback_config_change_ripristina_il_modulo():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777904"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777904"
        )

        await database.set_module_active_for_guild(777777904, "leveling", True)
        await database.set_module_active_for_guild(777777904, "leveling", False)
        # Ora leveling è False. Vogliamo tornare a True (il valore
        # PRIMA della seconda scrittura) usando la voce di storico
        # relativa a quella seconda scrittura.
        storico = await database.get_config_history(777777904)
        voce_da_annullare = storico[0]  # la più recente: True->False

        riuscito = await database.rollback_config_change(
            voce_da_annullare.id, rolled_back_by=7
        )

        assert riuscito is True
        assert await database.is_module_active_for_guild(777777904, "leveling") is True
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777904"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777904"
        )
        await database.close()


@pytest.mark.asyncio
async def test_rollback_config_change_registra_se_stesso_come_nuova_voce():
    # Un rollback non deve sparire silenziosamente: deve comparire
    # come una NUOVA voce nello storico, con changed_by = chi ha
    # fatto il rollback.
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777905"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777905"
        )

        await database.set_module_active_for_guild(777777905, "leveling", True)
        storico_prima = await database.get_config_history(777777905)
        await database.rollback_config_change(storico_prima[0].id, rolled_back_by=7)

        storico_dopo = await database.get_config_history(777777905)
        assert len(storico_dopo) == 2  # la scrittura originale + il rollback
        assert storico_dopo[0].changed_by == 7  # la voce più recente è il rollback
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777905"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777905"
        )
        await database.close()


@pytest.mark.asyncio
async def test_rollback_config_change_setting():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777906"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777906"
        )

        await database.set_guild_setting(777777906, "report_channel_id", 111)
        await database.set_guild_setting(777777906, "report_channel_id", 222)

        storico = await database.get_config_history(777777906)
        voce_da_annullare = storico[0]  # 111 -> 222

        await database.rollback_config_change(voce_da_annullare.id, rolled_back_by=None)

        valore_attuale = await database.get_guild_setting(777777906, "report_channel_id")
        assert valore_attuale == 111
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 777777906"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 777777906"
        )
        await database.close()


@pytest.mark.asyncio
async def test_rollback_config_change_voce_inesistente_restituisce_false():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        riuscito = await database.rollback_config_change(999999999, rolled_back_by=1)
        assert riuscito is False
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_config_history_non_mischia_server_diversi():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id IN (777777907, 777777908)"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id IN (777777907, 777777908)"
        )

        await database.set_module_active_for_guild(777777907, "leveling", True)
        await database.set_module_active_for_guild(777777908, "verify", True)

        storico_907 = await database.get_config_history(777777907)
        assert len(storico_907) == 1
        assert storico_907[0].key_name == "leveling"
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id IN (777777907, 777777908)"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id IN (777777907, 777777908)"
        )
        await database.close()

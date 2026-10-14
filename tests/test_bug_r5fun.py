"""Correzioni del giro cacciatore-bug su feat/r5-fun (alert live, statistiche NF-25)."""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord

from cogs.utility.activity_stats import ActivityStatsCog
from core.alert_options_logic import AlertOptions
from core.live_alert_flow import pubblica_cambio_live
from core.repositories.activity_stats_repo import ActivityStatsRepository
from core.repositories.alert_options_repo import AlertOptionsRepository
from core.repositories.kick_subscription_repo import KickSubscriptionRepository
from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

G = 720001


# --- minuti in vocale: si somma prima, si divide dopo ---------------------
async def test_minuti_vocale_non_perdono_i_secondi_di_ogni_giorno(clean_db):
    repo = ActivityStatsRepository(lambda: clean_db)
    giorni = [date(2026, 10, d) for d in (1, 2, 3)]
    await repo.flush({}, {(G, d, 5): [0, 50] for d in giorni}, {})  # 3 x 50 s = 150 s = 2 minuti
    assert await repo.member_total(G, 5, giorni[0], "voice_minutes") == 2
    assert await repo.top_members(G, giorni[0], "voice_minutes", 5) == [(5, 2)]
    assert await repo.members_over(G, giorni[0], "voice_minutes", 2) == {5}


# --- ruolo per attività: gerarchia di chi lo configura ---------------------
async def test_regola_attivita_rifiuta_ruolo_sopra_chi_la_crea(clean_db, monkeypatch):
    cog = ActivityStatsCog(MagicMock(), repo=ActivityStatsRepository(lambda: clean_db))
    from core.database import db
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    await db.set_module_active_for_guild(G, "server_stats", True)
    guild = fake_guild(G, owner_id=1)
    guild.me.top_role = fake_role(9, position=50)
    utente = fake_member(2, roles=[fake_role(10, position=5)])
    it = fake_interaction(guild=guild, user=utente)

    class _C:
        value = "messages"

    await cog.ruolo_aggiungi.callback(cog, it, fake_role(300, position=7), _C(), 5, 7, True)
    assert "uguale o superiore" in it.response.send_message.await_args.args[0]
    assert await cog._repo.list_rules(G) == []
    await cog.ruolo_aggiungi.callback(cog, it, fake_role(301, position=3), _C(), 5, 7, True)
    assert len(await cog._repo.list_rules(G)) == 1


# --- vocale ripresa al riavvio: rispetta esclusioni e modulo ----------------
async def test_riprendi_vocali_salta_canali_e_ruoli_esclusi(clean_db, monkeypatch):
    import core.database as dm
    from core.database import db

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, "server_stats", True)
    repo = ActivityStatsRepository(lambda: clean_db)
    await repo.toggle_ignored_channel(G, 61)
    await repo.toggle_ignored_role(G, 77)
    bot = MagicMock()
    guild = fake_guild(G)
    guild.afk_channel = None
    c_ok, c_escluso = MagicMock(id=60), MagicMock(id=61)
    c_ok.members = [fake_member(1), fake_member(2, roles=[fake_role(77)])]
    c_escluso.members = [fake_member(3)]
    guild.voice_channels = [c_ok, c_escluso]
    bot.guilds = [guild]
    cog = ActivityStatsCog(bot, repo=repo)
    await cog._riprendi_vocali()
    assert len(cog._voce) == 1


# --- classifica canali: niente canali che chi guarda non può aprire ---------
async def test_classifica_canali_nasconde_i_privati(monkeypatch, clean_db):
    import cogs.utility.server_stats as ss

    repo = ActivityStatsRepository(lambda: clean_db)
    monkeypatch.setattr(ss, "activity_stats_repo", repo)
    oggi = datetime.now(timezone.utc).date()
    await repo.flush({(G, oggi, 40): [9, 0], (G, oggi, 41): [5, 0]}, {}, {})
    g = fake_guild(G)
    visto = fake_member(7)

    def canale(vis):
        c = MagicMock()
        c.permissions_for.return_value = MagicMock(view_channel=vis)
        return c

    g.get_channel = lambda cid: canale(cid != 40)
    emb, _ = await ss.costruisci_statistiche(g, "canali", 7, visti_da=visto)
    assert "<#40>" not in emb.description and "<#41>" in emb.description


# --- avvisi: ruolo «in diretta» e riga delle opzioni ------------------------
async def test_ruolo_live_resta_se_il_membro_e_ancora_in_diretta_altrove(clean_db):
    opz_repo = AlertOptionsRepository(lambda: clean_db)
    tw = TwitchSubscriptionRepository(lambda: clean_db)
    kk = KickSubscriptionRepository(lambda: clean_db)
    t = await tw.add_subscription(G, 1, "a", "A", 1)
    k = await kk.add_subscription(G, 1, "a", "A", 1)
    await opz_repo.set_fields("TW", t, G, live_member_id=5)
    await opz_repo.set_fields("KK", k, G, live_member_id=5)
    assert not await opz_repo.other_live_for_member(G, 5, "TW", t)
    await kk.update_last_known_live(k, True)
    assert await opz_repo.other_live_for_member(G, 5, "TW", t)
    assert not await opz_repo.other_live_for_member(G, 5, "KK", k)
    assert not await opz_repo.other_live_for_member(G, 6, "TW", t)


async def test_fine_diretta_non_toglie_il_ruolo_se_c_e_un_altro_avviso_live(monkeypatch):
    import core.live_alert_flow as f

    repo_opz = MagicMock()
    repo_opz.other_live_for_member = AsyncMock(return_value=True)
    repo_opz.set_last_message = AsyncMock()
    monkeypatch.setattr(f, "alert_options_repo", repo_opz)
    ruolo_fn = AsyncMock()
    monkeypatch.setattr(f, "aggiorna_ruolo_live", ruolo_fn)
    monkeypatch.setattr(f, "avviso_fine", AsyncMock())
    canale = fake_text_channel(1)
    canale.__class__ = discord.TextChannel
    guild = MagicMock()
    guild.get_channel.return_value = canale
    bot = MagicMock()
    bot.get_guild.return_value = guild
    sub = MagicMock(id=3, guild_id=G, channel_id=1)
    repo_stato = MagicMock(update_last_known_live=AsyncMock())
    await pubblica_cambio_live(
        bot, sub, "TW", in_diretta=False, testo="x", url=None, opz=AlertOptions(live_member_id=5),
        ruolo_live_id=9, repo_stato=repo_stato, avvisi=MagicMock(), nome="Twitch",
    )
    repo_stato.update_last_known_live.assert_awaited_once()
    ruolo_fn.assert_not_awaited()


async def test_ultimo_messaggio_non_ricrea_le_opzioni_di_un_avviso_rimosso(clean_db):
    repo = AlertOptionsRepository(lambda: clean_db)
    await repo.set_fields("TW", 9, G, delete_on_end=True)
    await repo.delete("TW", 9, G)
    await repo.set_last_message("TW", 9, G, 123)
    assert await clean_db.fetchval("SELECT count(*) FROM alert_options WHERE sub_id = 9") == 0
    await repo.set_fields("TW", 8, G, delete_on_end=True)
    await repo.set_last_message("TW", 8, G, 123)
    assert (await repo.get("TW", 8)).last_message_id == 123


# --- revisore-capo: ruoli per attività, a rotazione ---------------------------
def test_ruoli_da_aggiornare_ruota_la_finestra():
    from core.activity_stats_logic import ruoli_da_aggiornare

    eleggibili = set(range(1, 61))
    visti: set[int] = set()
    for giro in range(3):
        dare, _ = ruoli_da_aggiornare(eleggibili, set(), True, limite=25, giro=giro)
        assert len(dare) == 25
        visti |= dare
    assert visti == eleggibili  # senza rotazione sarebbero sempre gli stessi 25
    # sotto il limite si prende tutto, qualunque sia il giro
    assert ruoli_da_aggiornare({1, 2}, set(), True, limite=25, giro=7)[0] == {1, 2}


async def test_aggiorna_ruoli_non_resta_bloccato_sui_primi_25():
    guild = fake_guild(G)
    ruolo = fake_role(10, position=1)
    guild.me.top_role = fake_role(99, position=50)
    guild.me.guild_permissions = discord.Permissions(manage_roles=True)
    guild.get_role = MagicMock(return_value=ruolo)
    ruolo.members = []
    membri = {u: MagicMock(id=u, bot=False, add_roles=AsyncMock(), remove_roles=AsyncMock()) for u in range(1, 61)}
    guild.get_member = MagicMock(side_effect=membri.get)
    repo = MagicMock()
    repo.members_over = AsyncMock(return_value=set(membri))
    regola = MagicMock(role_id=10, period_days=7, metric="messages", threshold=1, remove_when_below=True)
    cog = ActivityStatsCog(MagicMock(), repo=repo)
    import asyncio
    from unittest.mock import patch

    with patch.object(asyncio, "sleep", AsyncMock()):
        for _ in range(3):
            cog._giro_ruoli += 1
            await cog._applica_regola(guild, regola)
    # i ruoli non risultano mai posseduti (finto): ogni giro ne prova 25 diversi
    chiamati = {u for u, m in membri.items() if m.add_roles.await_count}
    assert len(chiamati) == 60


# --- revisore-capo: invio fallito = un solo warning e attese crescenti ------------
async def _cambio_con_invio_fallito(monkeypatch, sub_id=4):
    import core.live_alert_flow as f

    repo_opz = MagicMock(other_live_for_member=AsyncMock(return_value=False), set_last_message=AsyncMock())
    monkeypatch.setattr(f, "alert_options_repo", repo_opz)
    monkeypatch.setattr(f, "aggiorna_ruolo_live", AsyncMock())
    avviso = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500, reason="x"), "x"))
    monkeypatch.setattr(f, "avviso_live", avviso)
    canale = fake_text_channel(1)
    canale.__class__ = discord.TextChannel
    guild = MagicMock()
    guild.get_channel.return_value = canale
    bot = MagicMock()
    bot.get_guild.return_value = guild
    sub = MagicMock(id=sub_id, guild_id=G, channel_id=1)
    repo_stato = MagicMock(update_last_known_live=AsyncMock())

    async def giro():
        await pubblica_cambio_live(
            bot, sub, "TW", in_diretta=True, testo="x", url=None, opz=AlertOptions(),
            ruolo_live_id=None, repo_stato=repo_stato, avvisi=MagicMock(), nome="Twitch",
        )

    return giro, avviso, repo_stato


async def test_invio_fallito_logga_una_volta_e_aspetta(monkeypatch, caplog):
    import core.live_alert_flow as f

    giro, avviso, repo_stato = await _cambio_con_invio_fallito(monkeypatch)
    ora = [1000.0]
    monkeypatch.setattr(f.time, "monotonic", lambda: ora[0])
    with caplog.at_level("WARNING", logger="iyokai.live_alert_flow"):
        await giro()
        assert avviso.await_count == 1
        await giro()  # ancora in attesa: nemmeno un tentativo
        assert avviso.await_count == 1
        ora[0] += f.ATTESA_BASE_SECONDI + 1
        await giro()
        assert avviso.await_count == 2
        ora[0] += f.ATTESA_BASE_SECONDI + 1  # l'attesa è raddoppiata: troppo presto
        await giro()
        assert avviso.await_count == 2
        ora[0] += 10 * f.ATTESA_MASSIMA_SECONDI
        await giro()
        assert avviso.await_count == 3
    assert len([r for r in caplog.records if "Impossibile pubblicare" in r.message]) == 1
    repo_stato.update_last_known_live.assert_not_awaited()


async def test_invio_riuscito_azzera_l_attesa(monkeypatch):
    import core.live_alert_flow as f

    giro, avviso, repo_stato = await _cambio_con_invio_fallito(monkeypatch, sub_id=5)
    ora = [1000.0]
    monkeypatch.setattr(f.time, "monotonic", lambda: ora[0])
    await giro()
    avviso.side_effect = None
    avviso.return_value = 77
    ora[0] += f.ATTESA_BASE_SECONDI + 1
    await giro()
    repo_stato.update_last_known_live.assert_awaited_once()
    assert ("TW", 5) not in f._FALLITI

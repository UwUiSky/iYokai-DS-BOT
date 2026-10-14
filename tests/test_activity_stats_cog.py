"""NF-25 (#96): cog di raccolta, ruoli per attività, comandi /moduli statistiche e viste di /utility serverstats."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from cogs.utility.activity_stats import MODULE_SERVER_STATS, ActivityStatsCog
from core.database import db
from core.repositories.activity_stats_repo import ActivityStatsRepository
from tests.support.discord_fakes import (
    fake_guild, fake_interaction, fake_member, fake_message, fake_role, fake_text_channel,
)
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

GID = 710001


class _Ch:
    def __init__(self, value):
        self.value = value


@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(GID, MODULE_SERVER_STATS, True)
    yield
    dm.db._modules_cache.clear()


@pytest.fixture
def cog(clean_db):
    bot = MagicMock()
    bot.guilds = []
    return ActivityStatsCog(bot, repo=ActivityStatsRepository(lambda: clean_db))


def _msg(autore=None, canale=None, guild=None):
    m = fake_message(author=autore or fake_member(5), channel=canale or fake_text_channel(40), guild=guild or fake_guild(GID))
    m.webhook_id = None
    m.type = discord.MessageType.default
    return m


async def _totali(cog, uid=5):
    await cog.scrivi_lotto()
    return await cog._repo.member_total(GID, uid, datetime(2020, 1, 1).date(), "messages")


async def test_conta_un_messaggio_e_scrive_a_lotto(cog):
    await cog.on_message(_msg())
    await cog.on_message(_msg())
    assert await _totali(cog) == 2


async def test_ignora_bot_webhook_sistema_dm_e_modulo_spento(cog):
    await cog.on_message(_msg(autore=fake_member(5, bot=True)))
    w = _msg(); w.webhook_id = 1
    await cog.on_message(w)
    s = _msg(); s.type = discord.MessageType.new_member
    await cog.on_message(s)
    d = _msg(); d.guild = None
    await cog.on_message(d)
    await db.set_module_active_for_guild(GID, MODULE_SERVER_STATS, False)
    await cog.on_message(_msg())
    assert await _totali(cog) == 0


async def test_canale_e_ruolo_esclusi(cog):
    await cog._repo.toggle_ignored_channel(GID, 40)
    await cog._repo.toggle_ignored_role(GID, 77)
    await cog.on_message(_msg())
    await cog.on_message(_msg(autore=fake_member(5, roles=[fake_role(77)]), canale=fake_text_channel(41)))
    assert await _totali(cog) == 0


async def test_lotto_non_scritto_viene_rimesso_in_coda(cog):
    cog._repo = MagicMock(flush=AsyncMock(side_effect=RuntimeError("db giù")), get_settings=cog._repo.get_settings)
    await cog.on_message(_msg())
    await cog.scrivi_lotto()
    assert cog._ultimo_errore == "RuntimeError"
    cog._repo.flush = AsyncMock()
    await cog.scrivi_lotto()
    canali, membri, ore = cog._repo.flush.await_args.args
    assert sum(v[0] for v in membri.values()) == 1


async def test_vocale_accredita_alla_uscita_e_salta_afk(cog):
    g = fake_guild(GID)
    afk = MagicMock(); afk.id = 90
    g.afk_channel = afk
    canale = MagicMock(); canale.id = 91
    m = fake_member(6); m.guild = g; m.roles = []
    prima = MagicMock(channel=None); dopo = MagicMock(channel=canale)
    await cog.on_voice_state_update(m, prima, dopo)
    assert len(cog._voce) == 1
    cog._voce._sessioni[(GID, 6)][1] = datetime(2026, 1, 1, tzinfo=timezone.utc)
    await cog.on_voice_state_update(m, MagicMock(channel=canale), MagicMock(channel=None))
    await cog.scrivi_lotto()
    assert await cog._repo.member_total(GID, 6, datetime(2020, 1, 1).date(), "voice_minutes") == 1440  # tetto 1 giorno
    await cog.on_voice_state_update(m, MagicMock(channel=None), MagicMock(channel=afk))
    assert len(cog._voce) == 0


async def test_ruoli_per_attivita_danno_e_tolgono(cog, monkeypatch):
    me = fake_member(999, roles=[fake_role(9, position=10)], guild_permissions=discord.Permissions(manage_roles=True), bot=True)
    g = fake_guild(GID, me=me)
    ruolo = fake_role(300, position=2)
    vecchio = fake_member(8); vecchio.add_roles = AsyncMock(); vecchio.remove_roles = AsyncMock()
    nuovo = fake_member(5); nuovo.add_roles = AsyncMock(); nuovo.remove_roles = AsyncMock()
    ruolo.members = [vecchio]
    g.get_role = MagicMock(return_value=ruolo)
    g.get_member = MagicMock(side_effect=lambda u: {5: nuovo, 8: vecchio}.get(u))
    cog.bot.get_guild = MagicMock(return_value=g)
    for _ in range(3):
        await cog.on_message(_msg(guild=g))
    await cog.scrivi_lotto()
    await cog._repo.add_rule(GID, 300, "messages", 3, 7, True)
    import cogs.utility.activity_stats as m
    monkeypatch.setattr(m.asyncio, "sleep", AsyncMock())
    await cog.aggiorna_ruoli()
    nuovo.add_roles.assert_awaited_once()
    vecchio.remove_roles.assert_awaited_once()


async def test_ruolo_sopra_il_bot_non_si_tocca(cog):
    g = fake_guild(GID)  # me ha top_role in posizione 0
    ruolo = fake_role(300, position=5); ruolo.members = []
    g.get_role = MagicMock(return_value=ruolo)
    cog.bot.get_guild = MagicMock(return_value=g)
    await cog._repo.add_rule(GID, 300, "messages", 1, 7, True)
    await cog._repo.flush({}, {(GID, datetime.now(timezone.utc).date(), 5): [9, 0]}, {})
    g.get_member = MagicMock()
    await cog.aggiorna_ruoli()
    g.get_member.assert_not_called()


async def test_comandi_regola_e_diagnosi(cog):
    it = fake_interaction(guild=fake_guild(GID))
    it.guild.me.top_role = fake_role(9, position=10)
    await cog.ruolo_aggiungi.callback(cog, it, fake_role(300, position=2), _Ch("messages"), 50, 7, True)
    assert "Regola salvata" in it.response.send_message.await_args.args[0]
    assert len(await cog._repo.list_rules(GID)) == 1
    it = fake_interaction(guild=fake_guild(GID))
    await cog.elenco.callback(cog, it)
    assert "50 messaggi" in it.response.send_message.await_args.kwargs["embed"].description
    it = fake_interaction(guild=fake_guild(GID))
    await cog.diagnosi.callback(cog, it)
    testo = it.response.send_message.await_args.args[0]
    assert "Modulo Server Stats attivo" in testo and "Messaggi contati" in testo
    it = fake_interaction(guild=fake_guild(GID))
    await cog.ruolo_elimina.callback(cog, it, 999999)
    assert it.response.send_message.await_args.args[0] == "Non trovo questa regola."


async def test_modulo_spento_nei_comandi(cog):
    await db.set_module_active_for_guild(GID, MODULE_SERVER_STATS, False)
    it = fake_interaction(guild=fake_guild(GID))
    await cog.diagnosi.callback(cog, it)
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_albero_e_limiti():
    import cogs.utility.activity_stats as a, cogs.utility.server_stats as s
    from core.command_groups import GRUPPI
    from tests.test_command_tree_invariants import conta_caratteri

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    bot.wait_until_ready = AsyncMock()
    await bot.add_cog(a.ActivityStatsCog(bot))
    await s.setup(bot)
    assert {"statistiche impostazioni", "statistiche ruolo-aggiungi", "statistiche ruolo-elimina",
            "statistiche elenco", "statistiche diagnosi"} <= percorsi_del_gruppo("moduli")
    assert conta_caratteri(GRUPPI["moduli"]) < 6800
    vista = {o.name: o for o in comando_nel_gruppo("utility", "serverstats").parameters}["vista"]
    assert len(vista.choices) <= 25
    await bot.remove_cog("ActivityStatsCog")


# --- /utility serverstats: viste ---------------------------------------

async def test_serverstats_viste_di_attivita(cog, monkeypatch):
    import cogs.utility.server_stats as ss

    monkeypatch.setattr(ss, "activity_stats_repo", cog._repo)
    g = fake_guild(GID)
    g.member_count = 3
    ruolo = fake_role(300); ruolo.members = [fake_member(5)]
    await cog.on_message(_msg(guild=g)); await cog.on_message(_msg(autore=fake_member(6), guild=g))
    await cog.scrivi_lotto()
    emb, file = await ss.costruisci_statistiche(g, "canali", 7)
    assert "<#40>" in emb.description and file is None
    emb, _ = await ss.costruisci_statistiche(g, "membri", 7, ruolo=ruolo)
    assert "<@5>" in emb.description and "<@6>" not in emb.description
    emb, file = await ss.costruisci_statistiche(g, "ore", 7)
    assert file is not None and file.filename == "statistiche.png"
    emb, file = await ss.costruisci_statistiche(g, "giorni-settimana", 7)
    assert file is not None
    emb, _ = await ss.costruisci_statistiche(g, "membro", 7, utente=fake_member(5))
    assert "**1** messaggi" in emb.description


async def test_bottoni_periodo_solo_per_l_autore(cog, monkeypatch):
    import cogs.utility.server_stats as ss

    monkeypatch.setattr(ss, "activity_stats_repo", cog._repo)
    view = ss._PeriodoView(5, fake_guild(GID), "canali", 14, "messages", None, None)
    assert len(view.children) == 4
    it = fake_interaction(guild=fake_guild(GID), user=fake_member(77))
    await view.children[0].callback(it)
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True
    it = fake_interaction(guild=fake_guild(GID), user=fake_member(5))
    await view.children[1].callback(it)
    it.edit_original_response.assert_awaited_once()


async def test_serverstats_ingressi_e_uscite_separati(monkeypatch):
    import types
    import cogs.utility.server_stats as ss

    oggi = datetime.now(timezone.utc)

    async def _eventi(guild_id, tipo, since):
        return [types.SimpleNamespace(created_at=oggi)] * (3 if tipo == "member_join" else 1)

    monkeypatch.setattr(ss, "event_log_repo", types.SimpleNamespace(get_events_by_type_since=_eventi))
    seen = {}
    monkeypatch.setattr(ss, "render_growth_chart", lambda serie, titolo: seen.setdefault(titolo, dict(serie)) and b"\x89PNG")
    g = fake_guild(GID)
    g.member_count = 1
    for vista, atteso in (("ingressi", 3), ("uscite", -1)):
        await ss.costruisci_statistiche(g, vista, 3)
        serie = next(v for k, v in seen.items() if k.startswith(ss.VISTE[vista]))
        assert serie[oggi.date()] == atteso

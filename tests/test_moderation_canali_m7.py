"""
tests/test_moderation_canali_m7.py
==================================
Canali, nomi e nuovi arrivati, blocco M7 (#115): slowmode su una categoria (MOD-098), slowmode lungo gestito dal
bot (MOD-099), elenco dei canali con slowmode (MOD-100), cambio nickname (MOD-101), ban o kick di chi è entrato
da poco (MOD-007). Database vero.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation import channel_control as cc
from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CHANNEL_CONTROL, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.channel_control import ModerationChannelControlCog
from cogs.moderation.nickname import ModerationNicknameCog
from core import moderazione_canali_logic as logica
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel
from tests.test_moderation_ordine_azione import ID_CANALE_LOG, ID_SERVER, Scena

G = ID_SERVER


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_CHANNEL_CONTROL, True)
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    await db.set_guild_setting(G, SETTING_MOD_LOG_CHANNEL, ID_CANALE_LOG)
    monkeypatch.setattr("cogs.moderation.actions.PAUSA_ENTRATI", 0, raising=False)
    monkeypatch.setattr(cc, "PAUSA_CANALI", 0)
    yield
    database_module.db._modules_cache.clear()


def _canale(cid, slow=0):
    c = fake_text_channel(cid, f"c{cid}")
    c.slowmode_delay = slow
    c.mention = f"<#{cid}>"
    c.edit = AsyncMock()
    return c


def _testo(scena):
    c = scena.interazione.response.send_message.call_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


# --- logica ---

@pytest.mark.parametrize("testo,secondi", [("7h", 7 * 3600), ("2d", 2 * 86400), ("7d", 7 * 86400)])
def test_slowmode_lungo_valido(testo, secondi):
    assert logica.secondi_slowmode_lungo(testo) == secondi


@pytest.mark.parametrize("testo", ["5h", "6h", "8d", "abc", "0"])
def test_slowmode_lungo_fuori_dai_limiti(testo):
    with pytest.raises(ValueError):
        logica.secondi_slowmode_lungo(testo)


def test_il_messaggio_arrivato_troppo_presto_si_cancella():
    ora = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    assert logica.deve_cancellare(ora - timedelta(hours=2), ora, 7 * 3600) is True
    assert logica.deve_cancellare(ora - timedelta(hours=8), ora, 7 * 3600) is False
    assert logica.deve_cancellare(None, ora, 7 * 3600) is False


def test_avviso_al_massimo_ogni_10_minuti():
    assert logica.puo_avvisare(None, 1000.0) is True
    assert logica.puo_avvisare(1000.0, 1000.0 + 599) is False
    assert logica.puo_avvisare(1000.0, 1000.0 + 600) is True


def test_canali_della_categoria_hanno_un_tetto_di_50():
    cat = SimpleNamespace(text_channels=[object() for _ in range(70)])
    assert len(logica.canali_della_categoria(cat)) == logica.MAX_CANALI_CATEGORIA == 50


def test_nickname_valido():
    assert logica.nickname_valido("Mario") is True
    assert logica.nickname_valido("") is False
    assert logica.nickname_valido("x" * 33) is False


def test_entrati_scelti_per_tempo_e_tetto():
    ora = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    membri = [SimpleNamespace(id=i, joined_at=ora - timedelta(minutes=i)) for i in range(1, 300)]
    membri.append(SimpleNamespace(id=999, joined_at=None))
    scelti, restano = logica.entrati_da_poco(membri, 250, ora)
    assert len(scelti) == 200 and restano == 50
    assert scelti[0].id == 1  # i più recenti per primi
    scelti2, restano2 = logica.entrati_da_poco(membri, 10, ora)
    assert [m.id for m in scelti2] == list(range(1, 11)) and restano2 == 0


# --- repo ---

async def test_slowmode_lungo_nel_db():
    await moderation_repo.set_slowmode_lungo(G, 5, 8 * 3600)
    await moderation_repo.set_slowmode_lungo(G, 5, 9 * 3600)
    assert await moderation_repo.list_slowmode_lungo(G) == [(5, 9 * 3600)]
    ora = datetime.now(timezone.utc)
    await moderation_repo.set_slowmode_ultimo(G, 5, 20, ora)
    assert (await moderation_repo.get_slowmode_ultimo(G, 5, 20)) is not None
    await moderation_repo.delete_slowmode_lungo(G, 5)
    assert await moderation_repo.list_slowmode_lungo(G) == []
    assert await moderation_repo.get_slowmode_ultimo(G, 5, 20) is None


# --- slowmode ---

def _scena_canali():
    scena = Scena()
    scena.moderatore.guild_permissions = discord.Permissions(moderate_members=True)
    return scena


async def test_slowmode_su_una_categoria_cambia_tutti_i_canali():
    scena = _scena_canali()
    canali = [_canale(i) for i in range(1, 4)]
    cat = SimpleNamespace(text_channels=canali, mention="cat", name="cat")
    cog = ModerationChannelControlCog(bot=None)
    await cog.slowmode.callback(cog, scena.interazione, 30, None, cat)
    for c in canali:
        assert c.edit.await_args.kwargs["slowmode_delay"] == 30


async def test_slowmode_lungo_imposta_il_massimo_nativo_e_salva():
    scena = _scena_canali()
    canale = _canale(77)
    scena.interazione.channel = canale
    cog = ModerationChannelControlCog(bot=None)
    await cog.slowmode.callback(cog, scena.interazione, None, canale, None, "2d")
    assert canale.edit.await_args.kwargs["slowmode_delay"] == 21600
    assert await moderation_repo.list_slowmode_lungo(G) == [(77, 2 * 86400)]


async def test_slowmode_lungo_troppo_corto_e_rifiutato():
    scena = _scena_canali()
    canale = _canale(77)
    cog = ModerationChannelControlCog(bot=None)
    await cog.slowmode.callback(cog, scena.interazione, None, canale, None, "3h")
    canale.edit.assert_not_called()
    assert await moderation_repo.list_slowmode_lungo(G) == []


async def test_slowmode_normale_toglie_il_lungo():
    scena = _scena_canali()
    canale = _canale(77)
    await moderation_repo.set_slowmode_lungo(G, 77, 86400)
    cog = ModerationChannelControlCog(bot=None)
    await cog.slowmode.callback(cog, scena.interazione, 0, canale)
    assert await moderation_repo.list_slowmode_lungo(G) == []


async def test_slowmode_senza_valori_mostra_l_elenco():
    scena = _scena_canali()
    scena.server.text_channels = [_canale(1, 10), _canale(2, 0)]
    await moderation_repo.set_slowmode_lungo(G, 9, 86400)
    scena.server.get_channel = MagicMock(side_effect=lambda cid: _canale(cid) if cid == 9 else None)
    cog = ModerationChannelControlCog(bot=None)
    await cog.slowmode.callback(cog, scena.interazione, None)
    testo = scena.interazione.response.send_message.call_args.kwargs["embed"].description
    assert "<#1>" in testo and "<#9>" in testo and "<#2>" not in testo


def _messaggio(canale, utente, staff=False):
    m = MagicMock(spec=discord.Message)
    m.guild = SimpleNamespace(id=G)
    m.channel = canale
    m.author = fake_member(utente, guild_permissions=discord.Permissions(manage_messages=staff))
    m.author.send = AsyncMock()
    m.delete = AsyncMock()
    m.created_at = datetime.now(timezone.utc)
    return m


async def test_il_bot_cancella_il_secondo_messaggio_troppo_presto():
    cog = ModerationChannelControlCog(bot=None)
    canale = _canale(77)
    await moderation_repo.set_slowmode_lungo(G, 77, 8 * 3600)
    primo = _messaggio(canale, 20)
    await cog.on_message(primo)
    primo.delete.assert_not_called()
    secondo = _messaggio(canale, 20)
    await cog.on_message(secondo)
    secondo.delete.assert_awaited_once()
    secondo.author.send.assert_awaited_once()
    terzo = _messaggio(canale, 20)
    await cog.on_message(terzo)
    terzo.delete.assert_awaited_once()
    terzo.author.send.assert_not_called()  # un solo avviso ogni 10 minuti


async def test_lo_staff_e_i_bot_non_sono_limitati():
    cog = ModerationChannelControlCog(bot=None)
    canale = _canale(77)
    await moderation_repo.set_slowmode_lungo(G, 77, 8 * 3600)
    for _ in range(2):
        m = _messaggio(canale, 30, staff=True)
        await cog.on_message(m)
        m.delete.assert_not_called()


async def test_canale_cancellato_esce_dallo_slowmode_lungo():
    """Un canale cancellato non resta nel tetto dei 50 né nell'elenco (non si potrebbe più togliere)."""
    cog = ModerationChannelControlCog(bot=None)
    canale = _canale(77)
    canale.guild = SimpleNamespace(id=G)
    await moderation_repo.set_slowmode_lungo(G, 77, 8 * 3600)
    await cog.on_message(_messaggio(canale, 20))
    assert 77 in cog._lungo
    await cog.on_guild_channel_delete(canale)
    assert await moderation_repo.list_slowmode_lungo(G) == []
    assert 77 not in cog._lungo
    assert await moderation_repo.get_slowmode_ultimo(G, 77, 20) is None


async def test_canali_senza_slowmode_lungo_non_toccano_il_db(monkeypatch):
    cog = ModerationChannelControlCog(bot=None)
    canale = _canale(5)
    m = _messaggio(canale, 20)
    await cog.on_message(m)
    m.delete.assert_not_called()
    assert await db._pool.fetchval("SELECT count(*) FROM moderation_slowmode_ultimi") == 0


# --- nickname ---

async def test_nick_cambia_il_nome():
    scena = _scena_canali()
    scena.moderatore.guild_permissions = discord.Permissions(manage_nicknames=True)
    scena.server.me.guild_permissions = discord.Permissions(manage_nicknames=True)
    scena.bersaglio.edit = AsyncMock()
    cog = ModerationNicknameCog(bot=None)
    await cog.nick.callback(cog, scena.interazione, scena.bersaglio, "Nome Nuovo")
    assert scena.bersaglio.edit.await_args.kwargs["nick"] == "Nome Nuovo"


async def test_nick_vuoto_azzera():
    scena = _scena_canali()
    scena.moderatore.guild_permissions = discord.Permissions(manage_nicknames=True)
    scena.server.me.guild_permissions = discord.Permissions(manage_nicknames=True)
    scena.bersaglio.edit = AsyncMock()
    cog = ModerationNicknameCog(bot=None)
    await cog.nick.callback(cog, scena.interazione, scena.bersaglio, None)
    assert scena.bersaglio.edit.await_args.kwargs["nick"] is None


async def test_nick_senza_permesso_non_cambia():
    scena = _scena_canali()
    scena.bersaglio.edit = AsyncMock()
    cog = ModerationNicknameCog(bot=None)
    await cog.nick.callback(cog, scena.interazione, scena.bersaglio, "X")
    scena.bersaglio.edit.assert_not_called()


# --- entrati da poco ---

def _entrati(scena, n, minuti_fa=lambda i: i):
    ora = datetime.now(timezone.utc)
    membri = []
    for i in range(1, n + 1):
        m = fake_member(1000 + i, roles=[fake_role(role_id=2, position=5)])
        m.guild = scena.server
        m.joined_at = ora - timedelta(minutes=minuti_fa(i))
        m.ban = AsyncMock()
        m.kick = AsyncMock()
        m.send = AsyncMock()
        membri.append(m)
    scena.server.members = membri
    per_id = {m.id: m for m in [*membri, scena.moderatore]}
    scena.server.get_member = MagicMock(side_effect=per_id.get)
    permessi = discord.Permissions(ban_members=True, kick_members=True)
    scena.moderatore.guild_permissions = permessi
    scena.server.me.guild_permissions = permessi
    scena.server.bulk_ban = AsyncMock(side_effect=lambda ids, **kw: SimpleNamespace(banned=list(ids), failed=[]))
    return membri


async def test_entrati_mostra_il_numero_e_aspetta_la_conferma():
    scena = Scena()
    _entrati(scena, 5, lambda i: i)  # 1..5 minuti fa
    cog = ModerationActionsCog(bot=None)
    await cog.entrati.callback(cog, scena.interazione, 3, "ban", "raid in corso")
    kw = scena.interazione.response.send_message.call_args.kwargs
    assert kw["view"] is not None and kw["ephemeral"] is True
    assert "3" in scena.interazione.response.send_message.call_args.args[0]
    scena.server.bulk_ban.assert_not_called()


async def test_entrati_nessuno_non_chiede_conferma():
    scena = Scena()
    _entrati(scena, 3, lambda i: 500 + i)
    cog = ModerationActionsCog(bot=None)
    await cog.entrati.callback(cog, scena.interazione, 5, "ban", "raid in corso")
    assert scena.interazione.response.send_message.call_args.kwargs.get("view") is None


async def test_conferma_ban_usa_il_ban_in_blocco_e_crea_i_casi():
    scena = Scena()
    membri = _entrati(scena, 3)
    cog = ModerationActionsCog(bot=None)
    await cog.entrati.callback(cog, scena.interazione, 10, "ban", "raid in corso")
    vista = scena.interazione.response.send_message.call_args.kwargs["view"]
    conferma = fake_interaction(guild=scena.server, user=scena.moderatore)
    await vista.esegui(conferma)
    assert scena.server.bulk_ban.await_count == 1
    ids = [o.id for o in scena.server.bulk_ban.await_args.args[0]]
    assert sorted(ids) == sorted(m.id for m in membri)
    from core.repositories.moderation_repo import moderation_repo as repo

    assert len(await repo.list_cases_for_user(G, membri[0].id)) == 1


async def test_ban_uno_alla_volta_si_ferma_dopo_tre_403():
    """Se il ban in blocco è vietato si passa ai ban singoli: dopo tre 403 di fila ci si ferma (rischio blocco IP)."""
    scena = Scena()
    _entrati(scena, 6)
    risposta = MagicMock(status=403, reason="Forbidden")
    scena.server.bulk_ban = AsyncMock(side_effect=discord.Forbidden(risposta, "no"))
    scena.server.ban = AsyncMock(side_effect=discord.Forbidden(risposta, "no"))
    cog = ModerationActionsCog(bot=None)
    await cog.entrati.callback(cog, scena.interazione, 10, "ban", "raid in corso")
    vista = scena.interazione.response.send_message.call_args.kwargs["view"]
    await vista.esegui(fake_interaction(guild=scena.server, user=scena.moderatore))
    assert scena.server.ban.await_count == 3


async def test_conferma_kick_espelle_uno_per_uno():
    scena = Scena()
    membri = _entrati(scena, 3)
    cog = ModerationActionsCog(bot=None)
    await cog.entrati.callback(cog, scena.interazione, 10, "kick", "raid in corso")
    vista = scena.interazione.response.send_message.call_args.kwargs["view"]
    conferma = fake_interaction(guild=scena.server, user=scena.moderatore)
    await vista.esegui(conferma)
    for m in membri:
        m.kick.assert_awaited_once()
    scena.server.bulk_ban.assert_not_called()


async def test_solo_chi_ha_lanciato_il_comando_puo_confermare():
    scena = Scena()
    _entrati(scena, 2)
    cog = ModerationActionsCog(bot=None)
    await cog.entrati.callback(cog, scena.interazione, 10, "ban", "raid in corso")
    vista = scena.interazione.response.send_message.call_args.kwargs["view"]
    altro = fake_interaction(guild=scena.server, user=fake_member(77))
    assert await vista.interaction_check(altro) is False
    assert await vista.interaction_check(scena.interazione) is True

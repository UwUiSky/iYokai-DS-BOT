"""
tests/test_moderation_clear_filtri.py
=====================================
Filtri di /mod-canali clear (core/clear_filter_logic.py) e righe di log di
clear, lock, unlock, slowmode (M 1.8).
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import (
    MODULE_CHANNEL_CONTROL,
    MODULE_CLEAR,
    SETTING_MOD_LOG_CHANNEL,
)
from cogs.moderation.channel_control import ModerationChannelControlCog
from cogs.moderation.clear import ModerationClearCog
from core.clear_filter_logic import FiltriClear, messaggio_passa
from core.database import db
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)


def _msg(testo="", *, bot=False, allegati=(), embeds=(), menzioni=(), fissato=False, webhook=None, ruoli=()):
    m = MagicMock()
    m.content = testo
    m.author = MagicMock(id=5, bot=bot, roles=list(ruoli))
    m.attachments = list(allegati)
    m.embeds = list(embeds)
    m.mentions = list(menzioni)
    m.role_mentions = []
    m.pinned = fissato
    m.webhook_id = webhook
    return m


@pytest.mark.parametrize(
    "filtri,messaggio,atteso",
    [
        (FiltriClear(contiene="ciao"), _msg("Ciao a tutti"), True),
        (FiltriClear(contiene="ciao"), _msg("salve"), False),
        (FiltriClear(non_contiene="spam"), _msg("ok"), True),
        (FiltriClear(non_contiene="spam"), _msg("SPAM qui"), False),
        (FiltriClear(solo_link=True), _msg("guarda https://esempio.it/x"), True),
        (FiltriClear(solo_link=True), _msg("niente"), False),
        (FiltriClear(solo_inviti=True), _msg("vieni discord.gg/abc123"), True),
        (FiltriClear(solo_inviti=True), _msg("https://esempio.it"), False),
        (FiltriClear(solo_embed=True), _msg(embeds=[1]), True),
        (FiltriClear(solo_menzioni=True), _msg(menzioni=[1]), True),
        (FiltriClear(solo_menzioni=True), _msg("x"), False),
        (FiltriClear(solo_persone=True), _msg(bot=True), False),
        (FiltriClear(solo_persone=True), _msg(webhook=9), False),
        (FiltriClear(solo_bot=True), _msg(webhook=9), True),
        (FiltriClear(salta_fissati=True), _msg(fissato=True), False),
        (FiltriClear(ruolo_id=7), _msg(ruoli=[fake_role(role_id=7)]), True),
        (FiltriClear(ruolo_id=7), _msg(ruoli=[fake_role(role_id=8)]), False),
        (FiltriClear(autore_id=6), _msg("x"), False),
        (FiltriClear(contiene="a", solo_link=True), _msg("a senza link"), False),
    ],
)
def test_filtri(filtri, messaggio, atteso):
    assert messaggio_passa(messaggio, filtri) is atteso


ID_SERVER = 100
ID_LOG = 7001


@pytest.fixture
async def ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    for modulo in (MODULE_CLEAR, MODULE_CHANNEL_CONTROL):
        await db.set_module_active_for_guild(ID_SERVER, modulo, True)
    await db.set_guild_setting(ID_SERVER, SETTING_MOD_LOG_CHANNEL, ID_LOG)
    server = fake_guild(ID_SERVER)
    canale_log = fake_text_channel(ID_LOG, "mod-log")
    canale_log.send = AsyncMock()
    server.get_channel.return_value = canale_log
    mod = fake_member(10)
    canale = fake_text_channel(55, "generale")
    canale.purge = AsyncMock(return_value=[1, 2, 3])
    canale.set_permissions = AsyncMock()
    canale.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
    canale.edit = AsyncMock()
    inter = fake_interaction(guild=server, user=mod, channel=canale)
    yield inter, canale, canale_log
    database_module.db._modules_cache.clear()


async def test_clear_filtra_e_scrive_nel_log(ambiente):
    inter, canale, canale_log = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 50, contains="ciao", links_only=True)

    check = canale.purge.call_args.kwargs["check"]
    assert check(_msg("ciao https://a.it")) and not check(_msg("ciao"))
    embed = canale_log.send.call_args.kwargs["embed"]
    assert any("contiene" in f.value for f in embed.fields)


async def test_clear_in_un_altro_canale(ambiente):
    inter, canale, _ = ambiente
    altro = fake_text_channel(66, "altro")
    altro.purge = AsyncMock(return_value=[])
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, channel=altro)

    altro.purge.assert_awaited()
    canale.purge.assert_not_awaited()


async def test_clear_errore_http_non_esplode(ambiente):
    inter, canale, _ = ambiente
    canale.purge.side_effect = discord.HTTPException(MagicMock(status=500, reason="x"), "x")
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10)

    assert "Non sono riuscito" in inter.followup.send.call_args.args[0]


async def test_lock_unlock_slowmode_lasciano_una_riga_di_log(ambiente):
    inter, canale, canale_log = ambiente
    cog = ModerationChannelControlCog(bot=None)
    inter.guild.default_role = fake_role(role_id=ID_SERVER)

    await cog.lock.callback(cog, inter, None, "Pulizia in corso")
    await cog.unlock.callback(cog, inter, None)
    await cog.slowmode.callback(cog, inter, 10, None)

    assert canale_log.send.await_count == 3
    for chiamata in canale_log.send.call_args_list:
        assert any(f.name == "Moderatore" for f in chiamata.kwargs["embed"].fields)


async def test_clear_su_un_canale_senza_permesso_dell_utente_non_cancella(ambiente):
    inter, canale, _ = ambiente
    altro = fake_text_channel(66, "staff-privato")
    altro.purge = AsyncMock(return_value=[])
    altro.permissions_for = MagicMock(
        return_value=discord.Permissions(view_channel=False, manage_messages=True)
    )
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, channel=altro)

    altro.purge.assert_not_awaited()
    assert inter.response.send_message.call_args.kwargs["ephemeral"] is True
    altro.permissions_for.assert_called_with(inter.user)


def test_menzioni_di_ruolo_e_testo_in_minuscolo():
    con_ruolo = _msg("x")
    con_ruolo.role_mentions = [fake_role(role_id=3)]
    assert messaggio_passa(con_ruolo, FiltriClear(solo_menzioni=True))
    assert messaggio_passa(_msg("CIAO"), FiltriClear(contiene="ciao"))
    assert not messaggio_passa(_msg("CIAO"), FiltriClear(non_contiene="ciao"))


async def test_clear_bot_e_persone_insieme_non_cancella(ambiente):
    inter, canale, _ = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, bots_only=True, humans_only=True)

    canale.purge.assert_not_awaited()
    assert "insieme" in inter.response.send_message.call_args.args[0]


async def test_lock_con_errore_http_dice_che_non_puo(ambiente):
    inter, canale, canale_log = ambiente
    cog = ModerationChannelControlCog(bot=None)
    inter.guild.default_role = fake_role(role_id=ID_SERVER)
    canale.set_permissions.side_effect = discord.HTTPException(MagicMock(status=403, reason="x"), "x")

    await cog.lock.callback(cog, inter, None, None)

    assert "permessi" in inter.response.send_message.call_args.args[0]
    canale_log.send.assert_not_awaited()


async def test_clear_senza_gestire_messaggi_nel_canale_non_cancella(ambiente):
    inter, canale, _ = ambiente
    canale.permissions_for = MagicMock(
        return_value=discord.Permissions(view_channel=True, manage_messages=False)
    )
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10)

    canale.purge.assert_not_awaited()


# --- M1: filtri «tipo» e «modo» (MOD-070, 077, 079, 084, 085, 089) ---

from datetime import datetime, timedelta, timezone  # noqa: E402


def _msg_tipo(testo="", *, autore_id=5, bot=False, webhook=None, allegati=(), embeds=(),
              sticker=(), avatar="x", ruoli=1, eta_giorni=100):
    m = _msg(testo, bot=bot, allegati=allegati, embeds=embeds, webhook=webhook)
    m.author.id = autore_id
    m.author.avatar = avatar
    m.author.roles = [MagicMock(id=i) for i in range(ruoli)]
    m.author.created_at = datetime.now(timezone.utc) - timedelta(days=eta_giorni)
    m.stickers = list(sticker)
    return m


@pytest.mark.parametrize(
    "tipo,messaggio,atteso",
    [
        ("webhook", _msg_tipo(webhook=9, bot=True), True),
        ("webhook", _msg_tipo(bot=True), False),
        ("iyokai", _msg_tipo(autore_id=999, bot=True), True),
        ("iyokai", _msg_tipo(autore_id=998, bot=True), False),
        ("emoji", _msg_tipo("😀😀 👍"), True),
        ("emoji", _msg_tipo("<:ok:123456789012345678> <a:x:1>"), True),
        ("emoji", _msg_tipo("ciao 😀"), False),
        ("emoji", _msg_tipo(""), False),
        ("solo-testo", _msg_tipo("ciao"), True),
        ("solo-testo", _msg_tipo("ciao", allegati=[1]), False),
        ("solo-testo", _msg_tipo("ciao", embeds=[1]), False),
        ("solo-testo", _msg_tipo("ciao", sticker=[1]), False),
        ("sospetti", _msg_tipo("x", avatar=None), True),
        ("sospetti", _msg_tipo("x", ruoli=1), True),
        ("sospetti", _msg_tipo("x", ruoli=3, eta_giorni=2), True),
        ("sospetti", _msg_tipo("x", ruoli=3, eta_giorni=100), False),
    ],
)
def test_filtro_tipo(tipo, messaggio, atteso):
    assert messaggio_passa(messaggio, FiltriClear(tipo=tipo, bot_id=999)) is atteso


@pytest.mark.parametrize(
    "modo,testo,atteso",
    [
        ("contiene", "dico ciao a te", True),
        ("inizia", "Ciao a te", True),
        ("inizia", "dico ciao", False),
        ("finisce", "dico CIAO", True),
        ("finisce", "ciao dico", False),
        ("uguale", "CIAO", True),
        ("uguale", "ciao!", False),
    ],
)
def test_filtro_modo_del_testo(modo, testo, atteso):
    assert messaggio_passa(_msg(testo), FiltriClear(contiene="ciao", modo=modo)) is atteso


async def test_clear_passa_tipo_e_modo_ai_filtri(ambiente):
    inter, canale, canale_log = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 50, contains="ciao", tipo="solo-testo", modo="inizia")

    check = canale.purge.call_args.kwargs["check"]
    assert check(_msg_tipo("ciao a tutti")) and not check(_msg_tipo("dico ciao"))
    embed = canale_log.send.call_args.kwargs["embed"]
    assert any("solo-testo" in f.value for f in embed.fields)


def test_clear_ha_i_filtri_nuovi_e_sta_nei_limiti():
    import inspect
    from discord import app_commands
    cmd = ModerationClearCog.clear
    nomi = [p.name for p in cmd.parameters] if hasattr(cmd, "parameters") else list(inspect.signature(cmd.callback).parameters)
    assert "tipo" in nomi and "modo" in nomi
    assert len([n for n in nomi if n not in ("self", "interaction")]) <= 25


# --- M2: regex, prima/dopo, età, tetti, reazioni (MOD-072, 080, 081, 082, 087) ---

from core.clear_filter_logic import (  # noqa: E402
    MAX_CLEAR_AMOUNT,
    MAX_VECCHI,
    crea_controllo,
    leggi_riferimento_messaggio,
)


def test_filtro_regex_con_re2():
    f = FiltriClear(contiene=r"^\d{3}-\d{4}$", modo="regex")
    assert messaggio_passa(_msg("555-1234"), f)
    assert not messaggio_passa(_msg("ciao"), f)


def test_leggi_riferimento_id_e_link():
    assert leggi_riferimento_messaggio("123456789012345678", 55) == 123456789012345678
    assert leggi_riferimento_messaggio("https://discord.com/channels/1/55/777", 55) == 777
    with pytest.raises(ValueError):
        leggi_riferimento_messaggio("https://discord.com/channels/1/66/777", 55)
    with pytest.raises(ValueError):
        leggi_riferimento_messaggio("boh", 55)


def test_filtro_eta_dei_messaggi():
    vecchio = _msg("x")
    vecchio.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    assert messaggio_passa(vecchio, FiltriClear(piu_vecchi_di_s=3600))
    assert not messaggio_passa(vecchio, FiltriClear(piu_nuovi_di_s=3600))
    assert messaggio_passa(vecchio, FiltriClear(piu_nuovi_di_s=86400))


def test_tetto_dei_messaggi_vecchi_a_100():
    ora = datetime.now(timezone.utc)
    controllo, stato = crea_controllo(FiltriClear(), ora=ora)
    vecchi = []
    for _ in range(MAX_VECCHI + 30):
        m = _msg("x")
        m.created_at = ora - timedelta(days=20)
        vecchi.append(m)
    recente = _msg("x")
    recente.created_at = ora - timedelta(days=1)
    scelti = [m for m in vecchi if controllo(m)]
    assert len(scelti) == MAX_VECCHI and stato.vecchi_saltati == 30
    assert controllo(recente)


def test_tetto_totale_a_mille():
    assert MAX_CLEAR_AMOUNT == 1000


async def test_clear_oltre_200_e_prima_dopo(ambiente):
    inter, canale, _ = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 1000, dopo="100", prima="https://discord.com/channels/1/55/200")

    k = canale.purge.call_args.kwargs
    assert k["limit"] == 1000 and k["after"].id == 100 and k["before"].id == 200


async def test_clear_link_di_un_altro_canale_non_cancella(ambiente):
    inter, canale, _ = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, dopo="https://discord.com/channels/1/66/200")

    canale.purge.assert_not_awaited()
    assert inter.response.send_message.call_args.kwargs["ephemeral"] is True


async def test_clear_regex_sbagliata_non_cancella(ambiente):
    inter, canale, _ = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, contains=r"(a)\1", modo="regex")

    canale.purge.assert_not_awaited()


async def test_clear_modo_regex_senza_testo_non_cancella(ambiente):
    inter, canale, _ = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, modo="regex")

    canale.purge.assert_not_awaited()


async def test_clear_durata_sbagliata_non_cancella(ambiente):
    inter, canale, _ = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, piu_vecchi_di="boh")

    canale.purge.assert_not_awaited()


async def test_clear_dice_quanti_vecchi_restano(ambiente):
    inter, canale, _ = ambiente

    async def finto_purge(limit, check, **k):
        ora = datetime.now(timezone.utc)
        for _ in range(MAX_VECCHI + 5):
            m = _msg("x")
            m.created_at = ora - timedelta(days=20)
            check(m)
        return [1, 2]

    canale.purge = finto_purge
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 1000)

    assert "5" in inter.followup.send.call_args.args[0]


# reazioni

def _msg_reazioni(reazioni):
    m = MagicMock()
    m.reactions = [MagicMock(emoji=e) for e in reazioni]
    m.clear_reactions = AsyncMock()
    m.clear_reaction = AsyncMock()
    return m


def _storia(messaggi):
    async def gen(limit=None):
        for m in messaggi[:limit]:
            yield m
    return gen


async def test_reazioni_toglie_tutte(ambiente, monkeypatch):
    import cogs.moderation.clear as modulo
    monkeypatch.setattr(modulo, "PAUSA_REAZIONI", 0)
    inter, canale, canale_log = ambiente
    msgs = [_msg_reazioni(["👍"]), _msg_reazioni([]), _msg_reazioni(["🎉"])]
    canale.history = _storia(msgs)
    cog = ModerationClearCog(bot=None)

    await cog.reazioni.callback(cog, inter, 3)

    msgs[0].clear_reactions.assert_awaited()
    msgs[1].clear_reactions.assert_not_awaited()
    msgs[2].clear_reactions.assert_awaited()
    canale_log.send.assert_awaited()


async def test_reazioni_solo_una_emoji(ambiente, monkeypatch):
    import cogs.moderation.clear as modulo
    monkeypatch.setattr(modulo, "PAUSA_REAZIONI", 0)
    inter, canale, _ = ambiente
    msgs = [_msg_reazioni(["👍", "🎉"]), _msg_reazioni(["🎉"])]
    canale.history = _storia(msgs)
    cog = ModerationClearCog(bot=None)

    await cog.reazioni.callback(cog, inter, 2, emoji="👍")

    msgs[0].clear_reaction.assert_awaited_with("👍")
    msgs[1].clear_reaction.assert_not_awaited()
    msgs[0].clear_reactions.assert_not_awaited()


async def test_reazioni_si_ferma_dopo_tre_403(ambiente, monkeypatch):
    import cogs.moderation.clear as modulo
    monkeypatch.setattr(modulo, "PAUSA_REAZIONI", 0)
    inter, canale, _ = ambiente
    msgs = [_msg_reazioni(["👍"]) for _ in range(6)]
    for m in msgs:
        m.clear_reactions.side_effect = discord.Forbidden(MagicMock(status=403, reason="x"), "x")
    canale.history = _storia(msgs)
    cog = ModerationClearCog(bot=None)

    await cog.reazioni.callback(cog, inter, 6)

    assert sum(m.clear_reactions.await_count for m in msgs) == 3


async def test_clear_con_dopo_cancella_i_recenti_in_blocco(ambiente):
    """Con «dopo» la storia va comunque dal più nuovo: se si parte dai vecchi, discord.py
    cancella uno per uno anche tutti i recenti (fino a 900 chiamate) e il tetto dei vecchi non serve."""
    from discord.abc import _purge_helper

    inter, canale, _ = ambiente
    ora = datetime.now(timezone.utc)
    messaggi = []  # dal più nuovo al più vecchio
    for giorni in (0, 0, 0, 1, 1, 20, 20, 20):
        m = _msg("x")
        m.created_at = ora - timedelta(days=giorni, minutes=len(messaggi))
        m.id = discord.utils.time_snowflake(m.created_at)
        m.type = discord.MessageType.default
        m.delete = AsyncMock()
        messaggi.append(m)

    async def storia(limit=None, before=None, after=None, oldest_first=None, around=None):
        ordine = list(reversed(messaggi)) if (after is not None if oldest_first is None else oldest_first) else messaggi
        for m in ordine:
            if after is None or m.id > after.id:
                yield m

    canale.history = storia
    canale.delete_messages = AsyncMock()
    canale.purge = lambda **k: _purge_helper(canale, **k)
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 1000, dopo="1")

    in_blocco = [m for chiamata in canale.delete_messages.await_args_list for m in chiamata.args[0]]
    assert len(in_blocco) == 5  # i 5 recenti in una chiamata sola
    assert sum(m.delete.await_count for m in messaggi) == 3  # solo i 3 vecchi uno per uno

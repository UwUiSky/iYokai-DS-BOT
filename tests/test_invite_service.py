"""
tests/test_invite_service.py
============================
Link d'invito personali: slug unici e stabili, chi può averlo, invito Discord creato una volta
e ricreato se sparisce, tipo di ingresso registrato, opzioni dell'admin, pulizia all'uscita.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.database as database_module
from core import invite_links_logic as l, invite_service as svc
from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.invite_tracker import InviteTracker
from core.repositories.invite_links_repo import invite_links_repo
from core.repositories.invite_stats_repo import invite_stats_repo
from tests.support.discord_fakes import fake_guild, fake_member, fake_role, fake_text_channel

G = 7700
NOT_FOUND = discord.NotFound(MagicMock(status=404), "no")


def guild_con_canale(guild_id=G, *, permesso=True, funzioni=(), nome="Il Mio Server"):
    guild = fake_guild(guild_id, nome)
    canale = fake_text_channel(guild_id + 1, "benvenuto")
    canale.position = 0
    canale.permissions_for = MagicMock(return_value=discord.Permissions(create_instant_invite=permesso))
    canale.create_invite = AsyncMock(return_value=SimpleNamespace(code="Abc123"))
    guild.text_channels = [canale]
    guild.system_channel = guild.rules_channel = guild.public_updates_channel = None
    guild.features = list(funzioni)
    guild.vanity_url_code = None
    guild.get_channel = MagicMock(side_effect=lambda i: canale if i == canale.id else None)
    return guild, canale


def membro(uid, nome="Anna"):
    m = fake_member(uid, name=nome)
    m.roles = []
    return m


@pytest.fixture
def servizio(monkeypatch, clean_db):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(svc, "invite_tracker", InviteTracker())
    monkeypatch.setattr(svc, "url_pubblico", lambda: "https://sito.test")
    return clean_db


async def accendi(guild_id=G, acceso=True):
    await db.set_module_active_for_guild(guild_id, svc.MODULO_INVITI, acceso, changed_by=None)


@pytest.mark.asyncio
async def test_slug_unico_stabile_e_con_suffisso(servizio):
    await accendi()
    await accendi(G + 10)
    g1, _ = guild_con_canale()
    g2, _ = guild_con_canale(G + 10)  # altro server con lo stesso nome
    a, b = membro(1, "Anna"), membro(2, "Anna")
    _, l1 = await svc.ottieni_link(g1, a)
    _, l2 = await svc.ottieni_link(g2, a)
    _, l3 = await svc.ottieni_link(g1, b)
    assert l1.slug == "il-mio-server-anna"
    assert (l2.slug, l3.slug) == ("il-mio-server-anna-2", "il-mio-server-anna-3")
    a.name = "Nuovo Nome"  # il vecchio indirizzo resta
    _, ancora = await svc.ottieni_link(g1, a)
    assert ancora.slug == l1.slug
    assert svc.indirizzo(l1) == "https://sito.test/invito/il-mio-server-anna"


@pytest.mark.asyncio
async def test_chi_non_puo_avere_il_link(servizio):
    guild, canale = guild_con_canale()
    m = membro(1)
    assert (await svc.ottieni_link(guild, m))[0] == l.MODULO_SPENTO
    await accendi()
    assert (await svc.ottieni_link(guild, None))[0] == l.NON_NEL_SERVER
    guild.get_role = MagicMock(return_value=fake_role(55))
    await svc.imposta_opzioni(guild, ruolo_link=55, changed_by=1)
    assert (await svc.ottieni_link(guild, m))[0] == l.RUOLO_MANCANTE
    m.roles = [SimpleNamespace(id=55)]
    assert (await svc.ottieni_link(guild, m))[0] == l.OK
    # server senza permesso o con gli inviti in pausa: niente link nuovo
    senza, _ = guild_con_canale(G, permesso=False)
    senza.get_role = guild.get_role
    assert (await svc.ottieni_link(senza, membro(2)))[0] == l.RUOLO_MANCANTE
    await svc.imposta_opzioni(senza, ruolo_link=None, changed_by=1)
    assert (await svc.ottieni_link(senza, membro(2)))[0] == l.SENZA_PERMESSO
    pausa, _ = guild_con_canale(G, funzioni=("INVITES_DISABLED",))
    assert (await svc.ottieni_link(pausa, membro(3)))[0] == l.INVITI_DISABILITATI


@pytest.mark.asyncio
async def test_invito_creato_una_volta_riusato_e_ricreato(servizio):
    await accendi()
    guild, canale = guild_con_canale()
    bot = MagicMock()
    bot.fetch_invite = AsyncMock()
    _, link = await svc.ottieni_link(guild, membro(1))
    assert await svc.invito_discord(bot, guild, link) == (l.OK, "Abc123")
    kw = canale.create_invite.await_args.kwargs
    assert kw["max_age"] == 0 and kw["max_uses"] == 0 and kw["unique"] is True
    assert (await invite_links_repo.da_slug(link.slug)).discord_code == "Abc123"
    assert await svc.invito_discord(bot, guild, link) == (l.OK, "Abc123")
    assert canale.create_invite.await_count == 1  # conosciuto dalla cache degli inviti
    # cancellato: il tracker non lo conosce più e Discord dice 404 -> ne nasce uno nuovo
    svc.invite_tracker._cache.set(guild.id, {})
    bot.fetch_invite.side_effect = NOT_FOUND
    canale.create_invite.return_value = SimpleNamespace(code="Nuovo99")
    assert await svc.invito_discord(bot, guild, link) == (l.OK, "Nuovo99")
    # Discord non risponde: non si creano inviti a raffica
    svc.invite_tracker._cache.set(guild.id, {})
    bot.fetch_invite.side_effect = discord.HTTPException(MagicMock(status=500), "x")
    assert await svc.invito_discord(bot, guild, link) == (l.OK, "Nuovo99")
    assert canale.create_invite.await_count == 2


@pytest.mark.asyncio
async def test_apri_link_controlla_tutto_adesso(servizio):
    await accendi()
    guild, canale = guild_con_canale()
    m = membro(1)
    guild.get_member = MagicMock(return_value=m)
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    bot.fetch_invite = AsyncMock()
    _, link = await svc.ottieni_link(guild, m)
    assert await svc.apri_link(bot, link.slug) == (l.OK, "Abc123")
    assert (await invite_links_repo.da_slug(link.slug))
    assert (await svc.apri_link(bot, "non-esiste"))[1] is None
    assert (await svc.apri_link(bot, "../x"))[1] is None
    await accendi(acceso=False)
    assert await svc.apri_link(bot, link.slug) == (l.MODULO_SPENTO, None)
    await accendi()
    guild.get_member = MagicMock(return_value=None)
    guild.fetch_member = AsyncMock(side_effect=NOT_FOUND)
    assert await svc.apri_link(bot, link.slug) == (l.NON_NEL_SERVER, None)


@pytest.mark.asyncio
async def test_ingresso_registrato_con_il_tipo_di_link(servizio):
    await accendi()
    guild, _ = guild_con_canale()
    guild.vanity_url_code = "mio"
    _, link = await svc.ottieni_link(guild, membro(1))
    await invite_links_repo.imposta_codice(link.slug, "Abc123")
    assert (await svc.registra_ingresso(guild, 50, ("Abc123", 999))).tipo == l.TIPO_PERSONALE
    i = await invite_stats_repo.ingresso_di(G, 50)
    assert (i.inviter_id, i.kind) == (1, "personale")  # l'invitante è il proprietario, non il bot
    assert (await svc.registra_ingresso(guild, 51, ("mio", None))).tipo == l.TIPO_VANITY
    assert (await svc.registra_ingresso(guild, 52, ("zzz", 7))).tipo == l.TIPO_NORMALE
    assert (await svc.registra_ingresso(guild, 53, None)).tipo == l.TIPO_SCONOSCIUTO
    assert (await invite_stats_repo.ingresso_di(G, 53)).inviter_id is None
    assert (await svc.registra_ingresso(guild, 1, ("Abc123", 999))).invitante_id is None  # niente auto-invito
    assert (await invite_stats_repo.stats_for(G, 1)).totale == 1
    assert await invite_stats_repo.per_tipo(G) == {"personale": 2, "vanity": 1, "normale": 1, "sconosciuto": 1}
    assert [u for u, _ in await invite_stats_repo.top(G)] == [1, 7]
    await invite_stats_repo.mark_left(G, 50)
    assert (await invite_stats_repo.ingresso_di(G, 50)).left_at is not None


@pytest.mark.asyncio
async def test_uscita_toglie_link_e_invito(servizio):
    await accendi()
    guild, _ = guild_con_canale()
    _, link = await svc.ottieni_link(guild, membro(1))
    await invite_links_repo.imposta_codice(link.slug, "Abc123")
    invito = SimpleNamespace(delete=AsyncMock())
    bot = MagicMock()
    bot.fetch_invite = AsyncMock(return_value=invito)
    await svc.elimina_link_membro(bot, G, 1)
    invito.delete.assert_awaited_once()
    assert await invite_links_repo.da_slug(link.slug) is None
    await svc.elimina_link_membro(bot, G, 1)  # niente da fare, niente errori


@pytest.mark.asyncio
async def test_opzioni_dell_admin(servizio):
    guild, canale = guild_con_canale()
    guild.get_role = MagicMock(side_effect=lambda i: fake_role(i) if i == 55 else None)
    assert await svc.imposta_opzioni(guild, canale_log=canale.id, ruolo_link=55, changed_by=1) is True
    o = await svc.leggi_opzioni(G)
    assert (o.canale_log_id, o.ruolo_link_id) == (canale.id, 55)
    assert await svc.imposta_opzioni(guild, canale_log=canale.id, changed_by=1) is False
    for cattivo in ({"canale_log": 12345}, {"ruolo_link": 999}, {"ruolo_link": G}):
        with pytest.raises(ImpostazioneNonValida):
            await svc.imposta_opzioni(guild, changed_by=1, **cattivo)
    assert await svc.imposta_opzioni(guild, canale_log=None, ruolo_link=None, changed_by=1) is True
    o = await svc.leggi_opzioni(G)
    assert (o.canale_log_id, o.ruolo_link_id) == (None, None)

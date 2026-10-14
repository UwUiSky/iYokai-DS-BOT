"""
tests/test_alert_opzioni_cog.py
===============================
Comandi /moduli alert kick, opzioni, ruolo-live, guida-social, rimuovi e
elenco (NF-32, #129), contro PostgreSQL reale e interazioni finte fedeli.
"""

from unittest.mock import MagicMock

import discord
import pytest
import pytest_asyncio

import cogs.utility.feed_alerts as modulo
from cogs.utility.feed_alerts import MODULE_FEED_ALERTS, FeedAlertsCog, _slug_kick
from core.alert_options_logic import leggi_id_avviso
from core.database import Database
from core.repositories.alert_options_repo import AlertOptionsRepository
from core.repositories.custom_webhook_repo import CustomWebhookRepository
from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
from core.repositories.kick_subscription_repo import KickSubscriptionRepository
from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository
from core.repositories.youtube_subscription_repo import YoutubeSubscriptionRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

GUILD = 900000077


@pytest_asyncio.fixture
async def ambiente(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.set_module_active_for_guild(GUILD, MODULE_FEED_ALERTS, True)
    pool = lambda: database.pool  # noqa: E731
    monkeypatch.setattr(modulo, "db", database)
    for nome, classe in (
        ("feed_subscription_repo", FeedSubscriptionRepository),
        ("twitch_subscription_repo", TwitchSubscriptionRepository),
        ("youtube_subscription_repo", YoutubeSubscriptionRepository),
        ("kick_subscription_repo", KickSubscriptionRepository),
        ("alert_options_repo", AlertOptionsRepository),
        ("custom_webhook_repo", CustomWebhookRepository),
    ):
        monkeypatch.setattr(modulo, nome, classe(pool_provider=pool))
    yield database
    for tabella in ("kick_subscriptions", "alert_options", "live_role_settings", "twitch_subscriptions"):
        await database.pool.execute(f"DELETE FROM {tabella} WHERE guild_id = $1", GUILD)
    await database.close()


def _ruolo(role_id=300, mentionable=True, managed=False, default=False, alto=False):
    r = MagicMock(spec=discord.Role)
    r.id, r.mentionable, r.managed = role_id, mentionable, managed
    r.is_default.return_value = default
    r.mention = f"<@&{role_id}>"
    r.__ge__ = lambda self, altro: alto
    return r


def _testo(interazione) -> str:
    return interazione.response.send_message.call_args.args[0] if interazione.response.send_message.call_args.args else (
        interazione.response.send_message.call_args.kwargs.get("content", "")
    )


def test_slug_e_id():
    assert _slug_kick("https://kick.com/Nome_1/") == "Nome_1"
    assert _slug_kick("kick.com/abc") == "abc"
    assert _slug_kick("non valido!") is None
    assert leggi_id_avviso("kk-4") == ("KK", 4)
    assert leggi_id_avviso("WH-1") is None
    assert leggi_id_avviso("TW-x") is None


@pytest.mark.asyncio
async def test_kick_opzioni_elenco_rimuovi(ambiente):
    cog = FeedAlertsCog(bot=None)
    canale = fake_text_channel()
    canale.id, canale.mention = 500, "<#500>"
    guild = fake_guild()
    guild.id = GUILD
    utente = fake_member()
    utente.guild_permissions = discord.Permissions(mention_everyone=True)

    i = fake_interaction(guild=guild, user=utente)
    await cog.add_kick.callback(cog, i, "https://kick.com/Streamer", canale, "Streamer")
    assert "KK-" in _testo(i)
    kk = int(_testo(i).split("KK-")[1].split("`")[0])

    i = fake_interaction(guild=guild, user=utente)
    await cog.add_kick.callback(cog, i, "no no", canale, "x")
    assert "non valido" in _testo(i)

    i = fake_interaction(guild=guild, user=utente)
    await cog.opzioni.callback(cog, i, f"KK-{kk}", ruolo=_ruolo(), elimina=True, fine=False, annunci=True)
    assert "Opzioni aggiornate" in _testo(i)
    opz = await modulo.alert_options_repo.get("KK", kk)
    assert (opz.mention_role_id, opz.ping_allowed, opz.delete_on_end, opz.notify_end, opz.crosspost) == (
        300, True, True, False, True,
    )

    # RSS: fine diretta non ha senso
    rss = await modulo.feed_subscription_repo.add_subscription(
        guild_id=GUILD, channel_id=500, feed_url="https://esempio.com/f", label="f", created_by=1,
        message_template=None, max_per_guild=25,
    )
    i = fake_interaction(guild=guild, user=utente)
    await cog.opzioni.callback(cog, i, f"RSS-{rss}", elimina=True)
    assert "solo per Twitch" in _testo(i)
    await modulo.feed_subscription_repo.remove_subscription(rss, GUILD)

    # ID inesistente / sbagliato
    i = fake_interaction(guild=guild, user=utente)
    await cog.opzioni.callback(cog, i, "KK-999999", bottone=False)
    assert "Nessuna sottoscrizione" in _testo(i)

    i = fake_interaction(guild=guild, user=utente)
    await cog.list_alerts.callback(cog, i)
    assert f"KK-{kk}" in i.response.send_message.call_args.kwargs["embed"].description

    i = fake_interaction(guild=guild, user=utente)
    await cog.remove.callback(cog, i, f"kk-{kk}")
    assert "rimossa" in _testo(i)
    assert await modulo.alert_options_repo.get("KK", kk) == (await modulo.alert_options_repo.get("KK", 999999))


@pytest.mark.asyncio
async def test_azzera_riporta_ai_valori_di_base(ambiente):
    cog = FeedAlertsCog(bot=None)
    guild = fake_guild()
    guild.id = GUILD
    utente = fake_member()
    utente.guild_permissions = discord.Permissions.none()
    kk = await modulo.kick_subscription_repo.add_subscription(GUILD, 500, "abc", "x", 1)
    await modulo.alert_options_repo.set_fields("KK", kk, GUILD, notify_end=False)
    i = fake_interaction(guild=guild, user=utente)
    await cog.opzioni.callback(cog, i, f"KK-{kk}", azzera=True)
    assert (await modulo.alert_options_repo.get("KK", kk)).notify_end is True


@pytest.mark.asyncio
async def test_ruolo_non_menzionabile_senza_permesso_non_avvisa(ambiente):
    cog = FeedAlertsCog(bot=None)
    guild = fake_guild()
    guild.id = GUILD
    utente = fake_member()
    utente.guild_permissions = discord.Permissions.none()
    tw = await modulo.twitch_subscription_repo.add_subscription(
        guild_id=GUILD, channel_id=500, twitch_login="abc", label="t", created_by=1, max_per_guild=25
    )
    i = fake_interaction(guild=guild, user=utente)
    await cog.opzioni.callback(cog, i, f"TW-{tw}", ruolo=_ruolo(mentionable=False))
    assert (await modulo.alert_options_repo.get("TW", tw)).ping_allowed is False
    assert "non avvisato" in _testo(i)

    i = fake_interaction(guild=guild, user=utente)
    await cog.opzioni.callback(cog, i, f"TW-{tw}", ruolo=_ruolo(default=True))
    assert "@everyone" in _testo(i)


@pytest.mark.asyncio
async def test_ruolo_live_gerarchia_e_salvataggio(ambiente):
    cog = FeedAlertsCog(bot=None)
    guild = fake_guild()
    guild.id = GUILD
    guild.owner_id = 1
    utente = fake_member()
    utente.id = 2
    utente.top_role = _ruolo(role_id=10)
    me = MagicMock()
    me.guild_permissions = discord.Permissions(manage_roles=True)
    me.top_role = _ruolo(role_id=11)
    guild.me = me

    i = fake_interaction(guild=guild, user=utente)
    await cog.ruolo_live.callback(cog, i, _ruolo(alto=True))
    assert "uguale o superiore al tuo" in _testo(i)

    i = fake_interaction(guild=guild, user=utente)
    await cog.ruolo_live.callback(cog, i, _ruolo(role_id=301))
    assert await modulo.alert_options_repo.get_live_role(GUILD) == 301

    i = fake_interaction(guild=guild, user=utente)
    await cog.ruolo_live.callback(cog, i, None)
    assert "301" in _testo(i)


@pytest.mark.asyncio
async def test_guida_social_e_tetto(ambiente):
    cog = FeedAlertsCog(bot=None)
    i = fake_interaction()
    await cog.guida_social.callback(cog, i)
    assert "TikTok" in i.response.send_message.call_args.kwargs["embed"].description

    for n in range(modulo.MAX_LIVE_PER_SERVER):
        assert await modulo.kick_subscription_repo.add_subscription(
            GUILD, 500, f"c{n}", "x", 1, max_per_guild=modulo.MAX_LIVE_PER_SERVER
        )
    guild = fake_guild()
    guild.id = GUILD
    canale = fake_text_channel()
    i = fake_interaction(guild=guild)
    await cog.add_kick.callback(cog, i, "altro", canale, "x")
    assert "massimo consentito" in _testo(i)

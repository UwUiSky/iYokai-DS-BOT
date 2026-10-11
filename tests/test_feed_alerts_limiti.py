"""
tests/test_feed_alerts_limiti.py
====================================
Issue #67, voce 11.8 (LIM-16): tetto di feed per server e lista
`/moduli alert elenco` che non supera i 4096 caratteri di un embed.
"""

from types import SimpleNamespace
from unittest.mock import create_autospec

import pytest

import cogs.utility.feed_alerts as modulo
from core.database import Database
from core.repositories.custom_webhook_repo import CustomWebhookRepository
from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository
from core.repositories.youtube_subscription_repo import YoutubeSubscriptionRepository
from tests.support.discord_fakes import fake_interaction, fake_text_channel


@pytest.fixture
def repo(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", db_finto)

    async def url_sempre_sicuro(url):
        return True

    monkeypatch.setattr(modulo, "url_e_sicuro", url_sempre_sicuro)
    finti = {}
    for nome, classe in (
        ("feed_subscription_repo", FeedSubscriptionRepository),
        ("twitch_subscription_repo", TwitchSubscriptionRepository),
        ("youtube_subscription_repo", YoutubeSubscriptionRepository),
        ("custom_webhook_repo", CustomWebhookRepository),
    ):
        finto = create_autospec(classe, instance=True)
        if hasattr(classe, "add_subscription"):
            finto.add_subscription.return_value = 3
            finto.list_subscriptions.return_value = []
        else:
            finto.list_webhooks.return_value = []
        monkeypatch.setattr(modulo, nome, finto)
        finti[nome] = finto
    return finti


def _feed(i: int, url_lungo: bool = False):
    url = "https://esempio.com/" + ("x" * 180 if url_lungo else "") + f"{i}.rss"
    return SimpleNamespace(id=i, label=f"Feed {i}", channel_id=111, feed_url=url)


@pytest.mark.asyncio
async def test_il_26_feed_viene_rifiutato(repo):
    # il repository risponde None quando il tetto e' raggiunto (atomico)
    repo["feed_subscription_repo"].add_subscription.return_value = None
    cog = modulo.FeedAlertsCog(bot=None)
    interazione = fake_interaction()

    await cog.add.callback(
        cog, interazione, feed_url="https://esempio.com/nuovo.rss",
        channel=fake_text_channel(), label="Il ventiseiesimo",
    )

    testo = interazione.followup.send.call_args.args[0]
    assert "25" in testo and "✅" not in testo
    kwargs = repo["feed_subscription_repo"].add_subscription.call_args.kwargs
    assert kwargs["max_per_guild"] == modulo.MAX_FEED_PER_SERVER == 25


@pytest.mark.asyncio
async def test_il_25_feed_viene_accettato(repo):
    cog = modulo.FeedAlertsCog(bot=None)
    interazione = fake_interaction()

    await cog.add.callback(
        cog, interazione, feed_url="https://esempio.com/nuovo.rss",
        channel=fake_text_channel(), label="Il venticinquesimo",
    )

    assert "✅" in interazione.followup.send.call_args.args[0]


@pytest.mark.asyncio
async def test_elenco_lungo_resta_sotto_i_4096_caratteri(repo):
    repo["feed_subscription_repo"].list_subscriptions.return_value = [
        _feed(i, url_lungo=True) for i in range(25)
    ]
    repo["twitch_subscription_repo"].list_subscriptions.return_value = [
        SimpleNamespace(id=i, label=f"T{i}", twitch_login="a" * 25, channel_id=111)
        for i in range(40)
    ]
    cog = modulo.FeedAlertsCog(bot=None)
    interazione = fake_interaction()

    await cog.list_alerts.callback(cog, interazione)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    assert len(embed.description) <= 4096
    assert "altr" in embed.description  # dice che ce ne sono altre

"""
tests/test_feed_alerts_id_con_prefisso.py
=========================================
/alerts add, add-twitch e add-youtube-live mostrano l'ID della
sottoscrizione nella stessa forma che /alerts remove si aspetta
(RSS-3, TW-3, YT-3). Prima mostravano solo il numero, che remove
rifiuta con "Formato ID non valido".
"""

import re
from unittest.mock import create_autospec

import pytest

import cogs.utility.feed_alerts as modulo
from core.database import Database
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
    ):
        finto = create_autospec(classe, instance=True)
        finto.add_subscription.return_value = 3
        finto.remove_subscription.return_value = True
        monkeypatch.setattr(modulo, nome, finto)
        finti[nome] = finto
    return finti


def _id_mostrato(testo: str) -> str:
    trovato = re.search(r"ID `([^`]+)`", testo)
    assert trovato is not None, testo
    return trovato.group(1)


async def _rimuovi_con(cog, id_mostrato: str):
    interazione = fake_interaction()
    await cog.remove.callback(cog, interazione, subscription_id=id_mostrato)
    return interazione.response.send_message.call_args.args[0]


async def test_alerts_add_mostra_un_id_che_remove_accetta(repo):
    cog = modulo.FeedAlertsCog(bot=None)
    interazione = fake_interaction()

    await cog.add.callback(
        cog, interazione, feed_url="https://esempio.com/feed.rss",
        channel=fake_text_channel(), label="Prova",
    )

    id_mostrato = _id_mostrato(interazione.followup.send.call_args.args[0])
    assert id_mostrato == "RSS-3"
    assert await _rimuovi_con(cog, id_mostrato) == "Sottoscrizione rimossa."
    repo["feed_subscription_repo"].remove_subscription.assert_awaited_once_with(
        3, interazione.guild.id
    )


async def test_alerts_add_twitch_mostra_un_id_che_remove_accetta(repo):
    cog = modulo.FeedAlertsCog(bot=None)
    interazione = fake_interaction()

    await cog.add_twitch.callback(
        cog, interazione, twitch_login="streamerx", channel=fake_text_channel(), label="Prova"
    )

    id_mostrato = _id_mostrato(interazione.response.send_message.call_args.args[0])
    assert id_mostrato == "TW-3"
    assert await _rimuovi_con(cog, id_mostrato) == "Sottoscrizione rimossa."
    repo["twitch_subscription_repo"].remove_subscription.assert_awaited_once()


async def test_alerts_add_youtube_live_mostra_un_id_che_remove_accetta(repo):
    cog = modulo.FeedAlertsCog(bot=None)
    interazione = fake_interaction()

    await cog.add_youtube_live.callback(
        cog, interazione, youtube_channel_id="UCabc", channel=fake_text_channel(), label="Prova"
    )

    id_mostrato = _id_mostrato(interazione.response.send_message.call_args.args[0])
    assert id_mostrato == "YT-3"
    assert await _rimuovi_con(cog, id_mostrato) == "Sottoscrizione rimossa."
    repo["youtube_subscription_repo"].remove_subscription.assert_awaited_once()

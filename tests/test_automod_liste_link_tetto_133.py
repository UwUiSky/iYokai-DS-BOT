"""
tests/test_automod_liste_link_tetto_133.py
==========================================
Issue #133, AutoMod: le liste dei domini (whitelist e blacklist) hanno
un tetto. Oltre il tetto un dominio nuovo non si aggiunge e l'admin
riceve un messaggio chiaro; togliere un dominio funziona sempre.
"""

import pytest

from core.automod_advanced_logic import MAX_DOMINI_LISTA
from core.repositories.automod_advanced_repo import automod_advanced_repo
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.test_automod_config_commands import GUILD_ID, _FakeChoice, cog  # noqa: F401


def _interazione():
    return fake_interaction(guild=fake_guild(guild_id=GUILD_ID))


async def _domini(cog, azione: str, lista: str, dominio: str):
    interazione = _interazione()
    await cog.anti_link_domain.callback(
        cog,
        interazione,
        action=_FakeChoice(azione, azione),
        lista=_FakeChoice(lista.capitalize(), lista),
        domain=dominio,
    )
    return interazione.response.send_message.await_args


@pytest.mark.parametrize("lista", ["whitelist", "blacklist"])
async def test_oltre_il_tetto_il_dominio_non_si_aggiunge(cog, lista):
    for numero in range(MAX_DOMINI_LISTA):
        await _domini(cog, "add", lista, f"sito{numero}.it")

    chiamata = await _domini(cog, "add", lista, "uno-di-troppo.it")

    salvata = getattr(
        (await automod_advanced_repo.get_settings(GUILD_ID)).config.anti_link, lista
    )
    assert len(salvata) == MAX_DOMINI_LISTA
    assert "uno-di-troppo.it" not in salvata
    testo = chiamata.args[0]
    assert str(MAX_DOMINI_LISTA) in testo and "rimuovi" in testo.lower()
    assert chiamata.kwargs["ephemeral"] is True


async def test_al_tetto_si_puo_ancora_rimuovere_e_poi_aggiungere(cog):
    for numero in range(MAX_DOMINI_LISTA):
        await _domini(cog, "add", "blacklist", f"sito{numero}.it")

    await _domini(cog, "remove", "blacklist", "sito0.it")
    await _domini(cog, "add", "blacklist", "nuovo.it")

    salvata = (await automod_advanced_repo.get_settings(GUILD_ID)).config.anti_link.blacklist
    assert len(salvata) == MAX_DOMINI_LISTA
    assert "nuovo.it" in salvata and "sito0.it" not in salvata


async def test_dominio_gia_in_lista_al_tetto_non_da_errore(cog):
    for numero in range(MAX_DOMINI_LISTA):
        await _domini(cog, "add", "whitelist", f"sito{numero}.it")

    chiamata = await _domini(cog, "add", "whitelist", "sito5.it")

    assert "aggiunto" in chiamata.args[0]

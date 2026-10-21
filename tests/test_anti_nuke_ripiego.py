"""
tests/test_anti_nuke_ripiego.py
===============================
#59 (M 3.5): se la quarantena (o la rimozione dei ruoli) non toglie il
potere all'autore di un attacco, il server può scegliere un ripiego:
espellerlo o bannarlo. Spento di base.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.security.anti_nuke as modulo
import core.security_quarantine as quarantena
from core.repositories.security_repo import security_repo
from core.security_logic import AntiNukeConfig
from tests.support.discord_fakes import fake_member, fake_role
from tests.test_anti_nuke_117 import _scelta
from tests.test_anti_nuke_f1 import (  # noqa: F401  (fixture condivise)
    AUTORE_ID,
    GUILD_ID,
    _interazione,
    _server,
    attese,
    cog,
    db_finto,
)


def _http_403():
    return discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "no")


def _autore_intoccabile():
    """Autore con un ruolo sopra il bot: i ruoli non si tolgono."""
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=50)])
    autore.edit = AsyncMock(side_effect=_http_403())
    autore.add_roles = AsyncMock()
    autore.kick = AsyncMock()
    autore.ban = AsyncMock()
    return autore


def _quarantena_parziale(monkeypatch):
    monkeypatch.setattr(
        modulo, "metti_in_quarantena",
        AsyncMock(return_value=quarantena.EsitoQuarantena(True, [], ruoli_non_tolti=True)),
    )


async def test_di_base_nessun_ripiego(monkeypatch):
    _quarantena_parziale(monkeypatch)
    autore = _autore_intoccabile()
    server = _server(autore, [[]])

    esito, _ = await modulo._punish_actor(server, AUTORE_ID, AntiNukeConfig(punish_action="quarantine"), "r")

    assert AntiNukeConfig().ripiego_quarantena == "off"
    autore.kick.assert_not_awaited()
    autore.ban.assert_not_awaited()
    assert "ancora potente" in esito


@pytest.mark.parametrize("ripiego, metodo, parola", [("kick", "kick", "espulso"), ("ban", "ban", "bannato")])
async def test_quarantena_parziale_usa_il_ripiego(monkeypatch, ripiego, metodo, parola):
    _quarantena_parziale(monkeypatch)
    autore = _autore_intoccabile()
    server = _server(autore, [[]])
    config = AntiNukeConfig(punish_action="quarantine", ripiego_quarantena=ripiego)

    esito, tolti = await modulo._punish_actor(server, AUTORE_ID, config, "r")

    getattr(autore, metodo).assert_awaited_once()
    assert parola in esito and "ripiego" in esito and tolti == []


async def test_ruoli_non_tolti_usano_il_ripiego(monkeypatch):
    autore = _autore_intoccabile()
    server = _server(autore, [[]])
    config = AntiNukeConfig(punish_action="strip_roles", ripiego_quarantena="kick")

    esito, _ = await modulo._punish_actor(server, AUTORE_ID, config, "r")

    autore.kick.assert_awaited_once()
    assert "espulso" in esito


async def test_anche_il_ripiego_fallito_si_dice(monkeypatch):
    _quarantena_parziale(monkeypatch)
    autore = _autore_intoccabile()
    autore.kick = AsyncMock(side_effect=_http_403())
    server = _server(autore, [[]])
    config = AntiNukeConfig(punish_action="quarantine", ripiego_quarantena="kick")

    esito, _ = await modulo._punish_actor(server, AUTORE_ID, config, "r")

    assert "fallito" in esito and "ancora potente" in esito


async def test_quarantena_riuscita_non_usa_il_ripiego(monkeypatch):
    monkeypatch.setattr(
        modulo, "metti_in_quarantena",
        AsyncMock(return_value=quarantena.EsitoQuarantena(True, [52])),
    )
    autore = _autore_intoccabile()
    server = _server(autore, [[]])
    config = AntiNukeConfig(punish_action="quarantine", ripiego_quarantena="ban")

    await modulo._punish_actor(server, AUTORE_ID, config, "r")

    autore.ban.assert_not_awaited()


async def test_il_comando_salva_il_ripiego_e_lo_tiene(cog):
    await cog.punish_action.callback(cog, _interazione(), _scelta("quarantine"), _scelta("ban"))
    assert (await security_repo.get_settings(GUILD_ID)).anti_nuke.ripiego_quarantena == "ban"

    # Senza ripiego nel comando il valore salvato resta.
    await cog.punish_action.callback(cog, _interazione(), _scelta("strip_roles"))
    salvate = await security_repo.get_settings(GUILD_ID)
    assert salvate.anti_nuke.punish_action == "strip_roles"
    assert salvate.anti_nuke.ripiego_quarantena == "ban"

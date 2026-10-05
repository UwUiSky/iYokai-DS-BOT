"""
tests/test_clan_finanziato_con_trasferimento.py
===============================================
BUG-15: una gilda che copre il debito di creazione con un trasferimento
da un'altra gilda dello stesso capo diventa ufficiale, e il controllo
delle scadenze non la cancella. Database vero.
Funzioni coperte: SPEC §15.14
"""

from datetime import datetime, timedelta, timezone

import pytest

import core.guild_clan_expiry_worker as modulo_scadenze
from core.guild_clan_expiry_worker import GuildClanExpiryWorker
from core.guild_clan_logic import CREATION_DEFICIT
from tests.test_guild_clan_cog_behavior import (  # noqa: F401  (cog_e_repos è una fixture)
    _FakeGuild,
    _FakeInteraction,
    _FakeMember,
    cog_e_repos,
)

CAPO = 1
SERVER_RICCO = 100
SERVER_NUOVO = 200


class _BotSenzaServer:
    def get_guild(self, guild_id: int):
        return None


async def _due_gilde_dello_stesso_capo(clan_repo):
    """Una gilda ricca e ufficiale, e una appena creata ancora in debito."""
    tra_un_giorno = datetime.now(timezone.utc) + timedelta(hours=24)
    ricca = await clan_repo.create_clan(
        SERVER_RICCO, tag="RIC", name="Ricca", owner_id=CAPO, officialize_deadline=tra_un_giorno
    )
    await clan_repo.donate(ricca, user_id=CAPO, amount=CREATION_DEFICIT + 50_000)
    nuova = await clan_repo.create_clan(
        SERVER_NUOVO, tag="NEW", name="Nuova", owner_id=CAPO, officialize_deadline=tra_un_giorno
    )
    return ricca, nuova


async def _passa_la_scadenza(clan_repo, monkeypatch):
    monkeypatch.setattr(modulo_scadenze, "guild_clan_repo", clan_repo)
    dopo_la_scadenza = datetime.now(timezone.utc) + timedelta(hours=25)
    await GuildClanExpiryWorker().tick(bot=_BotSenzaServer(), now=dopo_la_scadenza)


@pytest.mark.asyncio
async def test_gilda_finanziata_con_trasferimento_resta(cog_e_repos, monkeypatch):
    cog, clan_repo, _ = cog_e_repos
    ricca, nuova = await _due_gilde_dello_stesso_capo(clan_repo)
    interazione = _FakeInteraction(_FakeGuild(SERVER_RICCO), user=_FakeMember(CAPO))

    await cog.clan_tesoreria_trasferisci.callback(
        cog, interazione, tag_destinazione="NEW", importo=CREATION_DEFICIT
    )
    await _passa_la_scadenza(clan_repo, monkeypatch)

    gilda = await clan_repo.get_clan(nuova)
    assert gilda is not None
    assert gilda.officialized is True
    assert gilda.treasury_balance == 0
    assert "ufficializzata" in interazione.response.sent_messages[0]


@pytest.mark.asyncio
async def test_trasferimento_che_non_copre_il_debito_non_salva_la_gilda(cog_e_repos, monkeypatch):
    cog, clan_repo, _ = cog_e_repos
    ricca, nuova = await _due_gilde_dello_stesso_capo(clan_repo)
    interazione = _FakeInteraction(_FakeGuild(SERVER_RICCO), user=_FakeMember(CAPO))

    await cog.clan_tesoreria_trasferisci.callback(
        cog, interazione, tag_destinazione="NEW", importo=CREATION_DEFICIT - 1
    )
    assert (await clan_repo.get_clan(nuova)).officialized is False
    await _passa_la_scadenza(clan_repo, monkeypatch)

    assert await clan_repo.get_clan(nuova) is None


@pytest.mark.asyncio
async def test_donazione_che_copre_il_debito_rende_ufficiale_nella_stessa_scrittura(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    _, nuova = await _due_gilde_dello_stesso_capo(clan_repo)

    await clan_repo.donate(nuova, user_id=CAPO, amount=CREATION_DEFICIT)

    assert (await clan_repo.get_clan(nuova)).officialized is True


@pytest.mark.asyncio
async def test_gilda_con_debito_gia_coperto_ma_non_ufficiale_viene_salvata(
    cog_e_repos, monkeypatch
):
    """Gilde finanziate con un trasferimento PRIMA di questa correzione."""
    cog, clan_repo, _ = cog_e_repos
    _, nuova = await _due_gilde_dello_stesso_capo(clan_repo)
    # Accredito che non passa da donazione né da trasferimento: il
    # debito è coperto ma la gilda resta "non ufficiale", come accadeva.
    await clan_repo.apply_treasury_delta(nuova, CREATION_DEFICIT, reason="voice_tick")
    assert (await clan_repo.get_clan(nuova)).officialized is False

    await _passa_la_scadenza(clan_repo, monkeypatch)

    gilda = await clan_repo.get_clan(nuova)
    assert gilda is not None
    assert gilda.officialized is True

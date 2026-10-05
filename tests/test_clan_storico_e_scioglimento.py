"""
tests/test_clan_storico_e_scioglimento.py
=========================================
M 9.13: /clan info mostra gli ultimi movimenti della tesoreria, e lo
scioglimento (a mano o per scadenza) toglie i ruoli Discord a tutti gli
ufficiali della gilda, non solo a chi lancia il comando. Database vero.
Funzioni coperte: SPEC §15.14
"""

from datetime import datetime, timedelta, timezone

import pytest

import core.guild_clan_expiry_worker as modulo_scadenze
from core.guild_clan_expiry_worker import GuildClanExpiryWorker
from tests.test_guild_clan_cog_behavior import (  # noqa: F401  (cog_e_repos è una fixture)
    _crea_clan_con_categoria,
    _FakeGuild,
    _FakeInteraction,
    _FakeMember,
    cog_e_repos,
)

GUILD_ID = 100
CAPO = 1
LIMITE_CAMPO_EMBED = 1024


def _nomi_dei_ruoli(membro) -> set[str]:
    return {ruolo.name for ruolo in membro.roles}


def _campo(embed, nome: str):
    return next((campo for campo in embed.fields if campo.name == nome), None)


async def _info(cog, guild):
    interazione = _FakeInteraction(guild, user=_FakeMember(CAPO))
    await cog.clan_info.callback(cog, interazione, tag=None)
    return interazione.response.sent_embeds[0]


# ----------------------------------------------------------------------
# Storico della tesoreria
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_clan_info_mostra_gli_ultimi_movimenti(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.donate(clan_id, user_id=7, amount=20_000)

    storico = _campo(await _info(cog, guild), "Ultimi movimenti")

    assert storico is not None
    righe = storico.value.split("\n")
    # Il più recente per primo: la donazione, poi il deficit di creazione.
    assert "+20000" in righe[0] and "<@7>" in righe[0]
    assert "-15000" in righe[1]


@pytest.mark.asyncio
async def test_lo_storico_mostra_cinque_movimenti_e_salta_i_tick_vocali(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    for importo in range(1, 9):
        await clan_repo.donate(clan_id, user_id=7, amount=importo)
    # I tick vocali sono uno al minuto per membro: coprirebbero tutto.
    for _ in range(10):
        await clan_repo.apply_treasury_delta(clan_id, 4, reason="voice_tick")

    storico = _campo(await _info(cog, guild), "Ultimi movimenti")

    righe = storico.value.split("\n")
    assert len(righe) == 5
    assert "+8 " in righe[0] and "+4 " in righe[4]
    assert all("<@7>" in riga for riga in righe)
    assert len(storico.value) <= LIMITE_CAMPO_EMBED


# ----------------------------------------------------------------------
# Scioglimento: via i ruoli a tutti gli ufficiali
# ----------------------------------------------------------------------
async def _gilda_con_ufficiali(cog, clan_repo, guild):
    """Capo (1), admin (2), co-owner (3) e un membro semplice (4), con i ruoli Discord dati dai comandi veri."""
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    persone = {user_id: _FakeMember(user_id) for user_id in (1, 2, 3, 4)}
    guild.presenti = persone
    for user_id in (2, 3, 4):
        await clan_repo.add_member(clan_id, user_id)
    for user_id, ruolo in ((2, "admin"), (3, "co_owner")):
        interazione = _FakeInteraction(guild, user=persone[CAPO])
        await cog.clan_promuovi.callback(cog, interazione, membro=persone[user_id], ruolo=ruolo)
    assert "Admin Clan" in _nomi_dei_ruoli(persone[2])
    assert "Admin Clan" in _nomi_dei_ruoli(persone[3])
    return clan_id, persone


@pytest.mark.asyncio
async def test_sciogli_toglie_i_ruoli_a_tutti_gli_ufficiali(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, persone = await _gilda_con_ufficiali(cog, clan_repo, guild)

    interazione = _FakeInteraction(guild, user=persone[CAPO])
    await cog.clan_sciogli.callback(cog, interazione)

    assert await clan_repo.get_clan(clan_id) is None
    for user_id in (1, 2, 3, 4):
        assert _nomi_dei_ruoli(persone[user_id]) & {"Capo Clan", "Admin Clan"} == set()


@pytest.mark.asyncio
async def test_la_scadenza_toglie_i_ruoli_agli_ufficiali(cog_e_repos, monkeypatch):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    # La gilda nasce dal comando vero: il capo riceve il ruolo "Capo Clan".
    capo = _FakeMember(CAPO)
    admin = _FakeMember(2)
    guild.presenti = {CAPO: capo, 2: admin}
    await cog.clan_crea.callback(cog, _FakeInteraction(guild, user=capo), tag="ABC", name="Breve")
    clan = await clan_repo.get_clan_by_tag(GUILD_ID, "ABC")
    await clan_repo.add_member(clan.id, 2)
    await cog.clan_promuovi.callback(
        cog, _FakeInteraction(guild, user=capo), membro=admin, ruolo="admin"
    )
    assert "Capo Clan" in _nomi_dei_ruoli(capo)

    class _Bot:
        def get_guild(self, guild_id: int):
            return guild if guild_id == GUILD_ID else None

    monkeypatch.setattr(modulo_scadenze, "guild_clan_repo", clan_repo)
    await GuildClanExpiryWorker().tick(
        bot=_Bot(), now=datetime.now(timezone.utc) + timedelta(hours=25)
    )

    assert await clan_repo.get_clan(clan.id) is None
    assert "Capo Clan" not in _nomi_dei_ruoli(capo)
    assert "Admin Clan" not in _nomi_dei_ruoli(admin)

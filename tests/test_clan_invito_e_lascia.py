"""
tests/test_clan_invito_e_lascia.py
==================================
M 9.8: /clan invita non aggiunge più nessuno senza consenso (manda un
invito con i bottoni Accetta e Rifiuta, che funzionano anche dopo un
riavvio del bot) e /clan lascia fa uscire dalla gilda. Database vero.
Funzioni coperte: SPEC §15.14
"""

import asyncio
from datetime import datetime, timedelta, timezone

import discord
import pytest
from discord.ext import commands

import cogs.leveling.leveling as leveling_module
from cogs.leveling.leveling import BottoneInvitoClan
from tests.support.concorrenza import apri_connessioni
from tests.test_guild_clan_cog_behavior import (  # noqa: F401  (cog_e_repos è una fixture)
    _clicca_invito,
    _crea_clan_con_categoria,
    _FakeGuild,
    _FakeInteraction,
    _FakeMember,
    cog_e_repos,
)

GUILD_ID = 100
CAPO = 1


async def _invita(cog, guild, invitato, chi_invita: int = CAPO):
    interazione = _FakeInteraction(guild, user=_FakeMember(chi_invita))
    await cog.clan_invita.callback(cog, interazione, membro=invitato)
    return interazione


def _nomi_dei_ruoli(membro) -> set[str]:
    return {ruolo.name for ruolo in membro.roles}


# ----------------------------------------------------------------------
# Invito
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rifiuto_dell_invito_non_fa_entrare(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    invitato = _FakeMember(2)
    invito = await _invita(cog, guild, invitato)

    clic = await _clicca_invito(invito, guild, invitato, azione="rifiuta")

    assert await clan_repo.get_member(clan_id, 2) is None
    assert invitato not in categoria.overwrites_impostati
    modifica = clic.response.edited_messages[0]
    assert "rifiutato" in modifica["content"]
    assert modifica["view"] is None  # i bottoni spariscono


@pytest.mark.asyncio
async def test_solo_l_invitato_puo_rispondere(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    invito = await _invita(cog, guild, _FakeMember(2))

    clic = await _clicca_invito(invito, guild, _FakeMember(3))

    assert "non è per te" in clic.response.sent_messages[0]
    assert await clan_repo.count_members(clan_id) == 1


@pytest.mark.asyncio
async def test_non_si_invita_un_bot(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    await _crea_clan_con_categoria(clan_repo, guild)
    robot = _FakeMember(2)
    robot._e_un_bot = True

    invito = await _invita(cog, guild, robot)

    assert "bot" in invito.response.sent_messages[0]
    assert invito.response.sent_views == []


@pytest.mark.asyncio
async def test_invito_scaduto_non_fa_entrare(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    ieri = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    bottone = BottoneInvitoClan("accetta", clan_id, 2, ieri)
    clic = _FakeInteraction(guild, user=_FakeMember(2))

    assert await bottone.interaction_check(clic) is True
    await bottone.callback(clic)

    assert await clan_repo.get_member(clan_id, 2) is None
    assert "scaduto" in clic.response.edited_messages[0]["content"]


@pytest.mark.asyncio
async def test_il_bottone_funziona_dopo_un_riavvio(cog_e_repos):
    """Dopo un riavvio discord.py ricostruisce il bottone dal solo custom_id."""
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    invitato = _FakeMember(2)
    invito = await _invita(cog, guild, invitato)
    custom_id = invito.response.sent_views[0].children[0].custom_id
    assert len(custom_id) <= 100  # limite di Discord

    schema = BottoneInvitoClan.__discord_ui_compiled_template__
    clic = _FakeInteraction(guild, user=invitato)
    ricostruito = await BottoneInvitoClan.from_custom_id(clic, None, schema.fullmatch(custom_id))
    assert await ricostruito.interaction_check(clic) is True
    await ricostruito.callback(clic)

    assert (await clan_repo.get_member(clan_id, 2)).role == "member"


@pytest.mark.asyncio
async def test_il_bottone_dell_invito_e_registrato_all_avvio():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await leveling_module.setup(bot)
    try:
        registrati = bot._connection._view_store._dynamic_items
        assert BottoneInvitoClan.__discord_ui_compiled_template__ in registrati
    finally:
        bot.get_cog("LevelingCog").cog_unload()
        await bot.close()


@pytest.mark.asyncio
async def test_due_inviti_accettati_insieme_una_sola_gilda(cog_e_repos):
    """Chi accetta nello stesso momento gli inviti di due gilde entra in una sola."""
    cog, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    await _crea_clan_con_categoria(clan_repo, guild, owner_id=1, tag="AAA")
    await _crea_clan_con_categoria(clan_repo, guild, owner_id=5, tag="BBB")
    invitato = _FakeMember(2)
    primo = await _invita(cog, guild, invitato, chi_invita=1)
    secondo = await _invita(cog, guild, invitato, chi_invita=5)

    await asyncio.gather(
        _clicca_invito(primo, guild, invitato),
        _clicca_invito(secondo, guild, invitato),
    )

    righe = await clan_repo._pool.fetchval(
        "SELECT COUNT(*) FROM clan_members WHERE user_id = 2"
    )
    assert righe == 1


@pytest.mark.asyncio
async def test_gilda_piena_al_momento_dell_accettazione(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild, max_members=2)
    primo_invitato, secondo_invitato = _FakeMember(2), _FakeMember(3)
    primo = await _invita(cog, guild, primo_invitato)
    secondo = await _invita(cog, guild, secondo_invitato)

    await asyncio.gather(
        _clicca_invito(primo, guild, primo_invitato),
        _clicca_invito(secondo, guild, secondo_invitato),
    )

    assert await clan_repo.count_members(clan_id) == 2  # il capo e uno solo dei due


# ----------------------------------------------------------------------
# /clan lascia
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lascia_fa_uscire_e_toglie_accesso_e_ruoli(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    socio = _FakeMember(2)
    await _clicca_invito(await _invita(cog, guild, socio), guild, socio)
    promozione = _FakeInteraction(guild, user=_FakeMember(CAPO))
    await cog.clan_promuovi.callback(cog, promozione, membro=socio, ruolo="co_owner")
    assert "Admin Clan" in _nomi_dei_ruoli(socio)

    interazione = _FakeInteraction(guild, user=socio)
    await cog.clan_lascia.callback(cog, interazione)

    assert interazione.response.chiamate[0] == "defer"
    assert "Hai lasciato" in interazione.response.sent_messages[0]
    assert await clan_repo.get_member(clan_id, 2) is None
    assert (await clan_repo.get_clan(clan_id)).co_owner_id is None
    assert socio not in categoria.overwrites_impostati
    assert "Admin Clan" not in _nomi_dei_ruoli(socio)


@pytest.mark.asyncio
async def test_il_capo_clan_non_puo_lasciare(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)

    interazione = _FakeInteraction(guild, user=_FakeMember(CAPO))
    await cog.clan_lascia.callback(cog, interazione)

    assert "/clan sciogli" in interazione.response.sent_messages[0]
    assert await clan_repo.get_member(clan_id, CAPO) is not None


@pytest.mark.asyncio
async def test_lascia_senza_gilda_avvisa(cog_e_repos):
    cog, _, _ = cog_e_repos

    interazione = _FakeInteraction(_FakeGuild(GUILD_ID), user=_FakeMember(9))
    await cog.clan_lascia.callback(cog, interazione)

    assert "Non fai parte di nessuna gilda" in interazione.response.sent_messages[0]


# ----------------------------------------------------------------------
# Migrazione 0018 su un database che ha già dati sporchi
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migrazione_0018_toglie_doppioni_e_orfani_e_mette_il_vincolo(clean_db):
    from pathlib import Path

    from core.repositories.guild_clan_repo import GuildClanRepository

    sql = (
        Path(leveling_module.__file__).parents[2]
        / "core" / "migrations" / "0018_clan_members_una_gilda_per_server.sql"
    ).read_text(encoding="utf-8")
    repo = GuildClanRepository(pool_provider=lambda: clean_db)
    tra_un_giorno = datetime.now(timezone.utc) + timedelta(hours=24)
    prima = await repo.create_clan(GUILD_ID, "AAA", "Prima", 1, tra_un_giorno)
    seconda = await repo.create_clan(GUILD_ID, "BBB", "Seconda", 5, tra_un_giorno)
    altrove = await repo.create_clan(GUILD_ID + 1, "CCC", "Altro server", 9, tra_un_giorno)

    async with clean_db.acquire() as conn:
        transazione = conn.transaction()
        await transazione.start()
        try:
            # Stato di prima della migrazione, con i dati sporchi.
            await conn.execute("DROP INDEX IF EXISTS uq_clan_members_server_utente")
            await conn.execute("ALTER TABLE clan_members DROP COLUMN IF EXISTS guild_id")
            vecchio = datetime.now(timezone.utc) - timedelta(days=30)
            for clan_id, user_id, ruolo, quando in (
                (prima, 7, "member", vecchio),      # 7 in due gilde dello stesso server:
                (seconda, 7, "admin", vecchio + timedelta(days=1)),  # resta la più vecchia
                (seconda, 1, "member", vecchio),    # 1 è capo della prima: resta da capo
                (altrove, 7, "member", vecchio),    # altro server: non è un doppione
                (999_999, 8, "member", vecchio),    # gilda che non esiste più
            ):
                await conn.execute(
                    "INSERT INTO clan_members (clan_id, user_id, role, joined_at) "
                    "VALUES ($1, $2, $3, $4)",
                    clan_id, user_id, ruolo, quando,
                )

            await conn.execute(sql)

            righe = await conn.fetch(
                "SELECT clan_id, user_id, role, guild_id FROM clan_members ORDER BY clan_id, user_id"
            )
            assert [tuple(r) for r in righe] == [
                (prima, 1, "owner", GUILD_ID),
                (prima, 7, "member", GUILD_ID),
                (seconda, 5, "owner", GUILD_ID),
                (altrove, 7, "member", GUILD_ID + 1),
                (altrove, 9, "owner", GUILD_ID + 1),
            ]
            with pytest.raises(Exception, match="uq_clan_members_server_utente"):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO clan_members (clan_id, user_id, role, guild_id) "
                        "VALUES ($1, 7, 'member', $2)",
                        seconda, GUILD_ID,
                    )
        finally:
            # Lo schema del database di test torna com'era.
            await transazione.rollback()

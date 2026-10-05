"""
tests/test_anti_raid_f1.py
==========================
Anti-raid, correzioni della fase F1 (BUG-12, LIM-30):
- il blocco scatta solo quando gli ingressi superano la soglia;
- il livello di verifica alzato torna com'era alla scadenza del blocco;
- ingressi insieme creano un solo ruolo Quarantined;
- un solo DM al proprietario per episodio;
- il ruolo Quarantined blocca ogni tipo di canale, anche quelli nuovi.

L'anti-raid viene configurato con i suoi comandi (database vero).
Server, canali e membri sono finti fedeli.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import cogs.moderation._shared as modulo_shared
import cogs.security.anti_raid as modulo
from core.automod_rate_tracker import AutomodRateTracker
from core.database import Database
from core.repositories.security_repo import security_repo
from tests.support.discord_fakes import (
    fake_forum_channel,
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
    fake_voice_channel,
)

GUILD_ID = 666
INIZIO = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def orologio(monkeypatch):
    """Orologio finto: il test decide che ore sono."""
    stato = {"adesso": INIZIO}
    monkeypatch.setattr(discord.utils, "utcnow", lambda: stato["adesso"])

    def avanti(**durata) -> datetime:
        stato["adesso"] += timedelta(**durata)
        return stato["adesso"]

    return avanti


@pytest.fixture
def db_finto(clean_db, monkeypatch):
    finto = create_autospec(Database, instance=True)
    finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo_shared, "db", finto)
    monkeypatch.setattr(modulo, "db", finto)
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(modulo, "security_rate_tracker", AutomodRateTracker())
    return finto


@pytest.fixture
def server() -> MagicMock:
    server = fake_guild(guild_id=GUILD_ID, owner_id=1)
    server.owner = fake_member(user_id=1)
    server.verification_level = discord.VerificationLevel.medium
    server.channels = []
    ruoli: dict[int, MagicMock] = {}

    async def _create_role(**kwargs):
        # Un attimo di attesa, come una chiamata vera a Discord: è qui
        # che due ingressi insieme creavano due ruoli.
        await asyncio.sleep(0.01)
        ruolo = fake_role(role_id=5000 + len(ruoli), name=kwargs["name"])
        ruoli[ruolo.id] = ruolo
        server.roles = list(ruoli.values())
        return ruolo

    async def _edit(**kwargs):
        if "verification_level" in kwargs:
            server.verification_level = kwargs["verification_level"]
        return server

    server.create_role.side_effect = _create_role
    server.get_role.side_effect = ruoli.get
    server.edit.side_effect = _edit
    return server


@pytest.fixture
async def cog(db_finto, server, orologio):
    bot = create_autospec(commands.Bot, instance=True)
    bot.get_guild.side_effect = lambda guild_id: server if guild_id == GUILD_ID else None
    cog = modulo.AntiRaidCog(bot)
    # Anti-raid acceso; raid = più di 2 ingressi in 60 secondi.
    await cog.enable.callback(cog, _interazione(), True)
    await cog.join_rate.callback(cog, _interazione(), 2, 60)
    return cog


def _interazione() -> MagicMock:
    return fake_interaction(guild=fake_guild(guild_id=GUILD_ID))


async def _azione(cog, valore: str) -> None:
    await cog.lockdown_action.callback(
        cog, _interazione(), app_commands.Choice(name=valore, value=valore)
    )


def _ingresso(server: MagicMock, user_id: int, *, avatar: bool = True) -> MagicMock:
    membro = fake_member(user_id=user_id, name=f"Persona{user_id}")
    membro.guild = server
    membro.created_at = INIZIO - timedelta(days=400)
    membro.avatar = MagicMock() if avatar else None
    return membro


async def _raid(cog, server: MagicMock, quanti: int = 3, primo_id: int = 100) -> list[MagicMock]:
    membri = [_ingresso(server, primo_id + numero) for numero in range(quanti)]
    for membro in membri:
        await cog.on_member_join(membro)
    return membri


async def _azioni_registrate() -> list[str]:
    return [riga["category"] for riga in await security_repo.get_recent_actions(GUILD_ID)]


# ====================================================================
# Il blocco scatta solo sulla soglia di ingressi
# ====================================================================
async def test_un_solo_ingresso_senza_avatar_non_fa_scattare_il_blocco(cog, server):
    await _azione(cog, "both")
    sospetto = _ingresso(server, 100, avatar=False)
    sospetto.created_at = INIZIO - timedelta(minutes=5)  # account nuovo
    sospetto.name = "asjdk48213"                         # nome "da bot"

    await cog.on_member_join(sospetto)

    sospetto.add_roles.assert_not_awaited()
    server.create_role.assert_not_awaited()
    server.edit.assert_not_awaited()
    server.owner.send.assert_not_awaited()
    assert await _azioni_registrate() == []


async def test_ingressi_oltre_la_soglia_fanno_scattare_il_blocco(cog, server):
    await _azione(cog, "both")

    membri = await _raid(cog, server, quanti=3)

    membri[0].add_roles.assert_not_awaited()
    membri[1].add_roles.assert_not_awaited()
    membri[2].add_roles.assert_awaited_once()
    assert server.verification_level is discord.VerificationLevel.highest
    assert await _azioni_registrate() == ["raid_join"]


# ====================================================================
# Scadenza del blocco e ripristino del livello di verifica
# ====================================================================
async def test_livello_di_verifica_torna_come_prima_alla_scadenza(cog, server, orologio):
    await _azione(cog, "verification")
    await _raid(cog, server)
    assert server.verification_level is discord.VerificationLevel.highest

    await cog.ripristina_blocchi_scaduti(orologio(seconds=modulo.DURATA_BLOCCO_SECONDI - 30))
    assert server.verification_level is discord.VerificationLevel.highest

    await cog.ripristina_blocchi_scaduti(orologio(seconds=60))
    assert server.verification_level is discord.VerificationLevel.medium

    # Il blocco è chiuso: un secondo giro non tocca più il server.
    server.edit.reset_mock()
    await cog.ripristina_blocchi_scaduti(orologio(minutes=5))
    server.edit.assert_not_awaited()


async def test_raid_che_continua_allunga_il_blocco_e_ricorda_il_livello_vero(
    cog, server, orologio
):
    await _azione(cog, "verification")
    await _raid(cog, server)
    orologio(seconds=modulo.DURATA_BLOCCO_SECONDI - 60)
    await _raid(cog, server, primo_id=200)  # seconda ondata, livello già al massimo

    await cog.ripristina_blocchi_scaduti(orologio(seconds=120))
    assert server.verification_level is discord.VerificationLevel.highest

    await cog.ripristina_blocchi_scaduti(orologio(seconds=modulo.DURATA_BLOCCO_SECONDI))
    assert server.verification_level is discord.VerificationLevel.medium
    # Alzato una volta sola: la seconda ondata non ripete la chiamata.
    livelli = [chiamata.kwargs["verification_level"] for chiamata in server.edit.await_args_list]
    assert livelli == [discord.VerificationLevel.highest, discord.VerificationLevel.medium]


async def test_livello_cambiato_a_mano_dallo_staff_non_viene_toccato(cog, server, orologio):
    await _azione(cog, "verification")
    await _raid(cog, server)
    server.verification_level = discord.VerificationLevel.high  # deciso dallo staff
    server.edit.reset_mock()

    await cog.ripristina_blocchi_scaduti(orologio(seconds=modulo.DURATA_BLOCCO_SECONDI + 1))

    server.edit.assert_not_awaited()
    assert server.verification_level is discord.VerificationLevel.high


async def test_ripristino_fallito_avvisa_lo_staff_e_non_riprova_all_infinito(
    cog, server, orologio
):
    await _azione(cog, "verification")
    await _raid(cog, server)
    server.owner.send.reset_mock()
    risposta = MagicMock()
    risposta.status = 403
    risposta.reason = "Forbidden"
    server.edit.side_effect = discord.Forbidden(risposta, "permessi mancanti")

    await cog.ripristina_blocchi_scaduti(orologio(seconds=modulo.DURATA_BLOCCO_SECONDI + 1))
    await cog.ripristina_blocchi_scaduti(orologio(minutes=5))

    assert server.edit.await_count == 2  # il raid e un solo tentativo di ripristino
    server.owner.send.assert_awaited_once()
    assert "medium" in server.owner.send.call_args.kwargs["embed"].description


# ====================================================================
# Un solo ruolo Quarantined con ingressi insieme
# ====================================================================
async def test_ingressi_insieme_creano_un_solo_ruolo_quarantined(cog, server):
    await _azione(cog, "quarantine")
    await cog.join_rate.callback(cog, _interazione(), 0, 60)
    membri = [_ingresso(server, 100 + numero) for numero in range(5)]

    await asyncio.gather(*(cog.on_member_join(membro) for membro in membri))

    assert server.create_role.await_count == 1
    ruoli_dati = {membro.add_roles.call_args.args[0].id for membro in membri}
    assert ruoli_dati == {5000}
    assert (await security_repo.get_settings(GUILD_ID)).quarantine_role_id == 5000


async def test_ruolo_non_creabile_non_rompe_l_ingresso(cog, server):
    await _azione(cog, "quarantine")
    risposta = MagicMock()
    risposta.status = 400
    risposta.reason = "Bad Request"
    server.create_role.side_effect = discord.HTTPException(risposta, "250 ruoli raggiunti")

    membri = await _raid(cog, server)

    membri[2].add_roles.assert_not_awaited()
    assert await _azioni_registrate() == ["raid_join"]


# ====================================================================
# Un solo DM al proprietario per episodio
# ====================================================================
async def test_un_solo_dm_al_proprietario_per_episodio(cog, server, orologio):
    await _azione(cog, "quarantine")

    await _raid(cog, server, quanti=8)

    server.owner.send.assert_awaited_once()
    # Ogni ingresso sospetto resta comunque nel registro.
    assert len(await _azioni_registrate()) == 6

    # Un raid nuovo, a episodio finito, avvisa di nuovo.
    orologio(seconds=modulo.DURATA_BLOCCO_SECONDI + 60)
    await _raid(cog, server, quanti=3, primo_id=300)
    assert server.owner.send.await_count == 2


async def test_controllo_scadenze_parte_con_il_cog_e_regge_un_bot_non_ancora_pronto():
    # BUG-19: wait_until_ready() prima del login fa morire il loop per sempre.
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = modulo.AntiRaidCog(bot)
    await bot.add_cog(cog)
    try:
        await asyncio.sleep(0.05)
        compito = cog._controlla_scadenze.get_task()
        assert compito is not None and not compito.done()
    finally:
        await bot.remove_cog("AntiRaidCog")
        await bot.close()
    assert not cog._controlla_scadenze.is_running()


# ====================================================================
# M 3.8 — il ruolo Quarantined blocca ogni tipo di canale (LIM-30)
# ====================================================================
PERMESSI_ATTESI = {
    "send_messages": False,
    "send_messages_in_threads": False,
    "create_public_threads": False,
    "create_private_threads": False,
    "add_reactions": False,
    "speak": False,
    "connect": False,
}


def _canali_di_ogni_tipo() -> list[MagicMock]:
    categoria = create_autospec(discord.CategoryChannel, instance=True)
    palco = create_autospec(discord.StageChannel, instance=True)
    canali = [fake_text_channel(), fake_voice_channel(), fake_forum_channel(), palco, categoria]
    for numero, canale in enumerate(canali):
        canale.id = 9000 + numero
        canale.name = f"canale-{numero}"
    return canali


def _permessi_negati(canale: MagicMock) -> dict:
    canale.set_permissions.assert_awaited_once()
    argomenti = dict(canale.set_permissions.call_args.kwargs)
    argomenti.pop("reason")
    return argomenti


async def test_ruolo_quarantined_blocca_ogni_tipo_di_canale(cog, server):
    await _azione(cog, "quarantine")
    server.channels = _canali_di_ogni_tipo()

    await _raid(cog, server)

    for canale in server.channels:
        assert _permessi_negati(canale) == PERMESSI_ATTESI
        assert canale.set_permissions.call_args.args[0].name == "Quarantined"


async def test_canale_nuovo_riceve_il_blocco_della_quarantena(cog, server):
    await _azione(cog, "quarantine")
    await _raid(cog, server)  # crea e salva il ruolo Quarantined
    nuovo = fake_text_channel(channel_id=9100, name="nuovo-canale")
    nuovo.guild = server

    await cog.on_guild_channel_create(nuovo)

    assert _permessi_negati(nuovo) == PERMESSI_ATTESI
    assert nuovo.set_permissions.call_args.args[0].id == 5000


async def test_canale_nuovo_senza_ruolo_di_quarantena_non_viene_toccato(cog, server):
    nuovo = fake_text_channel(channel_id=9100, name="nuovo-canale")
    nuovo.guild = server

    await cog.on_guild_channel_create(nuovo)

    nuovo.set_permissions.assert_not_awaited()


async def test_canale_nuovo_con_modulo_spento_non_viene_toccato(cog, server, db_finto):
    await _azione(cog, "quarantine")
    await _raid(cog, server)
    db_finto.is_module_active_for_guild.return_value = False
    nuovo = fake_voice_channel(channel_id=9100, name="nuova-sala")
    nuovo.guild = server

    await cog.on_guild_channel_create(nuovo)

    nuovo.set_permissions.assert_not_awaited()


async def test_canale_che_rifiuta_i_permessi_non_ferma_gli_altri(cog, server):
    await _azione(cog, "quarantine")
    server.channels = _canali_di_ogni_tipo()
    risposta = MagicMock()
    risposta.status = 403
    risposta.reason = "Forbidden"
    server.channels[0].set_permissions.side_effect = discord.Forbidden(risposta, "no")
    nascosto = fake_text_channel(channel_id=9200, name="___hidden___")
    server.channels.append(nascosto)

    membri = await _raid(cog, server)

    membri[2].add_roles.assert_awaited_once()
    server.channels[1].set_permissions.assert_awaited_once()
    nascosto.set_permissions.assert_not_awaited()

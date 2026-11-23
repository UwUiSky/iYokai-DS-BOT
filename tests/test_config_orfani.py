"""
tests/test_config_orfani.py
===========================
UTL-226 (#128, D111) # UTL-226: la configurazione si pulisce da canali e ruoli cancellati solo dopo 7 giorni.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import discord
import pytest

from core import config_orfani_logic as logica
from core.repositories.config_orfani_repo import ConfigOrfaniRepository
from tests.support.discord_fakes import fake_guild, fake_role

pytestmark = pytest.mark.asyncio

ADESSO = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def ambiente(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await database_module.db.ensure_guild_exists(800)
    repo = ConfigOrfaniRepository(lambda: clean_db)
    return database_module.db, repo


def _server(canali_vivi=(), ruoli_vivi=()):
    guild = fake_guild(800)
    guild.roles = [fake_role(role_id=1)]
    guild.get_role = lambda i: object() if i in ruoli_vivi else None
    guild.get_channel_or_thread = lambda i: object() if i in canali_vivi else None

    async def fetch(i):
        if i in canali_vivi:
            return object()
        raise discord.NotFound(MagicMock(status=404), "no")

    guild.fetch_channel = fetch
    return guild


async def _config(db):
    await db.set_guild_setting(800, "log_channel_id", 111, changed_by=1)
    await db.set_guild_setting(800, "ticket_support_role_ids", [5, 6], changed_by=1)


async def test_nessuna_pulizia_prima_dei_7_giorni(ambiente):
    db, repo = ambiente
    await _config(db)
    guild = _server(ruoli_vivi={5})  # canale 111 e ruolo 6 spariti (come in un nuke)
    assert await logica.pulisci_scaduti(guild, repo, ADESSO) == 0
    # sei giorni e 23 ore dopo: ancora niente
    assert await logica.pulisci_scaduti(guild, repo, ADESSO + timedelta(days=7) - timedelta(hours=1)) == 0
    assert await db.get_guild_setting(800, "log_channel_id") == 111
    assert await db.get_guild_setting(800, "ticket_support_role_ids") == [5, 6]
    assert set(await repo.elenco(800)) == {("canale", 111), ("ruolo", 6)}


async def test_dopo_7_giorni_si_pulisce_con_riga_nello_storico(ambiente):
    db, repo = ambiente
    await _config(db)
    guild = _server(ruoli_vivi={5})
    await logica.pulisci_scaduti(guild, repo, ADESSO)
    assert await logica.pulisci_scaduti(guild, repo, ADESSO + timedelta(days=7)) == 2
    assert await db.get_guild_setting(800, "log_channel_id") is None
    assert await db.get_guild_setting(800, "ticket_support_role_ids") == [5]
    storico = await db.get_config_history_filtrato(800, limit=10)
    assert {"log_channel_id", "ticket_support_role_ids"} <= {v.key_name for v in storico}
    assert await repo.elenco(800) == {}


async def test_canale_tornato_entro_7_giorni_non_si_pulisce(ambiente):
    db, repo = ambiente
    await _config(db)
    await logica.pulisci_scaduti(_server(ruoli_vivi={5}), repo, ADESSO)  # sparito
    tornato = _server(canali_vivi={111}, ruoli_vivi={5, 6})  # dopo 3 giorni è tornato (stesso ID)
    await logica.pulisci_scaduti(tornato, repo, ADESSO + timedelta(days=3))
    assert await repo.elenco(800) == {}
    # sparisce di nuovo: i 7 giorni ripartono da capo
    sparito = _server(ruoli_vivi={5, 6})
    await logica.pulisci_scaduti(sparito, repo, ADESSO + timedelta(days=8))
    assert await logica.pulisci_scaduti(sparito, repo, ADESSO + timedelta(days=12)) == 0
    assert await db.get_guild_setting(800, "log_channel_id") == 111


async def test_server_non_caricato_non_segna_niente(ambiente):
    db, repo = ambiente
    await _config(db)
    guild = _server()
    guild.roles = []
    assert await logica.pulisci_scaduti(guild, repo, ADESSO + timedelta(days=30)) == 0
    assert await repo.elenco(800) == {}
    assert await logica.pulisci_scaduti(None, repo, ADESSO) == 0


async def test_chi_non_e_piu_citato_perde_il_segno(ambiente):
    db, repo = ambiente
    await _config(db)
    guild = _server(ruoli_vivi={5})
    await logica.pulisci_scaduti(guild, repo, ADESSO)
    await db.remove_guild_setting(800, "log_channel_id", changed_by=1)  # tolto a mano (o rimappato da un ripristino)
    await logica.pulisci_scaduti(guild, repo, ADESSO + timedelta(days=1))
    assert set(await repo.elenco(800)) == {("ruolo", 6)}


async def test_anteprima_dice_quando_si_pulira(ambiente):
    db, repo = ambiente
    await _config(db)
    guild = _server(ruoli_vivi={5})
    await logica.pulisci_scaduti(guild, repo, ADESSO)
    righe = await logica.anteprima(guild, repo, ADESSO + timedelta(days=2))
    per_oggetto = {(r.tipo, r.oggetto_id): r for r in righe}
    assert per_oggetto[("canale", 111)].pulizia_il == ADESSO + timedelta(days=7)
    assert per_oggetto[("canale", 111)].chiavi == ["log_channel_id"]
    assert await db.get_guild_setting(800, "log_channel_id") == 111  # l'anteprima non tocca niente


# ---- il comando /admin-bot config pulisci ----
from cogs.utility import config_strumenti as modulo  # noqa: E402
from discord.ext import commands  # noqa: E402
from tests.support.discord_fakes import fake_interaction, fake_member  # noqa: E402


def _cog():
    return modulo.ConfigStrumentiCog(commands.Bot(command_prefix="!", intents=discord.Intents.default()))


async def test_pulisci_subito_solo_il_proprietario(ambiente, monkeypatch):
    db, repo = ambiente
    monkeypatch.setattr(modulo, "config_orfani_repo", repo)
    await _config(db)
    guild = _server(ruoli_vivi={5})
    guild.owner_id = 42
    cog = _cog()
    admin = fake_interaction(guild=guild, user=fake_member(user_id=7))
    await cog.pulisci.callback(cog, admin, True)
    assert "proprietario" in admin.response.send_message.call_args.args[0]
    assert await db.get_guild_setting(800, "log_channel_id") == 111  # niente è cambiato
    # l'anteprima è per tutti e non tocca niente
    anteprima = fake_interaction(guild=guild, user=fake_member(user_id=7))
    await cog.pulisci.callback(cog, anteprima, False)
    assert "7" in anteprima.followup.send.call_args.args[0]
    assert await db.get_guild_setting(800, "log_channel_id") == 111


async def test_pulisci_subito_il_proprietario_conferma(ambiente, monkeypatch):
    db, repo = ambiente
    monkeypatch.setattr(modulo, "config_orfani_repo", repo)
    await _config(db)
    guild = _server(ruoli_vivi={5})
    guild.owner_id = 42
    cog = _cog()
    i = fake_interaction(guild=guild, user=fake_member(user_id=42))
    await cog.pulisci.callback(cog, i, True)
    vista = i.followup.send.call_args.kwargs["view"]
    # un altro admin non può premere il bottone
    altro = fake_interaction(guild=guild, user=fake_member(user_id=7))
    await vista.conferma.callback(altro)
    assert await db.get_guild_setting(800, "log_channel_id") == 111
    prop = fake_interaction(guild=guild, user=fake_member(user_id=42))
    await vista.conferma.callback(prop)
    assert await db.get_guild_setting(800, "log_channel_id") is None
    assert await repo.elenco(800) == {}

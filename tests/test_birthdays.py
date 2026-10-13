"""
tests/test_birthdays.py
=======================
NF-26 (#97): compleanni. Solo giorno e mese; auguri nel canale (un messaggio per tutti i
festeggiati di oggi), ruolo per 24 ore, dato cancellabile dall'utente (registro NF-04).
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.birthdays as modulo
from cogs.utility.birthdays import BirthdaysCog
from core.birthday_logic import (
    data_valida,
    dividi_auguri,
    festeggia_oggi,
)
from core.birthday_worker import BirthdayWorker
from core.repositories.birthday_repo import BirthdayRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel
from tests.support.percorsi import comando_nel_gruppo


# ---------------------------------------------------------------- logica pura
@pytest.mark.parametrize("giorno, mese, ok", [(1, 1, True), (31, 12, True), (29, 2, True), (30, 2, False),
                                                (31, 4, False), (0, 1, False), (1, 13, False), (32, 1, False)])
def test_data_valida(giorno, mese, ok):
    assert data_valida(giorno, mese) is ok


def test_festeggia_oggi():
    assert festeggia_oggi(14, 3, date(2026, 3, 14)) is True
    assert festeggia_oggi(14, 3, date(2026, 3, 15)) is False


def test_29_febbraio_si_festeggia_il_28_negli_anni_non_bisestili():
    assert festeggia_oggi(29, 2, date(2027, 2, 28)) is True
    assert festeggia_oggi(29, 2, date(2027, 3, 1)) is False
    assert festeggia_oggi(29, 2, date(2028, 2, 29)) is True
    assert festeggia_oggi(29, 2, date(2028, 2, 28)) is False  # bisestile: solo il 29


def test_auguri_in_piu_messaggi_se_i_festeggiati_sono_tanti():
    menzioni = [f"<@{100000000000000000 + i}>" for i in range(200)]
    messaggi = dividi_auguri("🎂 Buon compleanno {users}!", menzioni)
    assert len(messaggi) > 1
    assert all(len(m) <= 2000 for m in messaggi)
    assert sum(m.count("<@") for m in messaggi) == 200


def test_auguri_modello_senza_segnaposto_aggiunge_i_nomi():
    [m] = dividi_auguri("Auguri!", ["<@1>", "<@2>"])
    assert "<@1>" in m and "<@2>" in m


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return BirthdayRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_imposta_cambia_rimuovi(repo):
    await repo.set_birthday(1, 5, 14, 3)
    await repo.set_birthday(1, 5, 15, 3)
    assert (await repo.get_birthday(1, 5)) == (15, 3)
    assert await repo.remove_birthday(1, 5) is True
    assert await repo.remove_birthday(1, 5) is False
    assert await repo.get_birthday(1, 5) is None


@pytest.mark.asyncio
async def test_claim_degli_auguri_una_volta_all_anno(repo):
    await repo.set_birthday(1, 5, 14, 3)
    await repo.set_birthday(1, 6, 14, 3)
    await repo.set_birthday(1, 7, 15, 3)
    primo = await repo.claim_due(1, date(2026, 3, 14))
    assert sorted(primo) == [5, 6]
    assert await repo.claim_due(1, date(2026, 3, 14)) == []  # già fatti
    assert await repo.claim_due(1, date(2027, 3, 14)) == [5, 6]  # l'anno dopo di nuovo


@pytest.mark.asyncio
async def test_claim_del_29_febbraio_nel_28(repo):
    await repo.set_birthday(1, 5, 29, 2)
    assert await repo.claim_due(1, date(2027, 2, 28)) == [5]
    await repo.set_birthday(1, 6, 29, 2)
    assert await repo.claim_due(1, date(2028, 2, 28)) == []
    assert sorted(await repo.claim_due(1, date(2028, 2, 29))) == [5, 6]


@pytest.mark.asyncio
async def test_rilascio_del_claim_permette_di_riprovare(repo):
    await repo.set_birthday(1, 5, 14, 3)
    assert await repo.claim_due(1, date(2026, 3, 14)) == [5]
    await repo.release_claim(1, [5], 2026)
    assert await repo.claim_due(1, date(2026, 3, 14)) == [5]


@pytest.mark.asyncio
async def test_configurazione(repo):
    assert (await repo.get_config(1)).channel_id is None
    await repo.set_channel(1, 50, "Auguri a {users}", ping_ruoli=False)
    await repo.set_role(1, 60)
    config = await repo.get_config(1)
    assert (config.channel_id, config.role_id, config.message) == (50, 60, "Auguri a {users}")
    assert [c.guild_id for c in await repo.list_active_configs()] == [1]
    await repo.set_channel(1, None, None, ping_ruoli=False)
    assert await repo.list_active_configs() == []


# ------------------------------------------------------------------------ worker
class _Scena:
    def __init__(self, utenti=(5, 6)):
        self.bot = MagicMock()
        self.guild = fake_guild(guild_id=1)
        self.guild.me.top_role = fake_role(900, "Bot", position=50)
        self.canale = fake_text_channel(50)
        self.canale.send = AsyncMock()
        self.ruolo = fake_role(60, "Compleanno", position=1)
        self.membri = {u: fake_member(u) for u in utenti}
        for m in self.membri.values():
            m.add_roles = AsyncMock()
        self.guild.get_channel = lambda cid: self.canale if cid == 50 else None
        self.guild.get_role = lambda rid: self.ruolo if rid == 60 else None
        self.guild.get_member = self.membri.get
        self.bot.get_guild = lambda gid: self.guild
        self.config = SimpleNamespace(guild_id=1, channel_id=50, role_id=60, message="🎂 Buon compleanno {users}!", ping_ruoli=False)
        self.repo = MagicMock()
        self.repo.list_active_configs = AsyncMock(return_value=[self.config])
        self.repo.claim_due = AsyncMock(return_value=list(utenti))
        self.repo.release_claim = AsyncMock()
        self.scheduler = MagicMock(schedule=AsyncMock(return_value=1))
        db_finto = MagicMock()
        db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
        self.worker = BirthdayWorker(self.repo, self.scheduler, db=db_finto)
        self.ora = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_un_messaggio_per_tutti_i_festeggiati_e_ruolo_a_tempo():
    s = _Scena()
    await s.worker.tick(s.bot, s.ora)
    s.canale.send.assert_awaited_once()
    testo = s.canale.send.await_args.args[0]
    assert "<@5>" in testo and "<@6>" in testo
    perm = s.canale.send.await_args.kwargs["allowed_mentions"]
    assert perm.everyone is False and perm.roles is False
    for m in s.membri.values():
        m.add_roles.assert_awaited_once()
    assert s.scheduler.schedule.await_count == 2
    primo = s.scheduler.schedule.await_args_list[0].args
    assert primo[2] == "birthday_role_remove" and (primo[3] - s.ora).total_seconds() == 24 * 3600


@pytest.mark.asyncio
async def test_chi_ha_lasciato_il_server_non_riceve_gli_auguri():
    s = _Scena(utenti=(5,))
    s.repo.claim_due.return_value = [5, 99]
    await s.worker.tick(s.bot, s.ora)
    assert "<@99>" not in s.canale.send.await_args.args[0]


@pytest.mark.asyncio
async def test_invio_fallito_rilascia_i_claim_per_riprovare():
    s = _Scena()
    s.canale.send.side_effect = discord.HTTPException(MagicMock(status=500, reason="x"), "boom")
    await s.worker.tick(s.bot, s.ora)
    s.repo.release_claim.assert_awaited_once_with(1, [5, 6], 2026)


@pytest.mark.asyncio
async def test_senza_festeggiati_non_manda_nulla():
    s = _Scena()
    s.repo.claim_due.return_value = []
    await s.worker.tick(s.bot, s.ora)
    s.canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_ruolo_non_assegnabile_gli_auguri_partono_lo_stesso():
    s = _Scena()
    s.ruolo.managed = True
    await s.worker.tick(s.bot, s.ora)
    s.canale.send.assert_awaited_once()
    for m in s.membri.values():
        m.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_modulo_spento():
    s = _Scena()
    s.worker._db.is_module_active_for_guild = AsyncMock(return_value=False)
    await s.worker.tick(s.bot, s.ora)
    s.repo.claim_due.assert_not_awaited()


# -------------------------------------------------------------------------- cog
@pytest.fixture
def cog(monkeypatch):
    c = BirthdaysCog(MagicMock())
    repo = MagicMock()
    repo.set_birthday = AsyncMock()
    repo.remove_birthday = AsyncMock(return_value=True)
    repo.get_birthday = AsyncMock(return_value=(14, 3))
    repo.set_channel = AsyncMock()
    repo.set_role = AsyncMock()
    repo.get_config = AsyncMock(return_value=SimpleNamespace(message="m", ping_ruoli=False))
    monkeypatch.setattr(modulo, "birthday_repo", repo)
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", db_finto)
    c.repo = repo
    return c


@pytest.mark.asyncio
async def test_imposta_valida_la_data(cog):
    i = fake_interaction()
    await cog.imposta.callback(cog, i, 30, 2)
    cog.repo.set_birthday.assert_not_awaited()
    await cog.imposta.callback(cog, i, 29, 2)
    cog.repo.set_birthday.assert_awaited_once_with(i.guild.id, i.user.id, 29, 2)


@pytest.mark.asyncio
async def test_rimuovi_cancella_il_dato(cog):
    i = fake_interaction()
    await cog.rimuovi.callback(cog, i)
    cog.repo.remove_birthday.assert_awaited_once_with(i.guild.id, i.user.id)


@pytest.mark.asyncio
async def test_mostra_dice_la_data_registrata(cog):
    i = fake_interaction()
    await cog.mostra.callback(cog, i)
    assert "14 marzo" in i.response.send_message.await_args.args[0]
    cog.repo.get_birthday.return_value = None
    await cog.mostra.callback(cog, i)
    assert "Non hai" in i.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_canale_senza_permessi_rifiutato(cog):
    i = fake_interaction()
    canale = fake_text_channel(50)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=False))
    await cog.canale.callback(cog, i, canale, None)
    cog.repo.set_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_ruolo_non_assegnabile_rifiutato_alla_configurazione(cog):
    server = fake_guild()
    server.me.top_role = fake_role(900, "Bot", position=50)
    i = fake_interaction(guild=server)
    i.user.top_role = fake_role(800, "Admin", position=60)
    gestito = fake_role(10, "Gestito", position=1, managed=True)
    await cog.ruolo.callback(cog, i, gestito)
    cog.repo.set_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_albero_dei_comandi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("imposta", "rimuovi", "mostra"):
        assert comando_nel_gruppo("level", f"compleanno {nome}") is not None
    for nome in ("canale", "ruolo"):
        assert comando_nel_gruppo("moduli", f"compleanni {nome}") is not None
    opz = {o["name"]: o for o in comando_nel_gruppo("level", "compleanno imposta").to_dict(bot.tree)["options"]}
    assert opz["giorno"]["max_value"] == 31 and opz["mese"]["max_value"] == 12

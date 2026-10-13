"""
tests/test_counters.py
======================
NF-16 (#87): canali contatore (membri, online, boost, obiettivo). Rinomina al massimo ogni 10
minuti per canale (LIM-3), solo se il numero è cambiato, tetto per server.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.counters as modulo
from cogs.utility.counters import CountersCog
from core.channel_rename import ChannelRenameTracker, RenameRateLimited
from core.counter_logic import (
    ETICHETTE_DI_BASE,
    MAX_CONTATORI,
    TIPI,
    Istantanea,
    nome_canale,
    valore_del_contatore,
    valida_etichetta,
)
from core.counter_worker import CounterWorker
from core.repositories.counter_repo import CounterRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo


# ---------------------------------------------------------------- logica pura
def test_valori_per_tipo():
    snap = Istantanea(member_count=120, online_count=30, boost_count=7)
    assert valore_del_contatore("members", snap) == 120
    assert valore_del_contatore("online", snap) == 30
    assert valore_del_contatore("boosts", snap) == 7
    assert valore_del_contatore("goal", snap) == 120


def test_online_sconosciuto_non_si_aggiorna():
    assert valore_del_contatore("online", Istantanea(10, None, 0)) is None


def test_nome_canale_con_obiettivo_e_taglio():
    assert nome_canale("Membri: {n}", 1234, None) == "Membri: 1234"
    assert nome_canale("{n}/{target}", 50, 100) == "50/100"
    assert len(nome_canale("x" * 90 + "{n}", 123456, None)) <= 100


@pytest.mark.parametrize("etichetta, ok", [("Membri: {n}", True), ("senza numero", False), ("", False),
                                             ("x" * 81 + "{n}", False), ("{n} ‮", True)])
def test_valida_etichetta(etichetta, ok):
    assert (valida_etichetta(etichetta, "members") is None) is ok


def test_obiettivo_richiede_target_nell_etichetta_di_base():
    assert "{target}" in ETICHETTE_DI_BASE["goal"]
    assert set(TIPI) == set(ETICHETTE_DI_BASE)


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return CounterRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_crea_elenca_elimina(repo):
    assert await repo.create(1, 10, "members", "Membri: {n}", None, created_by=7) == "ok"
    assert await repo.create(1, 10, "boosts", "Boost {n}", None, created_by=7) == "esiste"  # canale già usato
    elenco = await repo.list_for_guild(1)
    assert [(c.channel_id, c.kind) for c in elenco] == [(10, "members")]
    assert await repo.delete(1, elenco[0].id) is True
    assert await repo.delete(1, elenco[0].id) is False


@pytest.mark.asyncio
async def test_tetto_per_server(repo):
    for i in range(MAX_CONTATORI):
        assert await repo.create(1, 100 + i, "members", "{n}", None, created_by=7) == "ok"
    assert await repo.create(1, 999, "members", "{n}", None, created_by=7) == "pieno"
    assert await repo.create(2, 999, "members", "{n}", None, created_by=7) == "ok"


@pytest.mark.asyncio
async def test_ultimo_valore_e_elenco_globale(repo):
    await repo.create(1, 10, "members", "{n}", None, created_by=7)
    await repo.create(2, 20, "boosts", "{n}", None, created_by=7)
    [c] = await repo.list_for_guild(1)
    await repo.set_last_value(c.id, 42)
    assert (await repo.list_for_guild(1))[0].last_value == 42
    assert {c.guild_id for c in await repo.list_all()} == {1, 2}
    await repo.delete_by_channel(10)
    assert await repo.list_for_guild(1) == []


# ------------------------------------------------------------------------ worker
class _Scena:
    def __init__(self, monkeypatch, *, valore=100, ultimo=None, kind="members"):
        self.bot = MagicMock()
        self.guild = fake_guild(guild_id=1)
        self.guild.member_count = valore
        self.guild.premium_subscription_count = 3
        self.canale = MagicMock(spec=discord.VoiceChannel)
        self.canale.id = 10
        self.canale.name = "vecchio"
        self.guild.get_channel = lambda cid: self.canale if cid == 10 else None
        self.bot.get_guild = lambda gid: self.guild
        self.bot.fetch_guild = AsyncMock(return_value=SimpleNamespace(approximate_presence_count=55))
        self.contatore = SimpleNamespace(id=5, guild_id=1, channel_id=10, kind=kind, label="Membri: {n}", target=None,
                                         last_value=ultimo)
        self.repo = MagicMock()
        self.repo.list_all = AsyncMock(return_value=[self.contatore])
        self.repo.set_last_value = AsyncMock()
        self.repo.delete_by_channel = AsyncMock()
        self.rinomina = AsyncMock()
        db_finto = MagicMock()
        db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
        self.worker = CounterWorker(self.repo, rename=self.rinomina, db=db_finto)


@pytest.mark.asyncio
async def test_cambia_nome_se_il_numero_e_cambiato(monkeypatch):
    s = _Scena(monkeypatch, valore=100, ultimo=99)
    await s.worker.tick(s.bot)
    s.rinomina.assert_awaited_once()
    assert s.rinomina.await_args.args[1] == "Membri: 100"
    s.repo.set_last_value.assert_awaited_once_with(5, 100)


@pytest.mark.asyncio
async def test_non_tocca_discord_se_il_numero_non_cambia(monkeypatch):
    s = _Scena(monkeypatch, valore=100, ultimo=100)
    await s.worker.tick(s.bot)
    s.rinomina.assert_not_awaited()


@pytest.mark.asyncio
async def test_limite_di_discord_rimanda_al_giro_dopo(monkeypatch):
    s = _Scena(monkeypatch, valore=100, ultimo=99)
    s.rinomina.side_effect = RenameRateLimited(300)
    await s.worker.tick(s.bot)
    s.repo.set_last_value.assert_not_awaited()  # riprova al prossimo giro


@pytest.mark.asyncio
async def test_canale_cancellato_toglie_il_contatore(monkeypatch):
    s = _Scena(monkeypatch, valore=100, ultimo=99)
    s.guild.get_channel = lambda cid: None
    await s.worker.tick(s.bot)
    s.repo.delete_by_channel.assert_awaited_once_with(10)


@pytest.mark.asyncio
async def test_modulo_spento_non_fa_nulla(monkeypatch):
    s = _Scena(monkeypatch, valore=100, ultimo=99)
    s.worker._db.is_module_active_for_guild = AsyncMock(return_value=False)
    await s.worker.tick(s.bot)
    s.rinomina.assert_not_awaited()


@pytest.mark.asyncio
async def test_un_errore_su_un_server_non_ferma_gli_altri(monkeypatch):
    s = _Scena(monkeypatch, valore=100, ultimo=99)
    secondo = SimpleNamespace(**{**vars(s.contatore), "id": 6, "guild_id": 2})
    s.repo.list_all = AsyncMock(return_value=[secondo, s.contatore])
    chiamate = []

    def get_guild(gid):
        chiamate.append(gid)
        if gid == 2:
            raise RuntimeError("boom")
        return s.guild

    s.bot.get_guild = get_guild
    await s.worker.tick(s.bot)
    assert chiamate == [2, 1]
    s.rinomina.assert_awaited_once()


@pytest.mark.asyncio
async def test_online_chiede_i_conteggi_una_volta_per_server(monkeypatch):
    s = _Scena(monkeypatch, kind="online", ultimo=None)
    s.contatore.label = "Online: {n}"
    await s.worker.tick(s.bot)
    s.bot.fetch_guild.assert_awaited_once_with(1, with_counts=True)
    assert s.rinomina.await_args.args[1] == "Online: 55"


# -------------------------------------------------------------------------- cog
@pytest.fixture
def scena_cog(monkeypatch):
    cog = CountersCog(MagicMock())
    repo = MagicMock()
    repo.create = AsyncMock(return_value="ok")
    repo.list_for_guild = AsyncMock(return_value=[])
    repo.delete = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "counter_repo", repo)
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", db_finto)
    cog.repo = repo
    return cog


def _interazione(permessi_bot=None):
    server = fake_guild()
    server.member_count = 10
    i = fake_interaction(guild=server)
    return i, server


@pytest.mark.asyncio
async def test_crea_su_un_canale_esistente(scena_cog):
    i, server = _interazione()
    canale = MagicMock(spec=discord.VoiceChannel)
    canale.id = 10
    canale.permissions_for = MagicMock(return_value=discord.Permissions(manage_channels=True, view_channel=True))
    await scena_cog.crea.callback(scena_cog, i, "members", canale, None, None)
    scena_cog.repo.create.assert_awaited_once()
    assert scena_cog.repo.create.await_args.args[:3] == (server.id, 10, "members")


@pytest.mark.asyncio
async def test_crea_senza_permesso_di_gestire_il_canale(scena_cog):
    i, _ = _interazione()
    canale = MagicMock(spec=discord.VoiceChannel)
    canale.id = 10
    canale.mention = "<#10>"
    canale.permissions_for = MagicMock(return_value=discord.Permissions(manage_channels=False, view_channel=True))
    await scena_cog.crea.callback(scena_cog, i, "members", canale, None, None)
    scena_cog.repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_crea_senza_canale_ne_crea_uno_chiuso_a_tutti(scena_cog):
    i, server = _interazione()
    nuovo = MagicMock(spec=discord.VoiceChannel)
    nuovo.id = 77
    server.create_voice_channel = AsyncMock(return_value=nuovo)
    server.default_role = MagicMock()
    await scena_cog.crea.callback(scena_cog, i, "boosts", None, None, None)
    sovrascritture = server.create_voice_channel.await_args.kwargs["overwrites"]
    assert sovrascritture[server.default_role].connect is False
    assert scena_cog.repo.create.await_args.args[1] == 77


@pytest.mark.asyncio
async def test_crea_obiettivo_richiede_il_numero(scena_cog):
    i, _ = _interazione()
    await scena_cog.crea.callback(scena_cog, i, "goal", None, None, None)
    scena_cog.repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_crea_etichetta_senza_numero_rifiutata(scena_cog):
    i, _ = _interazione()
    await scena_cog.crea.callback(scena_cog, i, "members", None, "niente numero", None)
    scena_cog.repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_albero_dei_comandi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("crea", "elimina", "elenco"):
        assert comando_nel_gruppo("moduli", f"contatori {nome}") is not None
    crea = {o["name"]: o for o in comando_nel_gruppo("moduli", "contatori crea").to_dict(bot.tree)["options"]}
    assert len(crea["tipo"]["choices"]) == len(TIPI)
    assert crea["etichetta"]["max_length"] <= 85

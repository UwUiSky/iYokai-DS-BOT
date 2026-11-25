"""
tests/test_giveaway_worker.py
=================================
Test di GiveawayWorker.tick() contro PostgreSQL reale.
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from core.database import Database
from core.giveaway_worker import GiveawayWorker
from core.repositories.giveaway_repo import GiveawayRepository

ORA = datetime.now(timezone.utc)


class _FakeChannel(discord.TextChannel):
    def __init__(self, channel_id: int, fallisce: bool = False) -> None:
        self.id = channel_id
        self.sent_texts: list[str] = []
        self._fallisce = fallisce

    async def send(self, content: str, **kwargs) -> None:
        if self._fallisce:
            raise discord.HTTPException(response=_FakeHttpResponse(), message="errore finto")
        self.sent_texts.append(content)


class _FakeHttpResponse:
    status = 500
    reason = "errore finto"


class _FakeGuild:
    def __init__(self, guild_id: int, channel) -> None:
        self.id = guild_id
        self._channel = channel

    def get_channel_or_thread(self, channel_id: int):
        return self._channel

    async def fetch_channel(self, channel_id: int):
        # Non in memoria e non più su Discord: canale sparito.
        raise discord.NotFound(response=_FakeHttpResponse(), message="canale sparito")


class _FakeBot:
    def __init__(self, guild) -> None:
        self._guild = guild

    def get_guild(self, guild_id: int):
        return self._guild


@pytest.fixture
async def repo(monkeypatch):
    import core.giveaway_worker as modulo

    database = Database()
    await database.connect()
    await database.run_migrations()
    # Pulizia PRIMA di creare dati di test: clean_db (usata da altri
    # file, es. test_giveaway_repo.py) svuota solo all'inizio di
    # OGNI SUO test, non alla fine dell'intero file - una riga
    # lasciata dall'ultimo test di quel file sarebbe altrimenti
    # visibile qui (trovato per davvero: un giveaway "Server Boost"
    # residuo falsava il conteggio dei messaggi annunciati).
    await database.pool.execute("DELETE FROM giveaways")
    await database.pool.execute("DELETE FROM giveaway_entries")

    giveaway_repo = GiveawayRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(modulo, "giveaway_repo", giveaway_repo)

    yield giveaway_repo
    await database.pool.execute("DELETE FROM giveaways")
    await database.pool.execute("DELETE FROM giveaway_entries")
    await database.close()


@pytest.mark.asyncio
async def test_estrae_e_annuncia_i_vincitori(repo):
    giveaway_id = await repo.create_giveaway(
        100, channel_id=500, prize="Nitro", winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA - timedelta(minutes=1), created_by=1,
    )
    await repo.add_entry(giveaway_id, user_id=1)
    await repo.add_entry(giveaway_id, user_id=2)

    canale = _FakeChannel(500)
    await GiveawayWorker().tick(_FakeBot(_FakeGuild(100, canale)), now=ORA)

    assert len(canale.sent_texts) == 1
    assert "Nitro" in canale.sent_texts[0]
    assert (await repo.get_giveaway(giveaway_id)).ended is True


@pytest.mark.asyncio
async def test_nessun_partecipante_annuncia_comunque_senza_vincitori(repo):
    giveaway_id = await repo.create_giveaway(
        100, channel_id=500, prize="Nitro", winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA - timedelta(minutes=1), created_by=1,
    )

    canale = _FakeChannel(500)
    await GiveawayWorker().tick(_FakeBot(_FakeGuild(100, canale)), now=ORA)

    assert "nessuno ha partecipato" in canale.sent_texts[0]


@pytest.mark.asyncio
async def test_giveaway_non_ancora_scaduto_viene_ignorato(repo):
    await repo.create_giveaway(
        100, channel_id=500, prize="Nitro", winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA + timedelta(hours=1), created_by=1,
    )

    canale = _FakeChannel(500)
    await GiveawayWorker().tick(_FakeBot(_FakeGuild(100, canale)), now=ORA)

    assert canale.sent_texts == []


@pytest.mark.asyncio
async def test_canale_sparito_segna_comunque_concluso(repo):
    giveaway_id = await repo.create_giveaway(
        100, channel_id=500, prize="Nitro", winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA - timedelta(minutes=1), created_by=1,
    )

    await GiveawayWorker().tick(_FakeBot(_FakeGuild(100, channel=None)), now=ORA)

    assert (await repo.get_giveaway(giveaway_id)).ended is True


# ---- blocco C: la fine a stati non perde il premio ----
class _CanaleCheFallisceUnaVolta(_FakeChannel):
    def __init__(self, channel_id: int, volte: int) -> None:
        super().__init__(channel_id)
        self.volte = volte

    async def send(self, content: str, **kwargs) -> None:
        if self.volte > 0:
            self.volte -= 1
            raise discord.HTTPException(response=_FakeHttpResponse(), message="Discord ha avuto un singhiozzo")
        self.sent_texts.append(content)


async def _crea_con_iscritti(repo, canale_id=500, prize="Nitro", n=3):
    giveaway_id = await repo.create_giveaway(
        100, channel_id=canale_id, prize=prize, winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA - timedelta(minutes=1), created_by=1,
    )
    for u in range(1, n + 1):
        await repo.add_entry(giveaway_id, user_id=u)
    return giveaway_id


@pytest.mark.asyncio
async def test_se_l_annuncio_fallisce_i_vincitori_restano_e_il_giro_dopo_annuncia(repo):
    giveaway_id = await _crea_con_iscritti(repo)
    canale = _CanaleCheFallisceUnaVolta(500, volte=1)
    worker, bot = GiveawayWorker(), _FakeBot(_FakeGuild(100, canale))

    await worker.tick(bot, now=ORA)  # estrae, poi l'annuncio fallisce
    vincitori = await repo.get_vincitori(giveaway_id)
    assert len(vincitori) == 1 and canale.sent_texts == []
    assert (await repo.in_chiusura())[0][1] == "annuncio"  # estrazione fatta, annuncio da rifare

    await worker.tick(bot, now=ORA)  # il giro dopo
    assert len(canale.sent_texts) == 1 and "Nitro" in canale.sent_texts[0]
    assert await repo.get_vincitori(giveaway_id) == vincitori  # gli stessi: non si estrae due volte
    assert await repo.in_chiusura() == []


@pytest.mark.asyncio
async def test_un_giveaway_rotto_non_ferma_gli_altri(repo):
    rotto = await _crea_con_iscritti(repo, canale_id=501, prize="Rotto")
    sano = await _crea_con_iscritti(repo, canale_id=500, prize="Sano")

    class _Guild(_FakeGuild):
        def get_channel_or_thread(self, channel_id):
            if channel_id == 501:
                raise RuntimeError("errore imprevisto")
            return self._channel

    canale = _FakeChannel(500)
    await GiveawayWorker().tick(_FakeBot(_Guild(100, canale)), now=ORA)
    assert any("Sano" in t for t in canale.sent_texts)
    assert (await repo.in_chiusura())[0][0].id == rotto  # il rotto resta da riprovare


@pytest.mark.asyncio
async def test_dopo_troppi_tentativi_si_smette_e_si_avvisa(repo, monkeypatch):
    import core.avvisi_owner as avvisi
    from core import giveaway_worker as modulo

    monkeypatch.setattr(modulo, "MAX_TENTATIVI_FINE", 2)
    avvisati = []
    monkeypatch.setattr(avvisi.avvisi_owner, "caduto", lambda bot, nome, det="": avvisati.append(nome))
    giveaway_id = await _crea_con_iscritti(repo)
    canale = _CanaleCheFallisceUnaVolta(500, volte=99)
    worker, bot = GiveawayWorker(), _FakeBot(_FakeGuild(100, canale))
    for _ in range(3):
        await worker.tick(bot, now=ORA)
    assert await repo.in_chiusura() == []
    assert avvisati == [f"giveaway:{giveaway_id}"]
    stato = await repo._pool.fetchval("SELECT fase_fine FROM giveaways WHERE id = $1", giveaway_id)
    assert stato == "fallito"


@pytest.mark.asyncio
async def test_discord_che_non_risponde_non_conta_come_canale_sparito(repo):
    """Un errore 5xx nel cercare il canale si riprova; solo «non trovato» chiude senza annuncio."""
    giveaway_id = await _crea_con_iscritti(repo)

    class _Guild(_FakeGuild):
        def get_channel_or_thread(self, channel_id):
            return None

        async def fetch_channel(self, channel_id):
            raise discord.HTTPException(response=_FakeHttpResponse(), message="Discord giù")

    await GiveawayWorker().tick(_FakeBot(_Guild(100, None)), now=ORA)
    assert (await repo.in_chiusura())[0][1] == "annuncio"
    assert (await repo.get_giveaway(giveaway_id)).ended is True

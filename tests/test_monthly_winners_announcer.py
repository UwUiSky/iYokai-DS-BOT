"""
tests/test_monthly_winners_announcer.py
===========================================
Test di MonthlyWinnersAnnouncer.tick() contro PostgreSQL REALE —
righe di leveling_activity inserite davvero per il mese precedente,
non un repository finto: verifica che il podio annunciato sia quello
che il database restituisce sul serio.
"""

from datetime import datetime, timezone

import discord
import pytest

from core.monthly_winners_announcer import MonthlyWinnersAnnouncer
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.monthly_winners_repo import MonthlyWinnersRepository

ADESSO = datetime(2026, 10, 1, 0, 30, tzinfo=timezone.utc)  # periodo da annunciare: 2026-09


class _FakeChannel(discord.TextChannel):
    def __init__(self, channel_id: int, fallisce: bool = False) -> None:
        self.id = channel_id
        self.sent_embeds: list = []
        self._fallisce = fallisce

    async def send(self, embed=None) -> None:
        if self._fallisce:
            raise discord.HTTPException(response=_FakeHttpResponse(), message="errore finto")
        self.sent_embeds.append(embed)


class _FakeHttpResponse:
    status = 500
    reason = "errore finto"


class _FakeGuild:
    def __init__(self, guild_id: int, channel) -> None:
        self.id = guild_id
        self._channel = channel

    def get_channel(self, channel_id: int):
        return self._channel


class _FakeBot:
    def __init__(self, guild) -> None:
        self._guild = guild

    def get_guild(self, guild_id: int):
        return self._guild


@pytest.fixture
def repos(clean_db, monkeypatch):
    import core.monthly_winners_announcer as modulo

    winners_repo = MonthlyWinnersRepository(pool_provider=lambda: clean_db)
    leveling = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "monthly_winners_repo", winners_repo)
    monkeypatch.setattr(modulo, "leveling_repo", leveling)
    return clean_db, winners_repo


async def _inserisci_attivita(pool, guild_id, user_id, period, xp, coins):
    await pool.execute(
        """
        INSERT INTO leveling_activity (guild_id, user_id, period_key, xp, coins)
        VALUES ($1, $2, $3, $4, $5)
        """,
        guild_id, user_id, period, xp, coins,
    )


@pytest.mark.asyncio
async def test_annuncia_il_podio_del_mese_precedente(repos):
    pool, winners_repo = repos
    await winners_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    await _inserisci_attivita(pool, 100, 1, "2026-09", xp=900, coins=10)
    await _inserisci_attivita(pool, 100, 2, "2026-09", xp=500, coins=80)
    await _inserisci_attivita(pool, 100, 3, "2026-10", xp=99999, coins=99999)  # mese SBAGLIATO

    canale = _FakeChannel(500)
    await MonthlyWinnersAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    assert len(canale.sent_embeds) == 1
    embed = canale.sent_embeds[0]
    assert "settembre 2026" in embed.title
    podio_xp = embed.fields[0].value
    assert podio_xp.index("<@1>") < podio_xp.index("<@2>")  # ordine per XP
    assert "<@3>" not in podio_xp  # attività di ottobre esclusa
    podio_coin = embed.fields[1].value
    assert podio_coin.index("<@2>") < podio_coin.index("<@1>")  # ordine per coin

    assert (await winners_repo.get_config(100)).last_announced_period == "2026-09"


@pytest.mark.asyncio
async def test_secondo_tick_nello_stesso_mese_non_ripete(repos):
    pool, winners_repo = repos
    await winners_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    annunciatore = MonthlyWinnersAnnouncer()
    await annunciatore.tick(bot, now=ADESSO)
    await annunciatore.tick(bot, now=ADESSO)

    assert len(canale.sent_embeds) == 1


@pytest.mark.asyncio
async def test_periodo_gia_coperto_alla_configurazione_non_annuncia(repos):
    pool, winners_repo = repos
    # Configurato il 15 ottobre: settembre segnato come già coperto.
    await winners_repo.set_channel(100, channel_id=500, already_covered_period="2026-09")

    canale = _FakeChannel(500)
    await MonthlyWinnersAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    assert canale.sent_embeds == []


@pytest.mark.asyncio
async def test_mese_senza_attivita_annuncia_con_testo_esplicito(repos):
    pool, winners_repo = repos
    await winners_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    canale = _FakeChannel(500)
    await MonthlyWinnersAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    assert "Nessuna attività" in canale.sent_embeds[0].fields[0].value


@pytest.mark.asyncio
async def test_canale_sparito_segna_coperto_per_non_riprovare_ogni_ora(repos):
    pool, winners_repo = repos
    await winners_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    await MonthlyWinnersAnnouncer().tick(_FakeBot(_FakeGuild(100, channel=None)), now=ADESSO)

    assert (await winners_repo.get_config(100)).last_announced_period == "2026-09"


@pytest.mark.asyncio
async def test_errore_di_invio_non_segna_coperto_e_riprova(repos):
    pool, winners_repo = repos
    await winners_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    canale = _FakeChannel(500, fallisce=True)
    await MonthlyWinnersAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    # Errore transitorio: il periodo NON è segnato, il prossimo tick riprova.
    assert (await winners_repo.get_config(100)).last_announced_period == "2026-08"

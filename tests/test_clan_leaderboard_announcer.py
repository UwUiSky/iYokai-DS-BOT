"""
tests/test_clan_leaderboard_announcer.py
============================================
Test di ClanLeaderboardAnnouncer.tick() contro PostgreSQL REALE —
righe di clan_monthly_xp inserite davvero per il mese precedente, non
un repository finto: verifica che il podio annunciato sia quello che
il database restituisce sul serio. Stesso schema di
tests/test_monthly_winners_announcer.py.
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from core.clan_leaderboard_announcer import ClanLeaderboardAnnouncer
from core.repositories.clan_leaderboard_config_repo import ClanLeaderboardConfigRepository
from core.repositories.guild_clan_repo import GuildClanRepository

ADESSO = datetime(2026, 10, 1, 0, 30, tzinfo=timezone.utc)  # periodo da annunciare: 2026-09
ORA = datetime.now(timezone.utc)


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
    import core.clan_leaderboard_announcer as modulo

    config_repo = ClanLeaderboardConfigRepository(pool_provider=lambda: clean_db)
    clan_repo = GuildClanRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "clan_leaderboard_config_repo", config_repo)
    monkeypatch.setattr(modulo, "guild_clan_repo", clan_repo)
    return clean_db, config_repo, clan_repo


async def _crea_clan(clan_repo, guild_id, tag):
    return await clan_repo.create_clan(
        guild_id, tag=tag, name=f"Gilda {tag}", owner_id=1,
        officialize_deadline=ORA + timedelta(hours=24),
    )


async def _inserisci_xp_periodo(pool, clan_id, guild_id, period, xp):
    await pool.execute(
        """
        INSERT INTO clan_monthly_xp (clan_id, guild_id, period_key, xp_gained)
        VALUES ($1, $2, $3, $4)
        """,
        clan_id, guild_id, period, xp,
    )


@pytest.mark.asyncio
async def test_annuncia_la_top3_del_mese_precedente(repos):
    pool, config_repo, clan_repo = repos
    await config_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    primo = await _crea_clan(clan_repo, 100, "ONE")
    secondo = await _crea_clan(clan_repo, 100, "TWO")
    terzo = await _crea_clan(clan_repo, 100, "OLD")
    await _inserisci_xp_periodo(pool, primo, 100, "2026-09", xp=9000)
    await _inserisci_xp_periodo(pool, secondo, 100, "2026-09", xp=500)
    await _inserisci_xp_periodo(pool, terzo, 100, "2026-10", xp=99999)  # mese SBAGLIATO

    canale = _FakeChannel(500)
    await ClanLeaderboardAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    assert len(canale.sent_embeds) == 1
    embed = canale.sent_embeds[0]
    assert "settembre 2026" in embed.title
    assert embed.description.index("ONE") < embed.description.index("TWO")  # ordine per XP
    assert "OLD" not in embed.description  # attività di ottobre esclusa

    assert (await config_repo.get_config(100)).last_announced_period == "2026-09"


@pytest.mark.asyncio
async def test_solo_la_top3_anche_con_piu_gilde(repos):
    pool, config_repo, clan_repo = repos
    await config_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    for i, xp in enumerate([9000, 8000, 7000, 6000], start=1):
        clan_id = await _crea_clan(clan_repo, 100, f"C{i}")
        await _inserisci_xp_periodo(pool, clan_id, 100, "2026-09", xp=xp)

    canale = _FakeChannel(500)
    await ClanLeaderboardAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    assert "C4" not in canale.sent_embeds[0].description


@pytest.mark.asyncio
async def test_secondo_tick_nello_stesso_mese_non_ripete(repos):
    pool, config_repo, clan_repo = repos
    await config_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    annunciatore = ClanLeaderboardAnnouncer()
    await annunciatore.tick(bot, now=ADESSO)
    await annunciatore.tick(bot, now=ADESSO)

    assert len(canale.sent_embeds) == 1


@pytest.mark.asyncio
async def test_periodo_gia_coperto_alla_configurazione_non_annuncia(repos):
    pool, config_repo, clan_repo = repos
    # Configurato il 15 ottobre: settembre segnato come già coperto.
    await config_repo.set_channel(100, channel_id=500, already_covered_period="2026-09")

    canale = _FakeChannel(500)
    await ClanLeaderboardAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    assert canale.sent_embeds == []


@pytest.mark.asyncio
async def test_mese_senza_attivita_annuncia_con_testo_esplicito(repos):
    pool, config_repo, clan_repo = repos
    await config_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    canale = _FakeChannel(500)
    await ClanLeaderboardAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    assert "Nessuna gilda" in canale.sent_embeds[0].description


@pytest.mark.asyncio
async def test_canale_sparito_segna_coperto_per_non_riprovare_ogni_ora(repos):
    pool, config_repo, clan_repo = repos
    await config_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    await ClanLeaderboardAnnouncer().tick(_FakeBot(_FakeGuild(100, channel=None)), now=ADESSO)

    assert (await config_repo.get_config(100)).last_announced_period == "2026-09"


@pytest.mark.asyncio
async def test_errore_di_invio_non_segna_coperto_e_riprova(repos):
    pool, config_repo, clan_repo = repos
    await config_repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    canale = _FakeChannel(500, fallisce=True)
    await ClanLeaderboardAnnouncer().tick(_FakeBot(_FakeGuild(100, canale)), now=ADESSO)

    # Errore transitorio: il periodo NON è segnato, il prossimo tick riprova.
    assert (await config_repo.get_config(100)).last_announced_period == "2026-08"

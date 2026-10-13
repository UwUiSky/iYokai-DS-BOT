"""
tests/test_starboard.py
=======================
NF-08 (#79): starboard. Embed entro i limiti, un solo messaggio in bacheca
per originale, canali NSFW esclusi di default, soglia, comandi.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.starboard as modulo
from cogs.utility.starboard import StarboardCog
from core.repositories.starboard_repo import StarboardRepository
from core.starboard_logic import (
    SOGLIA_MAX,
    contenuto_bacheca,
    costruisci_embed,
    conta_stelle,
)
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_text_channel,
)
from tests.support.percorsi import comando_nel_gruppo


# ---------------------------------------------------------------- logica pura
def test_conta_stelle_ignora_bot_e_autore_di_default():
    utenti = [SimpleNamespace(id=1, bot=False), SimpleNamespace(id=2, bot=False),
              SimpleNamespace(id=3, bot=True), SimpleNamespace(id=9, bot=False)]
    assert conta_stelle(utenti, autore_id=9, voto_autore=False) == 2
    assert conta_stelle(utenti, autore_id=9, voto_autore=True) == 3


def test_conta_stelle_non_conta_due_volte_lo_stesso_utente():
    utenti = [SimpleNamespace(id=1, bot=False), SimpleNamespace(id=1, bot=False)]
    assert conta_stelle(utenti, autore_id=9, voto_autore=False) == 1


def test_embed_rispetta_i_limiti_con_testo_e_allegati_enormi():
    allegati = [f"https://cdn.example/{'a' * 300}{i}.txt" for i in range(30)]
    embed = costruisci_embed(
        testo="x" * 5000, nome_autore="n" * 400, avatar_url=None, link="https://discord.com/x",
        immagine_url=None, allegati=allegati,
    )
    assert len(embed.description) <= 4096
    assert len(embed.author.name) <= 256
    assert all(len(f.value) <= 1024 for f in embed.fields)
    assert len(embed) <= 6000


def test_contenuto_bacheca_mostra_stelle_e_canale():
    testo = contenuto_bacheca("⭐", 7, 123)
    assert "7" in testo and "<#123>" in testo


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return StarboardRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_config_impostata_e_letta(repo):
    assert await repo.get_config(1) is None
    await repo.set_config(1, channel_id=50, threshold=4, emoji="⭐")
    config = await repo.get_config(1)
    assert (config.channel_id, config.threshold, config.enabled, config.allow_nsfw) == (50, 4, True, False)
    await repo.set_threshold(1, 6)
    assert (await repo.get_config(1)).threshold == 6
    await repo.disable(1)
    assert (await repo.get_config(1)).enabled is False


@pytest.mark.asyncio
async def test_set_threshold_senza_config_non_crea_nulla(repo):
    assert await repo.set_threshold(1, 6) is False
    assert await repo.get_config(1) is None


@pytest.mark.asyncio
async def test_un_solo_messaggio_in_bacheca_per_originale(repo):
    assert await repo.claim_post(1, 10, 100, author_id=5) is True
    assert await repo.claim_post(1, 10, 100, author_id=5) is False
    await repo.release_post(100)  # invio fallito: si può riprovare
    assert await repo.get_post(100) is None
    assert await repo.claim_post(1, 10, 100, author_id=5) is True
    await repo.set_board_message(100, 999, stars=3)
    post = await repo.get_post(100)
    assert post.board_message_id == 999 and post.stars == 3
    await repo.release_post(100)  # già pubblicato: resta
    assert await repo.get_post(100) is not None


# -------------------------------------------------------------------------- cog
class _Scena:
    def __init__(self, monkeypatch, *, nsfw=False, stelle=3, soglia=3):
        self.bot = MagicMock()
        self.cog = StarboardCog(self.bot)
        self.guild = fake_guild()
        self.bacheca = fake_text_channel(50, "bacheca")
        self.bacheca.send = AsyncMock(return_value=SimpleNamespace(id=999, edit=AsyncMock()))
        self.canale = fake_text_channel(10, "chat")
        self.canale.is_nsfw = MagicMock(return_value=nsfw)
        self.canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True, read_message_history=True))
        self.autore = fake_member(5, "autore")
        self.messaggio = fake_message(100, author=self.autore, channel=self.canale, guild=self.guild, content="ciao")
        self.messaggio.attachments = []
        self.messaggio.jump_url = "https://discord.com/channels/1/10/100"
        self.messaggio.author.display_name = "autore"
        self.messaggio.author.display_avatar = SimpleNamespace(url="https://a/x.png")
        utenti = [SimpleNamespace(id=1000 + i, bot=False) for i in range(stelle)]

        async def _users(limit=None):
            for u in utenti:
                yield u

        reazione = SimpleNamespace(emoji="⭐", users=_users)
        self.messaggio.reactions = [reazione]
        self.canale.fetch_message = AsyncMock(return_value=self.messaggio)
        self.guild.get_channel = lambda cid: {50: self.bacheca, 10: self.canale}.get(cid)
        self.bot.get_guild = lambda gid: self.guild
        self.config = SimpleNamespace(
            guild_id=self.guild.id, channel_id=50, threshold=soglia, emoji="⭐", enabled=True, allow_nsfw=False,
            self_star=False,
        )
        self.repo = MagicMock()
        self.repo.get_config = AsyncMock(return_value=self.config)
        self.repo.claim_post = AsyncMock(return_value=True)
        self.repo.get_post = AsyncMock(return_value=None)
        self.repo.set_board_message = AsyncMock()
        self.repo.release_post = AsyncMock()
        monkeypatch.setattr(modulo, "starboard_repo", self.repo)
        db_finto = MagicMock()
        db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
        monkeypatch.setattr(modulo, "db", db_finto)


@pytest.mark.asyncio
async def test_sopra_soglia_pubblica_una_volta(monkeypatch):
    s = _Scena(monkeypatch, stelle=3, soglia=3)
    await s.cog.aggiorna(s.guild.id, 10, 100)
    s.bacheca.send.assert_awaited_once()
    assert s.bacheca.send.await_args.kwargs["embed"] is not None
    assert s.bacheca.send.await_args.kwargs["allowed_mentions"].everyone is False
    s.repo.set_board_message.assert_awaited_once_with(100, 999, 3)


@pytest.mark.asyncio
async def test_sotto_soglia_non_pubblica(monkeypatch):
    s = _Scena(monkeypatch, stelle=2, soglia=3)
    await s.cog.aggiorna(s.guild.id, 10, 100)
    s.bacheca.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_canale_nsfw_escluso_di_default(monkeypatch):
    s = _Scena(monkeypatch, nsfw=True, stelle=5, soglia=3)
    await s.cog.aggiorna(s.guild.id, 10, 100)
    s.bacheca.send.assert_not_awaited()
    s.config.allow_nsfw = True
    await s.cog.aggiorna(s.guild.id, 10, 100)
    s.bacheca.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_messaggio_gia_in_bacheca_si_aggiorna_non_si_duplica(monkeypatch):
    s = _Scena(monkeypatch, stelle=4, soglia=3)
    s.repo.claim_post.return_value = False
    esistente = SimpleNamespace(board_message_id=999, stars=3)
    s.repo.get_post.return_value = esistente
    vecchio = SimpleNamespace(edit=AsyncMock())
    s.bacheca.fetch_message = AsyncMock(return_value=vecchio)
    await s.cog.aggiorna(s.guild.id, 10, 100)
    s.bacheca.send.assert_not_awaited()
    vecchio.edit.assert_awaited_once()
    s.repo.set_board_message.assert_awaited_once_with(100, 999, 4)


@pytest.mark.asyncio
async def test_due_aggiornamenti_insieme_pubblicano_una_volta(monkeypatch):
    s = _Scena(monkeypatch, stelle=3, soglia=3)
    visti = set()

    async def claim(guild_id, channel_id, message_id, author_id):
        await asyncio.sleep(0)
        if message_id in visti:
            return False
        visti.add(message_id)
        return True

    s.repo.claim_post = claim
    await asyncio.gather(s.cog.aggiorna(s.guild.id, 10, 100), s.cog.aggiorna(s.guild.id, 10, 100))
    assert s.bacheca.send.await_count == 1


@pytest.mark.asyncio
async def test_invio_fallito_libera_il_posto(monkeypatch):
    s = _Scena(monkeypatch, stelle=3, soglia=3)
    s.bacheca.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=400), "no"))
    await s.cog.aggiorna(s.guild.id, 10, 100)
    s.repo.release_post.assert_awaited_once_with(100)


@pytest.mark.asyncio
async def test_il_messaggio_nella_bacheca_stessa_non_si_ripubblica(monkeypatch):
    s = _Scena(monkeypatch, stelle=9, soglia=3)
    await s.cog.aggiorna(s.guild.id, 50, 100)
    s.bacheca.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_comando_imposta_controlla_i_permessi_nel_canale(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.set_config = AsyncMock()
    canale = fake_text_channel(50, "bacheca")
    canale.permissions_for = MagicMock(
        return_value=discord.Permissions(send_messages=True, embed_links=False)
    )
    interazione = fake_interaction(guild=s.guild)
    await s.cog.imposta.callback(s.cog, interazione, canale, 3, "⭐")
    s.repo.set_config.assert_not_awaited()
    assert "incorporare" in interazione.response.send_message.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_comando_imposta_rifiuta_emoji_non_valida(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.set_config = AsyncMock()
    canale = fake_text_channel(50, "bacheca")
    canale.permissions_for = MagicMock(
        return_value=discord.Permissions(send_messages=True, embed_links=True)
    )
    interazione = fake_interaction(guild=s.guild)
    await s.cog.imposta.callback(s.cog, interazione, canale, 3, "ciao")
    s.repo.set_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_i_comandi_stanno_in_moduli_starboard():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("imposta", "soglia", "disattiva"):
        assert comando_nel_gruppo("moduli", f"starboard {nome}") is not None
    opzioni = {o["name"]: o for o in comando_nel_gruppo("moduli", "starboard soglia").to_dict(bot.tree)["options"]}
    assert opzioni["numero"]["max_value"] == SOGLIA_MAX


@pytest.mark.asyncio
async def test_canale_privato_non_finisce_in_bacheca(monkeypatch):
    """Un canale che @everyone non vede (staff, ticket) non va in una bacheca pubblica."""
    s = _Scena(monkeypatch, stelle=5, soglia=3)
    s.canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=False))
    await s.cog.aggiorna(s.guild.id, 10, 100)
    s.bacheca.send.assert_not_awaited()
    s.repo.claim_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_errore_non_http_libera_il_posto(monkeypatch):
    s = _Scena(monkeypatch, stelle=3, soglia=3)
    s.bacheca.send = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await s.cog.aggiorna(s.guild.id, 10, 100)
    s.repo.release_post.assert_awaited_once_with(100)


@pytest.mark.asyncio
async def test_il_blocco_per_messaggio_evita_il_doppio_invio(monkeypatch):
    """Senza l'asyncio.Lock due eventi insieme passano entrambi da get_post vuoto: qui il
    database non protegge (claim sempre vero), quindi a fermare il secondo è solo il blocco."""
    s = _Scena(monkeypatch, stelle=3, soglia=3)
    stato = {}

    async def get_post(message_id):
        return stato.get(message_id)

    async def invio(*a, **k):
        await asyncio.sleep(0.01)
        return SimpleNamespace(id=999, edit=AsyncMock())

    async def set_board(message_id, board_id, stelle):
        stato[message_id] = SimpleNamespace(board_message_id=board_id, stars=stelle)

    s.repo.get_post, s.repo.set_board_message = get_post, set_board
    s.bacheca.send = AsyncMock(side_effect=invio)
    s.bacheca.fetch_message = AsyncMock(return_value=SimpleNamespace(edit=AsyncMock()))
    await asyncio.gather(s.cog.aggiorna(s.guild.id, 10, 100), s.cog.aggiorna(s.guild.id, 10, 100))
    assert s.bacheca.send.await_count == 1

"""
tests/test_music_r4_blocco1.py
==============================
Catalogo MUS (issue #126) giro r4mus, blocco 1: mescola fisso spento a coda finita,
aggiunta con coda equa da `_play_nel_canale`, annunci (MUS-057, MUS-058), copertina (MUS-060).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import wavelink

from cogs.music.eventi import MusicEventiCog, coda_finita
from cogs.music.player import MusicCog
from core.music_announce_logic import PausaAnnunci, copertina_sicura, embed_brano
from core.music_queue_logic import requester_of
from core.music_settings_logic import MusicSettings, summary_lines
from tests.test_music_queue_cmds import _Coda, _player


class _Traccia:
    """Una traccia finta con `extras` come wavelink: un dizionario diventa un namespace."""

    def __init__(self, titolo, uid=None):
        self.title, self.length, self.author, self.artwork = titolo, 180000, "Artista", None
        self.is_stream = False
        self._extras = SimpleNamespace(requester_id=uid) if uid else SimpleNamespace()

    @property
    def extras(self):
        return self._extras

    @extras.setter
    def extras(self, valore):
        self._extras = SimpleNamespace(**valore)


def _cog_play(player):
    cog = MusicCog(bot=MagicMock())
    cog.bot.music_nodes = MagicMock()
    cog.bot.music_nodes.node_for.return_value = object()
    cog.bot.music_nodes.locale_di.return_value = None
    worker_guild = MagicMock()
    worker_guild.voice_client = player
    return cog, worker_guild


# --------------------- apertura B3: coda equa da `_play_nel_canale` ---------------------
@pytest.mark.asyncio
async def test_play_nel_canale_con_coda_equa_alterna_gli_utenti():
    player = _player([_Traccia("a", 1), _Traccia("b", 1), _Traccia("c", 2)])
    player.playing = True
    player.node = object()
    cog, worker_guild = _cog_play(player)
    cog._cerca = AsyncMock(return_value=([_Traccia("nuovo", 3)], player.node))
    rispondi = AsyncMock()
    imp = MusicSettings(queue_mode="equa")
    esito = await cog._play_nel_canale(1, 3, "nuovo", False, imp, MagicMock(), worker_guild, 9, rispondi)
    assert esito is True
    titoli = [t.title for t in player.queue]
    assert titoli == ["a", "c", "nuovo", "b"]
    assert requester_of(player.queue[2]) == 3


@pytest.mark.asyncio
async def test_play_nel_canale_con_mescola_fisso_non_riordina_per_utente():
    player = _player([_Traccia("a", 1), _Traccia("b", 1)])
    player.playing = True
    player.node = object()
    player.mescola_fisso = True
    cog, worker_guild = _cog_play(player)
    cog._cerca = AsyncMock(return_value=([_Traccia("nuovo", 3)], player.node))
    await cog._play_nel_canale(1, 3, "x", False, MusicSettings(queue_mode="equa"), MagicMock(), worker_guild, 9, AsyncMock())
    assert len(player.queue) == 3  # entra a caso, senza riordino equo


# --------------------- MUS-038: mescola fisso a coda finita ---------------------
@pytest.mark.asyncio
async def test_coda_finita_spegne_il_mescola_fisso():
    player = _player([])
    player.mescola_fisso = True
    cog = MusicEventiCog(bot=MagicMock())
    await cog.su_fine_brano(SimpleNamespace(player=player))
    assert player.mescola_fisso is False


@pytest.mark.asyncio
async def test_con_brani_in_coda_il_mescola_fisso_resta():
    player = _player([_Traccia("a")])
    player.mescola_fisso = True
    await MusicEventiCog(bot=MagicMock()).su_fine_brano(SimpleNamespace(player=player))
    assert player.mescola_fisso is True


def test_coda_finita_non_vale_con_la_ripetizione():
    player = _player([])
    player.queue.mode = wavelink.QueueMode.loop
    assert coda_finita(player) is False
    player.queue.mode = wavelink.QueueMode.normal
    assert coda_finita(player) is True


# --------------------- MUS-060: copertina ---------------------
def test_copertina_solo_https_corta_e_senza_spazi():
    assert copertina_sicura("https://i.scdn.co/a.jpg") == "https://i.scdn.co/a.jpg"
    for male in ("http://x/a.jpg", "javascript:alert(1)", "https://x/a b", None, 5, "https://" + "a" * 400):
        assert copertina_sicura(male) is None


def test_embed_brano_con_copertina():
    t = _Traccia("Titolo")
    t.artwork = "https://x/c.png"
    embed = embed_brano(t)
    assert embed.thumbnail.url == "https://x/c.png"
    assert "Artista" in embed.description
    t.artwork = "http://x/c.png"
    assert embed_brano(t).thumbnail.url is None


# --------------------- MUS-057 / MUS-058: annunci ---------------------
def _evento(guild_id=5):
    player = _player([])
    player.guild = SimpleNamespace(id=guild_id)
    return SimpleNamespace(player=player, track=_Traccia("Ciao"))


def _canale(guild_id=5):
    canale = MagicMock(spec=discord.TextChannel)
    canale.guild = SimpleNamespace(id=guild_id)
    canale.send = AsyncMock()
    return canale


@pytest.mark.asyncio
async def test_annuncio_spento_di_base(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    monkeypatch.setattr("cogs.music.eventi.load_music_settings", AsyncMock(return_value=MusicSettings()))
    await cog.su_inizio_brano(_evento())
    cog.bot.get_channel.assert_not_called()


@pytest.mark.asyncio
async def test_annuncio_nel_canale_scelto_senza_menzioni(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    canale = _canale()
    cog.bot.get_channel.return_value = canale
    imp = MusicSettings(announce=True, announce_channel_id=77)
    monkeypatch.setattr("cogs.music.eventi.load_music_settings", AsyncMock(return_value=imp))
    await cog.su_inizio_brano(_evento())
    canale.send.assert_awaited_once()
    assert canale.send.call_args.kwargs["allowed_mentions"].everyone is False
    assert canale.send.call_args.kwargs["embed"].title.endswith("Ciao")
    # un secondo brano subito dopo: pausa di 3 secondi
    await cog.su_inizio_brano(_evento())
    assert canale.send.await_count == 1


@pytest.mark.asyncio
async def test_annuncio_non_va_in_un_canale_di_un_altro_server(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    canale = _canale(guild_id=999)
    cog.bot.get_channel.return_value = canale
    imp = MusicSettings(announce=True, announce_channel_id=77)
    monkeypatch.setattr("cogs.music.eventi.load_music_settings", AsyncMock(return_value=imp))
    await cog.su_inizio_brano(_evento())
    canale.send.assert_not_called()


@pytest.mark.asyncio
async def test_annuncio_se_il_canale_vieta_non_solleva(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    canale = _canale()
    canale.send.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    cog.bot.get_channel.return_value = canale
    imp = MusicSettings(announce=True, announce_channel_id=77)
    monkeypatch.setattr("cogs.music.eventi.load_music_settings", AsyncMock(return_value=imp))
    await cog.su_inizio_brano(_evento())  # nessuna eccezione


def test_pausa_annunci_un_server_alla_volta():
    p = PausaAnnunci()
    assert p.puo_annunciare(1, 100.0) is True
    assert p.puo_annunciare(1, 101.0) is False
    assert p.puo_annunciare(2, 101.0) is True
    assert p.puo_annunciare(1, 104.0) is True


def test_riepilogo_mostra_gli_annunci():
    assert "spenti" in "\n".join(summary_lines(MusicSettings()))
    righe = "\n".join(summary_lines(MusicSettings(announce=True, announce_channel_id=5)))
    assert "<#5>" in righe

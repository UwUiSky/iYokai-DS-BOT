"""
tests/test_music_defer_allegato.py
==================================
M 8.16: i comandi che parlano con Lavalink chiamano defer() prima.
MUS-056: il bot entra "sordo". MUS-009: /music play con un file allegato.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cogs.music.player import MusicCog


class _Registro:
    def __init__(self) -> None:
        self.eventi: list[str] = []


class _Risposta:
    def __init__(self, reg: _Registro) -> None:
        self.reg = reg

    async def defer(self, **kw) -> None:
        self.reg.eventi.append("defer")

    async def send_message(self, *a, **kw) -> None:
        self.reg.eventi.append("risposta")


class _Seguito:
    def __init__(self, reg: _Registro) -> None:
        self.reg = reg
        self.testi: list[str] = []

    async def send(self, testo=None, **kw) -> None:
        self.reg.eventi.append("followup")
        self.testi.append(testo)


class _Player:
    def __init__(self, reg: _Registro) -> None:
        self.reg = reg
        self.playing = True
        self.paused = True
        self.volume = 50
        self.channel = SimpleNamespace(id=9)
        self.queue = SimpleNamespace(clear=lambda: None)

    async def skip(self, **kw):
        self.reg.eventi.append("lavalink")

    async def stop(self, **kw):
        self.reg.eventi.append("lavalink")

    async def pause(self, valore):
        self.reg.eventi.append("lavalink")

    async def set_volume(self, valore):
        self.reg.eventi.append("lavalink")

    async def disconnect(self, **kw):
        self.reg.eventi.append("lavalink")


def _cog_e_interazione(monkeypatch):
    reg = _Registro()
    player = _Player(reg)
    flotta = SimpleNamespace(release_session=_async_nulla)
    cog = MusicCog(bot=SimpleNamespace(music_fleet=flotta))

    async def _sempre_si(interaction):
        return True

    async def _worker(guild_id, **kw):
        return SimpleNamespace(voice_client=player), None

    cog._controlli_base = _sempre_si
    cog._get_worker_guild = _worker

    async def _impostazioni(db, guild_id):
        return SimpleNamespace(max_volume=200)

    import cogs.music.player as modulo

    monkeypatch.setattr(modulo, "load_music_settings", _impostazioni)
    interazione = SimpleNamespace(
        guild=SimpleNamespace(id=1),
        user=SimpleNamespace(voice=SimpleNamespace(channel=SimpleNamespace(id=9))),
        response=_Risposta(reg),
        followup=_Seguito(reg),
    )
    return cog, interazione, reg


async def _async_nulla(*a, **kw):
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "comando,argomenti",
    [
        ("skip", {}),
        ("stop", {}),
        ("pause", {}),
        ("resume", {}),
        ("volume_set", {"level": 80}),
        ("volume_up", {"amount": 10}),
        ("volume_down", {"amount": 10}),
        ("disconnect", {}),
    ],
)
async def test_defer_prima_di_lavalink(monkeypatch, comando, argomenti):
    cog, interazione, reg = _cog_e_interazione(monkeypatch)
    await getattr(cog, comando).callback(cog, interazione, **argomenti)
    assert reg.eventi.index("defer") < reg.eventi.index("lavalink")
    assert "risposta" not in reg.eventi  # dopo defer() si risponde solo con followup
    assert reg.eventi[-1] == "followup"


@pytest.mark.asyncio
async def test_il_bot_entra_sordo():
    ricevuti = {}

    class _Canale:
        guild = None
        user_limit = 0
        members: list = []

        def permissions_for(self, me):
            return None

        async def connect(self, cls, **kw):
            ricevuti.update(kw)
            return SimpleNamespace(autoplay=None)

    player, errore = await MusicCog(bot=None)._entra_in_canale(_Canale(), object())
    assert errore is None
    assert ricevuti.get("self_deaf") is True


def _interazione_play():
    risposte: list[str] = []

    class _R:
        async def send_message(self, testo, **kw):
            risposte.append(testo)

        async def defer(self, **kw):
            risposte.append("defer")

    return SimpleNamespace(
        guild=SimpleNamespace(id=1),
        user=SimpleNamespace(id=5, voice=SimpleNamespace(channel=SimpleNamespace(id=9))),
        response=_R(),
        followup=SimpleNamespace(send=_async_nulla),
    ), risposte


@pytest.mark.asyncio
async def test_play_con_allegato_audio_accoda_il_suo_url():
    cog = MusicCog(bot=None)
    accodati = []

    async def _sempre_si(interaction):
        return True

    async def _accoda(guild, membro, query, rispondi, **kw):
        accodati.append(query)

    cog._controlli_base = _sempre_si
    cog.accoda = _accoda
    interazione, _ = _interazione_play()
    allegato = SimpleNamespace(url="https://cdn.discordapp.com/a/b/canzone.mp3", content_type="audio/mpeg")

    await cog.play.callback(cog, interazione, allegato=allegato)

    assert accodati == ["https://cdn.discordapp.com/a/b/canzone.mp3"]


@pytest.mark.asyncio
async def test_play_con_allegato_non_audio_rifiuta():
    cog = MusicCog(bot=None)

    async def _sempre_si(interaction):
        return True

    cog._controlli_base = _sempre_si
    interazione, risposte = _interazione_play()
    allegato = SimpleNamespace(url="https://cdn.discordapp.com/a/b/foto.png", content_type="image/png")

    await cog.play.callback(cog, interazione, allegato=allegato)

    assert risposte == ["L'allegato deve essere un file audio o video."]


@pytest.mark.asyncio
async def test_play_senza_query_ne_allegato_rifiuta():
    cog = MusicCog(bot=None)

    async def _sempre_si(interaction):
        return True

    cog._controlli_base = _sempre_si
    interazione, risposte = _interazione_play()
    await cog.play.callback(cog, interazione)
    assert "allega" in risposte[0]

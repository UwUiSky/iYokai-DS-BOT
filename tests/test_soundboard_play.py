"""
tests/test_soundboard_play.py
=============================
NF-35 (#106): effetti sonori in vocale con un bot musicale. Scelta del
suono, pausa per utente, bot già nel canale (la musica continua) o bot
libero che entra con l'audio acceso, suona ed esce.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest

import cogs.fun.soundboard as modulo
from cogs.fun.soundboard import SoundboardCog, _esci_se_inattivo
from core.music_sound_logic import SCELTE_MAX, PausaUtente, Suono, scelte, trova


# ----------------------------------------------------------------- logica
def test_scelte_prima_del_server_e_al_massimo_25():
    suoni = [Suono(i, f"d{i}", False) for i in range(30)] + [Suono(100, "z server", True)]
    risultato = scelte(suoni, "")
    assert len(risultato) == SCELTE_MAX
    assert risultato[0] == ("z server", "s:100")
    assert all(len(e) <= 100 for e, _ in risultato)


def test_trova_dal_valore_o_dal_nome():
    suoni = [Suono(1, "Grillo", False), Suono(2, "grillo", True)]
    assert trova(suoni, "d:1").id == 1
    assert trova(suoni, "GRILLO").id == 2  # a mano: prima quello del server
    assert trova(suoni, "boh") is None


def test_pausa_per_utente():
    adesso = [0.0]
    pausa = PausaUtente(pausa=10, orologio=lambda: adesso[0])
    pausa.segna(1, 5)
    adesso[0] = 4.0
    assert pausa.resta(1, 5) == pytest.approx(6.0)
    assert pausa.resta(1, 6) == 0  # un altro utente non aspetta
    assert pausa.resta(2, 5) == 0  # un altro server nemmeno


# ----------------------------------------------------------------- comando
class _CanaleVoce:
    def __init__(self) -> None:
        self.suoni: list = []
        self.errore = None

    async def send_sound(self, suono):
        if self.errore:
            raise self.errore
        self.suoni.append(suono)


class _WorkerGuild:
    def __init__(self, player=None, sordo=False) -> None:
        self.voice_client = player
        self.me = SimpleNamespace(voice=SimpleNamespace(self_deaf=sordo, channel="canale"))
        self.cambi_voce: list = []
        self.canale = _CanaleVoce()

    def get_channel(self, cid):
        return self.canale

    async def change_voice_state(self, **kw):
        self.cambi_voce.append(kw)


class _Musica:
    def __init__(self, worker_guild) -> None:
        self.worker_guild = worker_guild
        self.ingressi: list = []
        self._lock = asyncio.Lock()

    async def _controlli_base(self, interaction):
        return True

    async def _get_worker(self, guild_id, **kw):
        return SimpleNamespace(name="w1"), self.worker_guild, None

    def _lock_canale(self, g, c):
        return self._lock

    async def _rilascia_se_libero(self, *a):
        pass

    async def _entra_in_canale(self, canale, nodo, volume=None, sordo=True):
        self.ingressi.append(sordo)
        player = SimpleNamespace(channel=canale, playing=False, queue=SimpleNamespace(is_empty=True))
        self.worker_guild.voice_client = player
        return player, None


def _cog(musica, monkeypatch):
    async def _impostazioni(db, gid):
        return SimpleNamespace(allowed_channel_id=None)

    monkeypatch.setattr(modulo, "load_music_settings", _impostazioni)
    monkeypatch.setattr(modulo, "channel_not_allowed", lambda cid, imp: None)
    monkeypatch.setattr(modulo, "_nodo_del_bot", lambda bot, w: "nodo")
    flotta = SimpleNamespace(release_session=_nulla)
    bot = SimpleNamespace(get_cog=lambda n: musica, music_fleet=flotta)
    cog = SoundboardCog(bot)
    suono_server = SimpleNamespace(id=5, name="Applauso", emoji=None, available=True)
    predefinito = SimpleNamespace(id=1, name="Grillo", emoji="🦗")
    cog._predefiniti = [predefinito]
    return cog, suono_server, predefinito


async def _nulla(*a, **kw):
    return None


def _interazione(suoni_server):
    testi: list[str] = []

    async def _rispondi(testo=None, **kw):
        testi.append(testo)

    async def _defer(**kw):
        pass

    interazione = SimpleNamespace(
        guild=SimpleNamespace(id=1, soundboard_sounds=suoni_server),
        user=SimpleNamespace(id=9, voice=SimpleNamespace(channel=SimpleNamespace(id=3))),
        response=SimpleNamespace(send_message=_rispondi, defer=_defer),
        followup=SimpleNamespace(send=_rispondi),
    )
    return interazione, testi


@pytest.mark.asyncio
async def test_bot_gia_nel_canale_suona_senza_fermare_la_musica(monkeypatch):
    player = SimpleNamespace(channel=_CanaleVoce(), playing=True)
    worker_guild = _WorkerGuild(player=player, sordo=True)
    musica = _Musica(worker_guild)
    cog, suono_server, _ = _cog(musica, monkeypatch)
    interazione, testi = _interazione([suono_server])

    await cog.suono.callback(cog, interazione, nome="s:5")

    assert player.channel.suoni == [suono_server]
    assert musica.ingressi == []  # nessun ingresso nuovo
    assert worker_guild.cambi_voce[0]["self_deaf"] is False  # un bot sordo non manda suoni
    assert "Applauso" in testi[-1]
    for task in list(cog._task):
        task.cancel()


@pytest.mark.asyncio
async def test_bot_libero_entra_con_audio_acceso_e_poi_esce(monkeypatch):
    worker_guild = _WorkerGuild(player=None)
    musica = _Musica(worker_guild)
    cog, _, predefinito = _cog(musica, monkeypatch)
    usciti = []

    async def _esci(flotta, wg, gid, cid, attesa=0):
        usciti.append((gid, cid))

    monkeypatch.setattr(modulo, "_esci_se_inattivo", _esci)
    interazione, testi = _interazione([])

    await cog.suono.callback(cog, interazione, nome="Grillo")
    await asyncio.gather(*cog._task)

    assert musica.ingressi == [False]
    assert worker_guild.voice_client.channel.suoni == [predefinito]
    assert usciti == [(1, 3)]


@pytest.mark.asyncio
async def test_pausa_per_utente_dal_comando(monkeypatch):
    worker_guild = _WorkerGuild(player=SimpleNamespace(channel=_CanaleVoce(), playing=True))
    cog, suono_server, _ = _cog(_Musica(worker_guild), monkeypatch)
    interazione, testi = _interazione([suono_server])
    await cog.suono.callback(cog, interazione, nome="s:5")
    await cog.suono.callback(cog, interazione, nome="s:5")
    assert "Aspetta" in testi[-1]
    assert len(worker_guild.voice_client.channel.suoni) == 1


@pytest.mark.asyncio
async def test_senza_permesso_soundboard_messaggio_chiaro(monkeypatch):
    canale = _CanaleVoce()
    canale.errore = discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no")
    worker_guild = _WorkerGuild(player=SimpleNamespace(channel=canale, playing=True))
    cog, suono_server, _ = _cog(_Musica(worker_guild), monkeypatch)
    interazione, testi = _interazione([suono_server])
    await cog.suono.callback(cog, interazione, nome="s:5")
    assert "permesso" in testi[-1]


@pytest.mark.asyncio
async def test_esce_solo_se_nessuno_ha_messo_musica():
    rilasciati = []

    async def _rilascia(gid, cid):
        rilasciati.append((gid, cid))

    flotta = SimpleNamespace(release_session=_rilascia)
    usciti = []

    async def _disconnetti():
        usciti.append(True)

    suona = SimpleNamespace(playing=True, queue=SimpleNamespace(is_empty=True), disconnect=_disconnetti)
    await _esci_se_inattivo(flotta, SimpleNamespace(voice_client=suona), 1, 3, attesa=0)
    assert usciti == [] and rilasciati == []

    fermo = SimpleNamespace(playing=False, queue=SimpleNamespace(is_empty=True), disconnect=_disconnetti)
    await _esci_se_inattivo(flotta, SimpleNamespace(voice_client=fermo), 1, 3, attesa=0)
    assert usciti == [True] and rilasciati == [(1, 3)]


def test_l_invito_dei_bot_musicali_permette_la_soundboard():
    from core.music_fleet import WORKER_INVITE_PERMISSIONS

    assert WORKER_INVITE_PERMISSIONS.use_soundboard
    assert not WORKER_INVITE_PERMISSIONS.administrator

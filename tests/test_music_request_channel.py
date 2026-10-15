"""
tests/test_music_request_channel.py
===================================
NF-19 (#90): canale delle richieste musicali. Logica del player, view
persistente, messaggi del canale che finiscono in coda, bottoni,
aggiornamento del messaggio al massimo ogni pochi secondi.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest
import wavelink

import cogs.music.request_channel as modulo
from cogs.music.request_channel import (
    MusicRequestCog,
    PlayerRichiesteView,
    embed_player,
    esegui_azione,
)
from core.music_request_logic import (
    MODO_CODA,
    MODO_NORMALE,
    MODO_TRACCIA,
    PausaAggiornamenti,
    StatoPlayer,
    contenuto_player,
    prossimo_modo_ripeti,
    query_da_messaggio,
    stato_da_player,
)
from core.repositories.music_request_repo import MusicRequestRepository
from core.ui_base import BaseView


# ----------------------------------------------------------------- logica
def test_titolo_lunghissimo_resta_entro_256():
    stato = StatoPlayer(titolo="x" * 400, durata_ms=1000, prossimi=tuple("y" * 300 for _ in range(9)), in_coda=40)
    contenuto = contenuto_player(stato)
    assert len(contenuto["titolo"]) <= 256
    assert all(len(v) <= 1024 for _, v in contenuto["campi"])
    assert len(embed_player(stato)) <= 6000
    assert "altri 35" in contenuto["campi"][0][1]


def test_senza_sessione_il_player_spiega_come_si_usa():
    assert "scrivi qui" in contenuto_player(None)["descrizione"]


def test_ripeti_a_giro():
    assert prossimo_modo_ripeti(MODO_NORMALE) == MODO_TRACCIA
    assert prossimo_modo_ripeti(MODO_TRACCIA) == MODO_CODA
    assert prossimo_modo_ripeti(MODO_CODA) == MODO_NORMALE


def test_query_da_testo_o_allegato_audio():
    assert query_da_messaggio("  una canzone ", []) == "una canzone"
    assert len(query_da_messaggio("x" * 500, [])) == 300
    assert query_da_messaggio("", [("https://cdn/a.png", "image/png"), ("https://cdn/b.mp3", "audio/mpeg")]) == "https://cdn/b.mp3"
    assert query_da_messaggio("", [("https://cdn/a.png", "image/png")]) is None


def test_stato_letto_dal_player():
    player = SimpleNamespace(
        current=SimpleNamespace(title="Ora", author="Autore", length=60000),
        position=30000, paused=True, channel=SimpleNamespace(name="Musica"),
        queue=_Coda([SimpleNamespace(title="Dopo")], wavelink.QueueMode.loop_all),
    )
    stato = stato_da_player(player)
    assert stato.titolo == "Ora" and stato.in_pausa and stato.modo == MODO_CODA
    assert stato.prossimi == ("Dopo",) and stato.canale_vocale == "Musica"
    assert stato_da_player(SimpleNamespace(current=None)) is None


def test_pausa_tra_aggiornamenti():
    adesso = [100.0]
    pausa = PausaAggiornamenti(pausa=5, orologio=lambda: adesso[0])
    assert pausa.attesa(1) == 0
    pausa.segna(1)
    adesso[0] = 102.0
    assert pausa.attesa(1) == pytest.approx(3.0)
    assert pausa.attesa(2) == 0
    adesso[0] = 106.0
    assert pausa.attesa(1) == 0


# ----------------------------------------------------------------- view
def test_view_persistente_con_cinque_bottoni_su_una_riga():
    view = PlayerRichiesteView()
    assert isinstance(view, BaseView)
    assert view.timeout is None and view.is_persistent()
    bottoni = [c for c in view.children if isinstance(c, discord.ui.Button)]
    assert len(bottoni) == 5
    assert {b.row for b in bottoni} == {0}
    assert all(b.custom_id.startswith("iyokai_musreq_") for b in bottoni)


# ----------------------------------------------------------------- repository
@pytest.fixture
def repo(clean_db):
    return MusicRequestRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_repository_canale_richieste(repo):
    await repo.set_channel(1, 10, 100, set_by=5)
    await repo.set_voice_channel(1, 77)
    assert (await repo.get(1)).voice_channel_id == 77
    await repo.set_channel(1, 11, 101, set_by=5)  # cambio canale: la sessione mostrata si azzera
    conf = await repo.get(1)
    assert (conf.channel_id, conf.message_id, conf.voice_channel_id) == (11, 101, None)
    await repo.set_message(1, 102)
    assert [c.message_id for c in await repo.list_all()] == [102]
    assert (await repo.remove(1)).channel_id == 11
    assert await repo.get(1) is None


# ----------------------------------------------------------------- bottoni
class _Coda(list):
    def __init__(self, voci=(), mode=wavelink.QueueMode.normal):
        super().__init__(voci)
        self.mode = mode
        self.mescolata = False

    @property
    def is_empty(self):
        return not self

    def shuffle(self):
        self.mescolata = True


class _Player:
    def __init__(self) -> None:
        self.paused = False
        self.playing = True
        self.queue = _Coda([1, 2])
        self.azioni: list = []

    async def pause(self, valore):
        self.paused = valore

    async def skip(self, force=True):
        self.azioni.append("skip")

    async def stop(self):
        self.azioni.append("stop")


@pytest.mark.asyncio
async def test_bottoni_sul_player():
    player = _Player()
    assert "pausa" in await esegui_azione(player, "pausa") and player.paused
    assert "Ripreso" in await esegui_azione(player, "pausa") and not player.paused
    await esegui_azione(player, "salta")
    await esegui_azione(player, "mescola")
    assert player.queue.mescolata
    await esegui_azione(player, "ripeti")
    assert player.queue.mode == wavelink.QueueMode.loop
    await esegui_azione(player, "ripeti")
    assert player.queue.mode == wavelink.QueueMode.loop_all
    await esegui_azione(player, "ripeti")
    assert player.queue.mode == wavelink.QueueMode.normal
    await esegui_azione(player, "stop")
    assert player.azioni == ["skip", "stop"] and player.queue.is_empty


# ----------------------------------------------------------------- canale
class _Canale:
    def __init__(self, cid: int) -> None:
        self.id = cid
        self.inviati: list[str] = []

    async def send(self, testo=None, **kw):
        self.inviati.append(testo)
        return SimpleNamespace(id=999)


class _Membro(discord.Member):
    """Eredita da discord.Member (per isinstance) senza il suo costruttore."""

    def __init__(self, voce, bot=False) -> None:
        self._voce = voce
        self._bot = bot

    @property
    def voice(self):
        return self._voce

    @property
    def bot(self):
        return self._bot

    @property
    def mention(self):
        return "@utente"

    @property
    def id(self):
        return 42


class _Messaggio:
    def __init__(self, guild_id, canale, testo, autore):
        self.guild = SimpleNamespace(id=guild_id)
        self.channel = canale
        self.content = testo
        self.attachments = []
        self.author = autore
        self.cancellato = False

    async def delete(self):
        self.cancellato = True


def _messaggio(guild_id, canale, testo, *, bot=False, voce=True):
    stato_voce = SimpleNamespace(channel=SimpleNamespace(id=77)) if voce else None
    return _Messaggio(guild_id, canale, testo, _Membro(stato_voce, bot))


class _Musica:
    def __init__(self, esito=77) -> None:
        self.accodate: list = []
        self.esito = esito

    async def accoda(self, guild, membro, query, rispondi, **kw):
        self.accodate.append(query)
        await rispondi("➕ Aggiunta")
        return self.esito


async def _modulo_attivo(guild_id, modulo_nome):
    return True


def _cog(monkeypatch, repo, musica):
    monkeypatch.setattr(modulo, "music_request_repo", repo)
    monkeypatch.setattr(modulo.db, "is_module_active_for_guild", _modulo_attivo)
    bot = SimpleNamespace(get_cog=lambda n: musica if n == "MusicCog" else None, get_channel=lambda cid: None)
    cog = MusicRequestCog(bot)
    cog.canali = {1: 10}
    return cog


@pytest.mark.asyncio
async def test_un_titolo_scritto_nel_canale_va_in_coda(monkeypatch, repo):
    await repo.set_channel(1, 10, 100, set_by=5)
    musica = _Musica()
    cog = _cog(monkeypatch, repo, musica)
    aggiornati = []

    async def _aggiorna(gid):
        aggiornati.append(gid)

    cog.aggiorna = _aggiorna
    canale = _Canale(10)
    messaggio = _messaggio(1, canale, "never gonna give you up")

    await cog.on_message(messaggio)

    assert musica.accodate == ["never gonna give you up"]
    assert messaggio.cancellato  # il canale resta pulito
    assert canale.inviati == ["@utente ➕ Aggiunta"]
    assert (await repo.get(1)).voice_channel_id == 77
    assert aggiornati == [1]


@pytest.mark.asyncio
async def test_messaggi_ignorati(monkeypatch, repo):
    musica = _Musica()
    cog = _cog(monkeypatch, repo, musica)
    await cog.on_message(_messaggio(1, _Canale(11), "altro canale"))
    await cog.on_message(_messaggio(1, _Canale(10), "da un bot", bot=True))
    await cog.on_message(_messaggio(2, _Canale(10), "altro server"))
    assert musica.accodate == []


@pytest.mark.asyncio
async def test_fuori_dal_vocale_si_spiega_e_si_cancella(monkeypatch, repo):
    musica = _Musica()
    cog = _cog(monkeypatch, repo, musica)
    canale = _Canale(10)
    messaggio = _messaggio(1, canale, "brano", voce=False)
    await cog.on_message(messaggio)
    assert musica.accodate == [] and messaggio.cancellato
    assert "canale vocale" in canale.inviati[0]


@pytest.mark.asyncio
async def test_aggiornamenti_ravvicinati_diventano_uno(monkeypatch, repo):
    cog = _cog(monkeypatch, repo, _Musica())
    cog.pausa = PausaAggiornamenti(pausa=0.05)
    fatti = []

    async def _ora(gid):
        fatti.append(gid)
        cog.pausa.segna(gid)

    cog.aggiorna_ora = _ora
    await cog.aggiorna(1)
    await cog.aggiorna(1)
    await cog.aggiorna(1)
    assert fatti == [1]  # gli altri due aspettano: ne parte uno solo
    await asyncio.sleep(0.1)
    assert fatti == [1, 1]


@pytest.mark.asyncio
async def test_messaggio_player_cancellato_se_ne_manda_uno_nuovo(monkeypatch, repo):
    await repo.set_channel(1, 10, 100, set_by=5)
    cog = _cog(monkeypatch, repo, _Musica())

    class _Parziale:
        async def edit(self, **kw):
            raise discord.NotFound(SimpleNamespace(status=404, reason="x"), "sparito")

    canale = _Canale(10)
    canale.get_partial_message = lambda mid: _Parziale()
    cog.bot.get_channel = lambda cid: canale

    await cog.aggiorna_ora(1)

    assert (await repo.get(1)).message_id == 999


@pytest.mark.asyncio
async def test_due_aggiornamenti_insieme_non_creano_due_player(monkeypatch, repo):
    """Inizio e fine brano nello stesso istante, messaggio player sparito: un solo messaggio nuovo."""
    await repo.set_channel(1, 10, 100, set_by=5)
    cog = _cog(monkeypatch, repo, _Musica())

    class _Parziale:
        async def edit(self, **kw):
            raise discord.NotFound(SimpleNamespace(status=404, reason="x"), "sparito")

    canale = _Canale(10)
    canale.get_partial_message = lambda mid: _Parziale()
    cog.bot.get_channel = lambda cid: canale

    await asyncio.gather(cog.aggiorna(1), cog.aggiorna(1))
    for task in list(cog._in_attesa.values()):
        task.cancel()

    assert len(canale.inviati) == 1


@pytest.mark.asyncio
async def test_richieste_a_raffica_dello_stesso_utente(monkeypatch, repo):
    """Spam nel canale: entro la pausa le richieste si cancellano senza cercare."""
    musica = _Musica()
    cog = _cog(monkeypatch, repo, musica)

    async def _aggiorna(gid):
        pass

    cog.aggiorna = _aggiorna
    canale = _Canale(10)
    messaggi = [_messaggio(1, canale, f"brano {i}") for i in range(5)]
    for m in messaggi:
        await cog.on_message(m)
    assert musica.accodate == ["brano 0"]
    assert all(m.cancellato for m in messaggi)

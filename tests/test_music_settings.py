"""
tests/test_music_settings.py
================================
Impostazioni musicali del server (issue #126: MUS-044, 047, 055, 059, 066).
Logica pura, lettura/scrittura su PostgreSQL vero, comandi /admin musica e i
controlli che le usano.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest

import cogs.music.player as player_module
from cogs.music.player import MusicCog
from cogs.music.settings import MusicSettingsCog
from core.database import Database
from core.music_fleet import handle_inactive_player
from core.music_settings_logic import (
    KEY_ALLOWED_CHANNEL,
    KEY_MAX_VOLUME,
    KEY_STAY_WHEN_QUEUE_ENDS,
    MusicSettings,
    channel_not_allowed,
    clamp_volume,
    load_music_settings,
    save_music_setting,
    summary_lines,
    track_too_long,
)


# ----------------------------- logica pura -----------------------------
def test_volume_tenuto_nel_massimo_del_server():
    s = MusicSettings(max_volume=80)
    assert clamp_volume(150, s) == 80
    assert clamp_volume(50, s) == 50
    assert clamp_volume(-5, s) == 0
    assert clamp_volume(150, MusicSettings()) == 150


def test_durata_massima():
    s = MusicSettings(max_track_minutes=10)
    assert track_too_long(11 * 60_000, s)
    assert not track_too_long(10 * 60_000, s)
    assert not track_too_long(3 * 3600_000, s, is_stream=True)  # le dirette non contano
    assert not track_too_long(3 * 3600_000, MusicSettings())  # 0 = nessun limite


def test_canale_permesso():
    assert channel_not_allowed(5, MusicSettings()) is None
    assert channel_not_allowed(5, MusicSettings(allowed_voice_channel_id=5)) is None
    assert "<#9>" in channel_not_allowed(5, MusicSettings(allowed_voice_channel_id=9))


def test_riepilogo_ha_una_riga_per_impostazione():
    righe = summary_lines(MusicSettings(max_volume=50, max_track_minutes=7, allowed_voice_channel_id=3))
    assert len(righe) == 4
    testo = "\n".join(righe)
    assert "50" in testo and "7 minuti" in testo and "<#3>" in testo
    assert "nessun limite" in "\n".join(summary_lines(MusicSettings()))


# ----------------------------- database vero -----------------------------
@pytest.mark.asyncio
async def test_le_impostazioni_si_salvano_e_si_rileggono():
    database = Database()
    await database.connect()
    guild_id = 700000090
    try:
        await database.run_migrations()
        assert await load_music_settings(database, guild_id) == MusicSettings(guild_id=guild_id)

        await save_music_setting(database, guild_id, KEY_MAX_VOLUME, 60, changed_by=1)
        await save_music_setting(database, guild_id, KEY_STAY_WHEN_QUEUE_ENDS, True, changed_by=1)
        await save_music_setting(database, guild_id, KEY_ALLOWED_CHANNEL, 42, changed_by=1)
        s = await load_music_settings(database, guild_id)
        assert (s.max_volume, s.stay_when_queue_ends, s.allowed_voice_channel_id) == (60, True, 42)

        await save_music_setting(database, guild_id, KEY_ALLOWED_CHANNEL, None, changed_by=1)
        assert (await load_music_settings(database, guild_id)).allowed_voice_channel_id is None
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()


# ----------------------------- comandi -----------------------------
class _Archivio:
    """Le impostazioni in memoria: stessa interfaccia di Database per questi usi."""

    def __init__(self):
        self.valori = {}

    async def get_guild_setting(self, guild_id, key, default=None):
        v = self.valori.get((guild_id, key))
        return default if v is None else v

    async def set_guild_setting(self, guild_id, key, value, changed_by=None):
        self.valori[(guild_id, key)] = value

    async def is_module_active_for_guild(self, guild_id, module):
        return True


class _Risposta:
    def __init__(self):
        self.inviati = []
        self.embeds = []

    async def defer(self, **kw):
        pass

    async def send_message(self, content=None, embed=None, **kw):
        if content is not None:
            self.inviati.append(content)
        if embed is not None:
            self.embeds.append(embed)


class _Utente(discord.Member):
    def __init__(self, canale_id=11):
        self._voce = SimpleNamespace(channel=SimpleNamespace(id=canale_id, members=[]))

    @property
    def voice(self):
        return self._voce

    @property
    def id(self):
        return 1


class _Interazione:
    def __init__(self, canale_id=11):
        self.guild = SimpleNamespace(id=900)
        self.user = _Utente(canale_id)
        self.response = _Risposta()
        self.followup = _Risposta()
        self.followup.send = self.followup.send_message


@pytest.mark.asyncio
async def test_comando_impostazioni_salva_e_il_riepilogo_le_mostra(monkeypatch):
    archivio = _Archivio()
    import cogs.music.settings as modulo

    monkeypatch.setattr(modulo, "db", archivio)
    cog = MusicSettingsCog(bot=None)

    i = _Interazione()
    await cog.impostazioni.callback(
        cog, i, volume_massimo=70, durata_massima=15, resta_a_coda_finita=True,
        canale_vocale=SimpleNamespace(id=33), tutti_i_canali=False,
    )
    s = await load_music_settings(archivio, 900)
    assert (s.max_volume, s.max_track_minutes, s.stay_when_queue_ends) == (70, 15, True)
    assert s.allowed_voice_channel_id == 33

    i = _Interazione()
    await cog.riepilogo.callback(cog, i)
    assert "70" in i.response.embeds[0].description and "<#33>" in i.response.embeds[0].description

    i = _Interazione()
    await cog.impostazioni.callback(cog, i, tutti_i_canali=True)
    assert (await load_music_settings(archivio, 900)).allowed_voice_channel_id is None


@pytest.mark.asyncio
async def test_comando_impostazioni_senza_opzioni_o_con_opzioni_in_conflitto(monkeypatch):
    import cogs.music.settings as modulo

    monkeypatch.setattr(modulo, "db", _Archivio())
    cog = MusicSettingsCog(bot=None)
    i = _Interazione()
    await cog.impostazioni.callback(cog, i)
    assert "almeno un'opzione" in i.response.inviati[0]
    i = _Interazione()
    await cog.impostazioni.callback(cog, i, canale_vocale=SimpleNamespace(id=1), tutti_i_canali=True)
    assert "non entrambi" in i.response.inviati[0]


# ----------------------------- i controlli -----------------------------
def _cog_con_worker(player, monkeypatch, archivio):
    monkeypatch.setattr(player_module, "db", archivio)
    guild_w = SimpleNamespace(voice_client=player, get_channel=lambda cid: object())
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: guild_w)
    rilasci = []

    class _F:
        async def get_worker_for_channel(self, g, c):
            return 1, worker

        async def get_or_assign_worker_for_channel(self, g, c):
            return 1, worker

        async def release_session(self, g, c):
            rilasci.append((g, c))

    return MusicCog(bot=SimpleNamespace(music_fleet=_F(), music_nodes=None)), rilasci


@pytest.mark.asyncio
async def test_il_volume_non_supera_il_massimo_scelto(monkeypatch):
    archivio = _Archivio()
    archivio.valori[(900, KEY_MAX_VOLUME)] = 80
    impostato = []

    async def set_volume(v):
        impostato.append(v)

    player = SimpleNamespace(volume=75, set_volume=set_volume)
    cog, _ = _cog_con_worker(player, monkeypatch, archivio)

    await cog.volume_up.callback(cog, _Interazione(), amount=30)
    await cog.volume_set.callback(cog, _Interazione(), level=200)
    assert impostato == [80, 80]


@pytest.mark.asyncio
async def test_play_fuori_dal_canale_permesso_viene_rifiutato(monkeypatch):
    archivio = _Archivio()
    archivio.valori[(900, KEY_ALLOWED_CHANNEL)] = 99
    cog, rilasci = _cog_con_worker(None, monkeypatch, archivio)
    i = _Interazione(canale_id=11)

    await cog.play.callback(cog, i, query="qualcosa")

    assert "<#99>" in i.followup.inviati[0]
    assert rilasci == []  # nessun worker nemmeno assegnato


@pytest.mark.asyncio
async def test_brano_troppo_lungo_non_entra_in_coda(monkeypatch):
    archivio = _Archivio()
    archivio.valori[(900, "music_max_track_minutes")] = 5
    node = object()
    player = SimpleNamespace(
        node=node, queue=SimpleNamespace(put_wait=AsyncMock()), playing=True, channel=None
    )
    cog, _ = _cog_con_worker(player, monkeypatch, archivio)
    lungo = SimpleNamespace(title="Megamix", length=2 * 3600_000, is_stream=False)
    i = _Interazione()

    with patch.object(cog, "_cerca", new=AsyncMock(return_value=([lungo], node))):
        await cog.play.callback(cog, i, query="megamix")

    assert "fino a 5 minuti" in i.followup.inviati[0]
    player.queue.put_wait.assert_not_called()


@pytest.mark.asyncio
async def test_a_coda_finita_il_bot_resta_se_il_server_lo_vuole(monkeypatch):
    import core.music_fleet as modulo

    archivio = _Archivio()
    monkeypatch.setattr(modulo, "db", archivio)
    disconnessioni, rilasci = [], []

    class _P:
        guild = SimpleNamespace(id=900)
        channel = SimpleNamespace(id=11)

        async def disconnect(self):
            disconnessioni.append(1)

    class _F:
        async def release_session(self, g, c):
            rilasci.append((g, c))

    archivio.valori[(900, KEY_STAY_WHEN_QUEUE_ENDS)] = True
    await handle_inactive_player(_P(), _F())
    assert disconnessioni == [] and rilasci == []

    archivio.valori[(900, KEY_STAY_WHEN_QUEUE_ENDS)] = False
    await handle_inactive_player(_P(), _F())
    assert disconnessioni == [1] and rilasci == [(900, 11)]

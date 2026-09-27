"""
tests/test_music_guard_clauses.py
=====================================
Test di MusicCog._controlli_base() — la parte verificabile senza una
connessione Lavalink/voce vera (vedi il limite dichiarato in cima a
cogs/music/player.py). Contro PostgreSQL reale per il controllo del
modulo attivo.
"""

import discord
import pytest
import wavelink

from cogs.music.player import MODULE_MUSIC, MusicCog
from core.database import Database


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list[discord.Embed] = []

    async def send_message(
        self, content: str | None = None, ephemeral: bool = False, embed: discord.Embed | None = None
    ) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)


class _FakeGuild:
    def __init__(self, guild_id: int, voice_client=None) -> None:
        self.id = guild_id
        self.voice_client = voice_client


class _FakeMember:
    def __init__(self, voice) -> None:
        self.voice = voice


class _FakeRealMember(discord.Member):
    """Eredita davvero da discord.Member (senza chiamarne il
    costruttore) — serve perché _controlli_base fa isinstance(...,
    discord.Member), che un semplice oggetto finto senza questa
    eredità non supererebbe mai. discord.Member.voice è una PROPERTY
    di sola lettura che legge da self.guild._voice_state_for(...) -
    troppo legata agli interni veri per un fake semplice, quindi la
    sovrascriviamo qui con una property nostra invece di provare ad
    assegnare self.voice direttamente (che fallirebbe: "property has
    no setter" — trovato scrivendo questo stesso test)."""

    def __init__(self, voice) -> None:
        self._voice_finta = voice

    @property
    def voice(self):
        return self._voice_finta


class _FakeInteraction:
    def __init__(self, guild_id: int | None, user, voice_client=None) -> None:
        self.guild = _FakeGuild(guild_id, voice_client) if guild_id is not None else None
        self.user = user
        self.response = _FakeResponse()


@pytest.mark.asyncio
async def test_fuori_da_un_server_rifiuta():
    cog = MusicCog(bot=None)
    interaction = _FakeInteraction(guild_id=None, user=_FakeMember(voice=None))

    risultato = await cog._controlli_base(interaction)

    assert risultato is False
    assert "solo dentro un server" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_modulo_disattivato_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000010
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        cog = MusicCog(bot=None)
        interaction = _FakeInteraction(guild_id, user=_FakeMember(voice=None))

        risultato = await cog._controlli_base(interaction)

        assert risultato is False
        assert "non è attivo" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000010")
        await database.close()


@pytest.mark.asyncio
async def test_utente_non_in_vocale_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000011
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        cog = MusicCog(bot=None)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=None))

        risultato = await cog._controlli_base(interaction)

        assert risultato is False
        assert "canale vocale" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000011")
        await database.close()


@pytest.mark.asyncio
async def test_tutti_i_controlli_passano(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000012
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = MusicCog(bot=None)
        risultato = await cog._controlli_base(interaction)

        assert risultato is True
        assert interaction.response.sent_messages == []
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000012")
        await database.close()


class _FakeQueue:
    """Finta wavelink.Queue — solo quello che i comandi nuovi (clear/
    shuffle/loop) leggono o chiamano, senza dipendere dall'oggetto
    vero (che richiede un player Lavalink reale per certe operazioni
    interne)."""

    def __init__(self, items=None, mode: wavelink.QueueMode | None = None) -> None:
        self._items = list(items) if items else []
        self.mode = mode if mode is not None else wavelink.QueueMode.normal
        self.clear_chiamato = False
        self.shuffle_chiamato = False

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    @property
    def is_empty(self) -> bool:
        return len(self._items) == 0

    def clear(self) -> None:
        self.clear_chiamato = True
        self._items = []

    def shuffle(self) -> None:
        self.shuffle_chiamato = True


class _FakeTrack:
    def __init__(self, title: str = "Canzone di prova", length: int = 200_000) -> None:
        self.title = title
        self.length = length


class _FakePlayer:
    def __init__(
        self,
        volume: int = 100,
        queue: "_FakeQueue | None" = None,
        current=None,
        position: int = 0,
        playing: bool = False,
    ) -> None:
        self.volume = volume
        self.set_volume_chiamato_con: int | None = None
        self.queue = queue if queue is not None else _FakeQueue()
        self.current = current
        self.position = position
        self.playing = playing

    async def set_volume(self, value: int) -> None:
        self.set_volume_chiamato_con = value
        self.volume = value


class _FakeWorkerGuild:
    """Il 'guild' visto dal bot WORKER per lo stesso server — un
    oggetto diverso dal guild visto dal bot principale (ogni client
    Discord ha la propria cache), come nell'architettura reale."""

    def __init__(self, voice_client=None) -> None:
        self.voice_client = voice_client


class _FakeWorkerBot:
    def __init__(self, worker_guild: _FakeWorkerGuild) -> None:
        self._worker_guild = worker_guild

    def get_guild(self, guild_id: int):
        return self._worker_guild


class _FakeFleet:
    """Finta MusicFleet — restituisce sempre lo stesso worker/guild
    finto, senza toccare il database (i test di routing VERI, con
    PostgreSQL, sono in tests/test_music_fleet.py)."""

    def __init__(self, worker_bot: _FakeWorkerBot) -> None:
        self._worker_bot = worker_bot
        self.release_guild_chiamato_per: list[int] = []

    async def get_worker_for_guild(self, guild_id: int):
        return 1, self._worker_bot

    async def get_or_assign_worker_for_guild(self, guild_id: int):
        return 1, self._worker_bot

    async def release_guild(self, guild_id: int) -> None:
        self.release_guild_chiamato_per.append(guild_id)


class _FakeBotConFleet:
    def __init__(self, music_fleet: _FakeFleet) -> None:
        self.music_fleet = music_fleet


def _cog_con_player_finto(player_finto: _FakePlayer) -> MusicCog:
    worker_guild = _FakeWorkerGuild(voice_client=player_finto)
    worker_bot = _FakeWorkerBot(worker_guild)
    fleet = _FakeFleet(worker_bot)
    bot = _FakeBotConFleet(fleet)
    return MusicCog(bot=bot)


@pytest.mark.asyncio
async def test_volume_up_non_supera_200(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000013
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        player_finto = _FakePlayer(volume=195)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.volume_up.callback(cog, interaction, amount=10)

        # 195 + 10 = 205, ma il tetto reale è 200 (la scala di
        # Discord, non i 1000 tecnici che Lavalink accetterebbe).
        assert player_finto.set_volume_chiamato_con == 200
        assert "200" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000013")
        await database.close()


@pytest.mark.asyncio
async def test_volume_down_non_scende_sotto_zero(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000014
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        player_finto = _FakePlayer(volume=5)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.volume_down.callback(cog, interaction, amount=10)

        assert player_finto.set_volume_chiamato_con == 0
        assert "0" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000014")
        await database.close()


@pytest.mark.asyncio
async def test_volume_up_dentro_al_range_funziona_normalmente(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000015
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        player_finto = _FakePlayer(volume=100)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.volume_up.callback(cog, interaction, amount=10)

        assert player_finto.set_volume_chiamato_con == 110
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000015")
        await database.close()


@pytest.mark.asyncio
async def test_build_lavalink_nodes_pubblici_per_primi_locale_per_ultimo():
    from cogs.music.player import _build_lavalink_nodes

    nodi = _build_lavalink_nodes()

    # 5 nodi pubblici di default + 1 nodo locale (LAVALINK_HOST/
    # PORT/PASSWORD) sempre in coda, come richiesto: pubblici
    # tentati per primi, il nodo locale/self-hostato SOLO come
    # ultima risorsa se tutti i pubblici falliscono.
    assert len(nodi) == 6
    assert "heavencloud" in nodi[0].uri
    assert "127.0.0.1" in nodi[-1].uri or "localhost" in nodi[-1].uri


@pytest.mark.asyncio
async def test_clear_senza_sessione_attiva_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000016
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        class _FakeFleetVuota:
            async def get_worker_for_guild(self, guild_id: int):
                return None

        cog = MusicCog(bot=_FakeBotConFleet(_FakeFleetVuota()))
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        await cog.clear_queue.callback(cog, interaction)

        assert "nessuna sessione musicale attiva" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000016")
        await database.close()


@pytest.mark.asyncio
async def test_clear_svuota_la_coda_senza_toccare_la_traccia_in_corso(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000017
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        coda = _FakeQueue(items=[_FakeTrack("A"), _FakeTrack("B"), _FakeTrack("C")])
        player_finto = _FakePlayer(queue=coda, current=_FakeTrack("In riproduzione"), playing=True)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.clear_queue.callback(cog, interaction)

        assert coda.clear_chiamato is True
        assert "3" in interaction.response.sent_messages[0]
        assert player_finto.current is not None  # la traccia in corso non è toccata
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000017")
        await database.close()


@pytest.mark.asyncio
async def test_clear_con_coda_già_vuota_lo_dice_senza_errore(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000018
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        player_finto = _FakePlayer(queue=_FakeQueue())
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.clear_queue.callback(cog, interaction)

        assert "già vuota" in interaction.response.sent_messages[0]
        assert player_finto.queue.clear_chiamato is False
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000018")
        await database.close()


@pytest.mark.asyncio
async def test_shuffle_mescola_la_coda(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000019
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        coda = _FakeQueue(items=[_FakeTrack("A"), _FakeTrack("B")])
        player_finto = _FakePlayer(queue=coda)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.shuffle.callback(cog, interaction)

        assert coda.shuffle_chiamato is True
        assert "coda" in interaction.response.sent_messages[0].lower()
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000019")
        await database.close()


@pytest.mark.asyncio
async def test_shuffle_con_coda_vuota_o_con_una_sola_traccia_non_serve(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000020
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        coda = _FakeQueue(items=[_FakeTrack("Unica")])
        player_finto = _FakePlayer(queue=coda)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.shuffle.callback(cog, interaction)

        assert coda.shuffle_chiamato is False
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000020")
        await database.close()


@pytest.mark.asyncio
async def test_loop_track_attiva_e_poi_disattiva(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000021
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        player_finto = _FakePlayer(queue=_FakeQueue())
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.loop_track.callback(cog, interaction)
        assert player_finto.queue.mode == wavelink.QueueMode.loop
        assert "attivato" in interaction.response.sent_messages[0].lower()

        interaction2 = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))
        await cog.loop_track.callback(cog, interaction2)
        assert player_finto.queue.mode == wavelink.QueueMode.normal
        assert "disattivato" in interaction2.response.sent_messages[0].lower()
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000021")
        await database.close()


@pytest.mark.asyncio
async def test_loop_queue_attiva_e_poi_disattiva(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000022
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        player_finto = _FakePlayer(queue=_FakeQueue())
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.loop_queue.callback(cog, interaction)
        assert player_finto.queue.mode == wavelink.QueueMode.loop_all
        assert "attivato" in interaction.response.sent_messages[0].lower()

        interaction2 = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))
        await cog.loop_queue.callback(cog, interaction2)
        assert player_finto.queue.mode == wavelink.QueueMode.normal
        assert "disattivato" in interaction2.response.sent_messages[0].lower()
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000022")
        await database.close()


@pytest.mark.asyncio
async def test_loop_track_e_loop_queue_sono_mutuamente_esclusivi(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000023
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        player_finto = _FakePlayer(queue=_FakeQueue())
        cog = _cog_con_player_finto(player_finto)

        await cog.loop_track.callback(cog, _FakeInteraction(guild_id, user=_FakeRealMember(voice=object())))
        assert player_finto.queue.mode == wavelink.QueueMode.loop

        # Attivare il loop coda mentre il loop traccia è attivo deve
        # sostituirlo, non sommarsi (sono lo stesso campo sottostante).
        await cog.loop_queue.callback(cog, _FakeInteraction(guild_id, user=_FakeRealMember(voice=object())))
        assert player_finto.queue.mode == wavelink.QueueMode.loop_all
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000023")
        await database.close()


@pytest.mark.asyncio
async def test_nowplaying_senza_traccia_in_riproduzione(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000024
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        player_finto = _FakePlayer(queue=_FakeQueue(), current=None, playing=False)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.nowplaying.callback(cog, interaction)

        assert "nessuna traccia" in interaction.response.sent_messages[0].lower()
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000024")
        await database.close()


@pytest.mark.asyncio
async def test_nowplaying_mostra_barra_di_avanzamento(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000025
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        traccia = _FakeTrack("La Mia Canzone", length=200_000)
        coda = _FakeQueue(items=[_FakeTrack("Prossima")])
        player_finto = _FakePlayer(queue=coda, current=traccia, position=100_000, playing=True)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = _cog_con_player_finto(player_finto)
        await cog.nowplaying.callback(cog, interaction)

        assert len(interaction.response.sent_embeds) == 1
        embed = interaction.response.sent_embeds[0]
        assert "La Mia Canzone" in embed.title or "La Mia Canzone" in (embed.description or "")
        testo_completo = f"{embed.title or ''} {embed.description or ''}"
        assert "🔘" in testo_completo
        assert "1" in testo_completo  # 1 traccia in coda dopo quella attuale
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000025")
        await database.close()


def test_wavelink_queue_shuffle_usa_random_shuffle_vero(monkeypatch):
    """
    Garanzia esplicita richiesta dall'utente: /shuffle deve essere
    SEMPRE genuinamente randomico (Fisher-Yates di random.shuffle),
    non un "mix" con pattern nascosti come capita con alcuni bot.
    /shuffle (cog.shuffle) delega direttamente a wavelink.Queue.
    shuffle() senza reimplementare nulla — qui si verifica che
    QUELLO, a sua volta, chiami davvero random.shuffle della
    libreria standard di Python (Fisher-Yates non polarizzato con un
    generatore decente), non un algoritmo proprietario o un ordine
    parzialmente deterministico. Se una futura versione di wavelink
    cambiasse questo internamente, questo test lo segnalerebbe.
    """
    import random as random_module

    coda = wavelink.Queue()
    coda._items = ["a", "b", "c", "d", "e"]

    chiamate: list[list] = []
    shuffle_originale = random_module.shuffle

    def _shuffle_spia(sequenza):
        chiamate.append(list(sequenza))
        shuffle_originale(sequenza)

    monkeypatch.setattr(random_module, "shuffle", _shuffle_spia)
    coda.shuffle()

    assert len(chiamate) == 1
    assert sorted(coda._items) == ["a", "b", "c", "d", "e"]  # stessi elementi, solo mescolati

"""
tests/test_sec10_listener_blacklist.py
==========================================
SEC-10: la blacklist globale deve fermare anche i listener che danno
qualcosa all'utente al di fuori di un'interazione (bottone/modale, già
coperti da core.ui_base.BaseView/BaseModal) — XP testuale, XP vocale,
ruoli da reazione (role menu in modalità reaction), verifica da
reazione.

SEC-21: stessi controlli per l'XP vocale e le coin dei clan, la
creazione del vocale temporaneo entrando nel canale generatore e i
premi `/assegna-lobby` e `/assegna-winner`. Questi test usano il
database vero (clean_db) e la blacklist vera: l'utente viene messo in
blacklist con `blacklist_repo.add_user`, come fa `/owner blacklist`.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, create_autospec

import discord
import pytest
from discord.ext import commands

from cogs.leveling.leveling import LevelingCog
from cogs.security.verify import VerifyCog
from cogs.utility.role_menus import RoleMenuCog
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_voice_channel,
)


class _FakeMember:
    def __init__(self, member_id: int, bot: bool = False) -> None:
        self.id = member_id
        self.bot = bot


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _NonDeveEssereChiamato:
    async def send(self, *args, **kwargs):
        raise AssertionError("Non deve inviare nulla per un utente in blacklist")


class _FakeMessage:
    def __init__(self, author, guild, channel) -> None:
        self.author = author
        self.guild = guild
        self.channel = channel
        self.type = discord.MessageType.default  # un messaggio normale


class TestLevelingOnMessageIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_utente_in_blacklist_non_guadagna_xp_ne_coin(self, monkeypatch):
        import cogs.leveling.leveling as leveling_module

        async def sempre_bloccato(user_id):
            return True

        monkeypatch.setattr(leveling_module.blacklist_repo, "is_user_blacklisted", sempre_bloccato)

        db_finto = AsyncMock()
        monkeypatch.setattr(leveling_module, "db", db_finto)
        leveling_repo_finto = AsyncMock()
        monkeypatch.setattr(leveling_module, "leveling_repo", leveling_repo_finto)

        cog = LevelingCog(bot=None)
        cog.cog_unload()

        messaggio = _FakeMessage(_FakeMember(1), _FakeGuild(100), _NonDeveEssereChiamato())
        await cog.on_message(messaggio)

        # Non deve nemmeno arrivare a controllare se il modulo è
        # attivo: la blacklist va controllata per prima.
        db_finto.is_module_active_for_guild.assert_not_awaited()
        leveling_repo_finto.add_text_xp.assert_not_awaited()


class TestLevelingVoceIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_membro_in_blacklist_non_guadagna_xp_vocale(self, monkeypatch):
        import cogs.leveling.leveling as leveling_module

        class _FakeVoiceState:
            self_deaf = False
            self_mute = False

        class _FakeVoiceMember:
            def __init__(self, member_id: int) -> None:
                self.id = member_id
                self.bot = False
                self.voice = _FakeVoiceState()
                self.mention = f"<@{member_id}>"

        class _FakeVoiceChannel:
            def __init__(self, channel_id: int, members: list) -> None:
                self.id = channel_id
                self.members = members
                self.sent_messages: list[str] = []

            async def send(self, content: str) -> None:
                self.sent_messages.append(content)

        class _FakeVoceGuild:
            def __init__(self, guild_id: int, voice_channels: list) -> None:
                self.id = guild_id
                self.voice_channels = voice_channels
                self.afk_channel = None

        async def bloccato_solo_utente_1(user_id):
            return user_id == 1

        monkeypatch.setattr(
            leveling_module.blacklist_repo, "is_user_blacklisted", bloccato_solo_utente_1
        )

        repo_finto = AsyncMock()
        monkeypatch.setattr(leveling_module, "leveling_repo", repo_finto)

        cog = LevelingCog(bot=None)
        cog.cog_unload()

        membro_bloccato = _FakeVoiceMember(1)
        canale = _FakeVoiceChannel(channel_id=100, members=[membro_bloccato])
        guild = _FakeVoceGuild(guild_id=1, voice_channels=[canale])

        await cog._process_guild_voice_xp(guild)

        repo_finto.add_voice_minute.assert_not_awaited()


class TestRoleMenusReactionIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_utente_in_blacklist_non_ottiene_il_ruolo(self, monkeypatch):
        import cogs.utility.role_menus as role_menus_module

        async def sempre_bloccato(user_id):
            return True

        monkeypatch.setattr(
            role_menus_module.blacklist_repo, "is_user_blacklisted", sempre_bloccato
        )
        db_finto = AsyncMock()
        monkeypatch.setattr(role_menus_module, "db", db_finto)
        repo_finto = AsyncMock()
        monkeypatch.setattr(role_menus_module, "role_menu_repo", repo_finto)

        cog = RoleMenuCog(bot=None)

        payload = type(
            "PayloadFinto",
            (),
            {
                "guild_id": 100,
                "member": _FakeMember(1),
                "message_id": 1,
                "emoji": "🎮",
            },
        )()

        await cog.on_raw_reaction_add(payload)

        db_finto.is_module_active_for_guild.assert_not_awaited()
        repo_finto.get_menu_by_message.assert_not_awaited()


class TestVerifyReactionIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_utente_in_blacklist_non_si_verifica(self, monkeypatch):
        import cogs.security.verify as verify_module

        async def sempre_bloccato(user_id):
            return True

        monkeypatch.setattr(verify_module.blacklist_repo, "is_user_blacklisted", sempre_bloccato)
        db_finto = AsyncMock()
        monkeypatch.setattr(verify_module, "db", db_finto)

        cog = VerifyCog(bot=None)
        cog.run_checks_and_finalize = AsyncMock(
            side_effect=AssertionError("non deve arrivare a verificare l'utente")
        )

        payload = type(
            "PayloadFinto",
            (),
            {
                "guild_id": 100,
                "member": _FakeMember(1),
                "message_id": 1,
                "emoji": verify_module.VERIFY_REACTION_EMOJI,
            },
        )()

        await cog.on_raw_reaction_add(payload)

        db_finto.is_module_active_for_guild.assert_not_awaited()


# ============================================================================
# SEC-21 — database vero, blacklist vera.
# ============================================================================

ID_SERVER = 100
ID_BLOCCATO = 1
ID_PULITO = 2
ID_OWNER_BOT = 999


@pytest.fixture
async def blacklist_vera(monkeypatch, clean_db):
    """Collega il database di test e mette ID_BLOCCATO in blacklist."""
    import core.database as database_module
    from core.repositories.blacklist_repo import blacklist_repo

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    blacklist_repo._user_cache.clear()
    await blacklist_repo.add_user(ID_BLOCCATO, "test SEC-21", added_by=ID_OWNER_BOT)
    # I comandi dell'economia controllano per prima cosa che il modulo sia attivo.
    await database_module.db.set_module_active_for_guild(ID_SERVER, "leveling", True)
    yield
    blacklist_repo._user_cache.clear()
    database_module.db._modules_cache.clear()


def _server_con_vocale(*membri):
    canale = fake_voice_channel(500)
    canale.members = list(membri)
    # Persone normali in un canale normale: né assordate né mutate, e
    # nessun canale AFK (il worker delle gilde applica le regole anti-farm).
    for membro in membri:
        membro.voice.self_deaf = False
        membro.voice.self_mute = False
    server = fake_guild(ID_SERVER)
    server.voice_channels = [canale]
    server.afk_channel = None
    return server


class TestClanVoiceWorkerIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_membro_in_blacklist_non_porta_xp_coin_ne_ore_al_clan(self, blacklist_vera):
        from core.guild_clan_voice_worker import GuildClanVoiceWorker
        from core.repositories.guild_clan_repo import guild_clan_repo

        adesso = datetime.now(timezone.utc)
        clan_id = await guild_clan_repo.create_clan(
            ID_SERVER,
            tag="ABC",
            name="Clan",
            owner_id=ID_BLOCCATO,
            officialize_deadline=adesso + timedelta(hours=24),
        )
        await guild_clan_repo.set_officialized(clan_id)
        prima = await guild_clan_repo.get_clan(clan_id)
        bot = create_autospec(commands.Bot, instance=True)
        bot.guilds = [_server_con_vocale(fake_member(ID_BLOCCATO))]

        await GuildClanVoiceWorker().tick(bot, now=adesso)

        dopo = await guild_clan_repo.get_clan(clan_id)
        assert dopo.total_xp == prima.total_xp
        assert dopo.treasury_balance == prima.treasury_balance
        assert dopo.total_voice_ticks == prima.total_voice_ticks

    @pytest.mark.asyncio
    async def test_il_compagno_di_clan_non_in_blacklist_matura_normalmente(self, blacklist_vera):
        from core.guild_clan_voice_worker import GuildClanVoiceWorker
        from core.repositories.guild_clan_repo import guild_clan_repo

        adesso = datetime.now(timezone.utc)
        clan_id = await guild_clan_repo.create_clan(
            ID_SERVER,
            tag="ABC",
            name="Clan",
            owner_id=ID_BLOCCATO,
            officialize_deadline=adesso + timedelta(hours=24),
        )
        await guild_clan_repo.set_officialized(clan_id)
        await guild_clan_repo.add_member(clan_id, ID_PULITO)
        prima = await guild_clan_repo.get_clan(clan_id)
        bot = create_autospec(commands.Bot, instance=True)
        bot.guilds = [_server_con_vocale(fake_member(ID_BLOCCATO), fake_member(ID_PULITO))]

        await GuildClanVoiceWorker().tick(bot, now=adesso)

        # Un solo tick accreditato (quello del compagno), non due.
        dopo = await guild_clan_repo.get_clan(clan_id)
        assert dopo.total_voice_ticks == prima.total_voice_ticks + 1
        assert dopo.total_xp == prima.total_xp + 10


class TestVocaleTemporaneoIgnoraBlacklist:
    ID_GENERATORE = 300
    ID_CATEGORIA = 400

    async def _entra_nel_generatore(self, id_utente: int):
        """
        Configura i vocali temporanei col comando vero, poi simula
        l'ingresso dell'utente nel canale generatore. Restituisce la
        categoria (per vedere se è stato creato un canale) e il membro.
        """
        from cogs.voice_temp.voice_temp import MODULE_VOICE_TEMP, VoiceTempCog
        from core.database import db

        server = fake_guild(ID_SERVER)
        generatore = fake_voice_channel(self.ID_GENERATORE, "Crea vocale")
        categoria = create_autospec(discord.CategoryChannel, instance=True)
        categoria.id = self.ID_CATEGORIA
        categoria.name = "Vocali"
        categoria.channels = []
        categoria.create_voice_channel.return_value = fake_voice_channel(901, "Canale di utente")
        server.get_channel.return_value = categoria

        cog = VoiceTempCog(create_autospec(commands.Bot, instance=True))
        await db.set_module_active_for_guild(ID_SERVER, MODULE_VOICE_TEMP, True)
        await cog.voicetemp_setup.callback(
            cog, fake_interaction(guild=server), generator=generatore, category=categoria
        )

        membro = fake_member(id_utente)
        membro.guild = server
        membro.display_name = "utente"
        prima = create_autospec(discord.VoiceState, instance=True)
        prima.channel = None
        dopo = create_autospec(discord.VoiceState, instance=True)
        dopo.channel = generatore

        await cog.on_voice_state_update(membro, prima, dopo)
        return categoria, membro

    @pytest.mark.asyncio
    async def test_utente_in_blacklist_non_ottiene_il_vocale_temporaneo(self, blacklist_vera):
        categoria, membro = await self._entra_nel_generatore(ID_BLOCCATO)

        categoria.create_voice_channel.assert_not_awaited()
        membro.move_to.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_utente_non_in_blacklist_ottiene_il_vocale_temporaneo(self, blacklist_vera):
        categoria, membro = await self._entra_nel_generatore(ID_PULITO)

        categoria.create_voice_channel.assert_awaited_once()
        membro.move_to.assert_awaited_once()


class TestPremiDallaCassaIgnoranoBlacklist:
    async def _cassa_con(self, importo: int) -> None:
        from core.repositories.guild_chest_repo import (
            REASON_WEEKLY_PERSONAL_DECAY,
            guild_chest_repo,
        )

        await guild_chest_repo.deposit(ID_SERVER, importo, REASON_WEEKLY_PERSONAL_DECAY)

    def _cog(self) -> LevelingCog:
        cog = LevelingCog(bot=None)
        cog.cog_unload()
        return cog

    @pytest.mark.asyncio
    async def test_assegna_lobby_salta_chi_e_in_blacklist_e_non_lo_fa_pagare(
        self, blacklist_vera
    ):
        from core.repositories.guild_chest_repo import guild_chest_repo
        from core.repositories.leveling_repo import leveling_repo

        await self._cassa_con(1_000)
        server = _server_con_vocale(fake_member(ID_BLOCCATO), fake_member(ID_PULITO))
        interazione = fake_interaction(guild=server)
        cog = self._cog()

        await cog.assegna_lobby.callback(cog, interazione, importo=100)

        assert (await leveling_repo.get_totals(ID_SERVER, ID_BLOCCATO)).coins_total == 0
        assert (await leveling_repo.get_totals(ID_SERVER, ID_PULITO)).coins_total == 100
        # La cassa paga solo per chi riceve davvero il premio.
        assert await guild_chest_repo.get_balance(ID_SERVER) == 900

    @pytest.mark.asyncio
    async def test_assegna_lobby_con_solo_utenti_in_blacklist_non_spende_nulla(
        self, blacklist_vera
    ):
        from core.repositories.guild_chest_repo import guild_chest_repo
        from core.repositories.leveling_repo import leveling_repo

        await self._cassa_con(1_000)
        interazione = fake_interaction(guild=_server_con_vocale(fake_member(ID_BLOCCATO)))
        cog = self._cog()

        await cog.assegna_lobby.callback(cog, interazione, importo=100)

        assert (await leveling_repo.get_totals(ID_SERVER, ID_BLOCCATO)).coins_total == 0
        assert await guild_chest_repo.get_balance(ID_SERVER) == 1_000

    @pytest.mark.asyncio
    async def test_assegna_winner_rifiuta_un_utente_in_blacklist(self, blacklist_vera):
        from core.repositories.guild_chest_repo import guild_chest_repo
        from core.repositories.leveling_repo import leveling_repo

        await self._cassa_con(1_000)
        interazione = fake_interaction(guild=fake_guild(ID_SERVER))
        cog = self._cog()

        await cog.assegna_winner.callback(
            cog, interazione, membro=fake_member(ID_BLOCCATO), importo=100
        )

        assert (await leveling_repo.get_totals(ID_SERVER, ID_BLOCCATO)).coins_total == 0
        assert await guild_chest_repo.get_balance(ID_SERVER) == 1_000
        assert interazione.response.send_message.await_args.kwargs.get("ephemeral") is True

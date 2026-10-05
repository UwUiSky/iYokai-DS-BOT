"""
tests/test_spam_trap_ban_e_appello.py
=====================================
Il percorso intero dello spam-trap, dal messaggio nella trappola
all'appello in DM, per tre correzioni della fase F1:
- LIM-20: il log del ban resta valido anche con molti canali ripuliti;
  il transcript viene mandato allo staff PRIMA di far partire il blocco
  di 24 ore, e non viene allegato se pesa troppo;
- REVIEW §12 (7.3): nel log ci sono la data di ingresso e la data del
  ban.

Tutto viene scritto dal codice di produzione: i canali con
`/spamtrap-setup`, l'indice dei messaggi da `on_message`, caso e
transcript dal ban. Database vero; Discord con i finti fedeli.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import core.ui_base as modulo_ui_base
from cogs.security.spam_trap import MODULE_SPAM_TRAP, SpamTrapCog
from core.repositories.spam_trap_repo import spam_trap_repo
import core.spam_trap_logic as logica_spam_trap
from core.spam_trap_rate_tracker import limite_dm_appello
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_text_channel,
)

GUILD_ID = 100
UTENTE_ID = 42
BOT_ID = 999
INGRESSO = datetime(2026, 9, 1, 18, 30, tzinfo=timezone.utc)


def _errore_http(status: int = 400) -> discord.HTTPException:
    risposta = MagicMock()
    risposta.status = status
    risposta.reason = "Bad Request"
    return discord.HTTPException(risposta, "errore finto di Discord")


def assert_embed_valido(embed: discord.Embed) -> None:
    """I limiti che Discord applica davvero a un embed (LIMITI.md §1.2)."""
    assert len(embed.title or "") <= 256
    assert len(embed.description or "") <= 4096
    assert len(embed.fields) <= 25
    for campo in embed.fields:
        assert 1 <= len(campo.name) <= 256
        assert 1 <= len(campo.value) <= 1024, f"campo «{campo.name}» di {len(campo.value)} caratteri"
    assert len(embed) <= 6000


class Scenario:
    """Un server con lo spam-trap configurato e un utente che ci casca."""

    def __init__(self) -> None:
        self.server = fake_guild(GUILD_ID, "Alpha")
        self.server.filesize_limit = 10 * 1024 * 1024
        self.canali: dict[int, MagicMock] = {}
        self._prossimo_id = 7000
        self.server.create_text_channel.side_effect = self._crea_canale
        self.server.get_channel.side_effect = self.canali.get
        self.server.audit_logs.side_effect = lambda **_kwargs: self._registro_vuoto()
        self.server.invites.return_value = []

        self.bot = create_autospec(commands.Bot, instance=True)
        self.bot.user = fake_member(user_id=BOT_ID, bot=True)
        self.bot.guilds = [self.server]
        self.bot.get_guild.side_effect = lambda guild_id: (
            self.server if guild_id == GUILD_ID else None
        )
        self.cog = SpamTrapCog(self.bot)

        self.utente = fake_member(user_id=UTENTE_ID, name="spammer")
        self.utente.guild = self.server
        self.utente.created_at = INGRESSO - timedelta(days=300)
        self.utente.joined_at = INGRESSO
        self.utente.display_avatar.read = AsyncMock(side_effect=_errore_http(404))
        self.trappola: MagicMock | None = None
        self.log: MagicMock | None = None
        self.thread = create_autospec(discord.Thread, instance=True)

    @staticmethod
    async def _registro_vuoto():
        for voce in ():
            yield voce

    async def _crea_canale(self, name, **_kwargs):
        return self.aggiungi_canale(name)

    def aggiungi_canale(self, nome: str) -> MagicMock:
        self._prossimo_id += 1
        canale = fake_text_channel(self._prossimo_id, nome)

        async def _rileggi(message_id: int) -> MagicMock:
            riletto = fake_message(
                message_id, author=self.utente, channel=canale, guild=self.server
            )
            riletto.content = "free nitro at https://evil.example"
            riletto.attachments = []
            riletto.author.display_name = "spammer"
            return riletto

        canale.fetch_message.side_effect = _rileggi
        self.canali[canale.id] = canale
        return canale

    async def configura(self) -> None:
        interazione = fake_interaction(guild=self.server)
        await self.cog.spamtrap_setup.callback(self.cog, interazione)
        config = await spam_trap_repo.get_config(GUILD_ID)
        self.trappola = self.canali[config.trap_channel_id]
        self.log = self.canali[config.log_channel_id]
        self.log.create_thread.return_value = self.thread
        self.log.send.reset_mock()

    def messaggio(self, canale: MagicMock, message_id: int, quando: datetime) -> MagicMock:
        messaggio = fake_message(message_id, author=self.utente, channel=canale, guild=self.server)
        messaggio.created_at = quando
        return messaggio

    async def scrive_nella_trappola(self) -> None:
        adesso = datetime.now(timezone.utc)
        await self.cog.on_message(self.messaggio(self.trappola, 900_000, adesso))

    def embed_del_log(self) -> discord.Embed:
        self.log.send.assert_awaited_once()
        return self.log.send.call_args.kwargs["embed"]

    def dm(self, testo: str) -> MagicMock:
        """Un DM dell'utente bannato al bot."""
        autore = create_autospec(discord.User, instance=True)
        autore.id = UTENTE_ID
        autore.bot = False
        autore.mention = f"<@{UTENTE_ID}>"
        canale_dm = create_autospec(discord.DMChannel, instance=True)
        messaggio = fake_message(author=autore, channel=canale_dm, content=testo)
        messaggio.guild = None
        return messaggio


@pytest.fixture
async def scenario(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    spam_trap_repo._config_cache.clear()
    limite_dm_appello.azzera()

    async def mai_bloccato(*_args):
        return False

    monkeypatch.setattr(modulo_ui_base.blacklist_repo, "is_user_blacklisted", mai_bloccato)
    monkeypatch.setattr(modulo_ui_base.blacklist_repo, "is_guild_blacklisted", mai_bloccato)

    await database_module.db.set_module_active_for_guild(GUILD_ID, MODULE_SPAM_TRAP, True)
    scenario = Scenario()
    await scenario.configura()
    yield scenario
    limite_dm_appello.azzera()
    spam_trap_repo._config_cache.clear()
    database_module.db._modules_cache.clear()


def _campo(embed: discord.Embed, nome: str) -> str | None:
    return next((campo.value for campo in embed.fields if campo.name == nome), None)


# ====================================================================
# M 3.12 — data di ingresso e data del ban nel log
# ====================================================================
async def test_log_del_ban_con_data_di_ingresso_e_data_del_ban(scenario):
    # Dopo il ban il membro non è più nel server: get_member dà None.
    # La data di ingresso va letta prima.
    prima = datetime.now(timezone.utc)

    await scenario.scrive_nella_trappola()

    scenario.server.ban.assert_awaited_once()
    embed = scenario.embed_del_log()
    assert _campo(embed, "Joined") == discord.utils.format_dt(INGRESSO, style="F")
    data_ban = _campo(embed, "Banned")
    assert data_ban is not None
    secondi = int(data_ban.removeprefix("<t:").removesuffix(":F>"))
    assert int(prima.timestamp()) <= secondi <= int(datetime.now(timezone.utc).timestamp())
    assert_embed_valido(embed)


async def test_data_di_ingresso_sconosciuta_viene_detta(scenario):
    scenario.utente.joined_at = None

    await scenario.scrive_nella_trappola()

    assert _campo(scenario.embed_del_log(), "Joined") == "Unknown"


# ====================================================================
# M 3.10 — log con molti canali ripuliti
# ====================================================================
async def test_sessanta_canali_ripuliti_il_log_resta_valido(scenario):
    dieci_giorni_fa = datetime.now(timezone.utc) - timedelta(days=10)
    for numero in range(60):
        canale = scenario.aggiungi_canale(f"canale-con-un-nome-abbastanza-lungo-{numero:02d}")
        await scenario.cog.on_message(scenario.messaggio(canale, 500_000 + numero, dieci_giorni_fa))

    await scenario.scrive_nella_trappola()

    embed = scenario.embed_del_log()
    assert_embed_valido(embed)
    elenco = _campo(embed, "Deleted messages (7-30 days)")
    assert "#canale-con-un-nome-abbastanza-lungo-00: 1" in elenco
    assert "more channel" in elenco
    # Il conto dei canali non mostrati è giusto.
    mostrati = elenco.count("#canale-con-un-nome")
    assert f"and {60 - mostrati} more channel" in elenco


def test_elenco_canali_corto_resta_intero():
    assert logica_spam_trap.format_deleted_channels({"generale": 3, "off-topic": 1}) == "#generale: 3\n#off-topic: 1"


def test_elenco_canali_lungo_viene_tagliato_a_mille_caratteri():
    canali = {f"canale-{numero:03d}-{'x' * 80}": numero for numero in range(200)}

    testo = logica_spam_trap.format_deleted_channels(canali)

    assert len(testo) <= 1000
    assert testo.endswith("more channel(s)")


async def test_log_che_discord_rifiuta_non_rompe_il_ban(scenario):
    scenario.log.send.side_effect = _errore_http()

    await scenario.scrive_nella_trappola()

    scenario.server.ban.assert_awaited_once()


# ====================================================================
# M 3.10 — transcript: prima si manda, poi parte il blocco di 24 ore
# ====================================================================
async def test_appello_consegnato_con_transcript_e_poi_blocco_di_24_ore(scenario):
    await scenario.scrive_nella_trappola()
    visto_al_momento_dell_invio = []

    async def _send(**kwargs):
        visto_al_momento_dell_invio.append(
            await spam_trap_repo.get_last_appeal(GUILD_ID, UTENTE_ID)
        )

    scenario.thread.send.side_effect = _send
    dm = scenario.dm("It was a mistake, sorry!")

    await scenario.cog.on_message(dm)

    # Quando il messaggio parte per lo staff il blocco NON è ancora segnato.
    assert visto_al_momento_dell_invio == [None]
    assert await spam_trap_repo.get_last_appeal(GUILD_ID, UTENTE_ID) is not None
    invio = scenario.thread.send.call_args.kwargs
    assert [allegato.filename for allegato in invio["files"]] == ["transcript-case-1.html"]
    assert_embed_valido(invio["embed"])
    assert "submitted" in dm.channel.send.call_args.args[0]


async def test_invio_allo_staff_fallito_non_fa_partire_il_blocco(scenario):
    await scenario.scrive_nella_trappola()
    scenario.thread.send.side_effect = _errore_http(413)
    dm = scenario.dm("It was a mistake, sorry!")

    await scenario.cog.on_message(dm)

    assert await spam_trap_repo.get_last_appeal(GUILD_ID, UTENTE_ID) is None
    assert "try again" in dm.channel.send.call_args.args[0].lower()
    # Il thread rimasto vuoto viene tolto.
    scenario.thread.delete.assert_awaited_once()


async def test_transcript_troppo_pesante_non_viene_allegato(scenario):
    await scenario.scrive_nella_trappola()
    scenario.server.filesize_limit = 200  # il transcript vero pesa molto di più
    dm = scenario.dm("It was a mistake, sorry!")

    await scenario.cog.on_message(dm)

    invio = scenario.thread.send.call_args.kwargs
    assert invio["files"] == []
    assert "too large" in invio["embed"].description.lower()
    assert_embed_valido(invio["embed"])
    assert await spam_trap_repo.get_last_appeal(GUILD_ID, UTENTE_ID) is not None


async def test_messaggio_di_appello_lunghissimo_non_rompe_l_embed(scenario):
    await scenario.scrive_nella_trappola()
    dm = scenario.dm("please " * 600)  # 4200 caratteri: più di una descrizione

    await scenario.cog.on_message(dm)

    assert_embed_valido(scenario.thread.send.call_args.kwargs["embed"])

"""
cogs/utility/azzeramento_dati.py
================================
Azzeramento dei dati del bot per un server, con 30 giorni di ritardo (UTL-228, D111): avviso al proprietario all'inizio e
3 giorni prima, sospensione se il proprietario del server cambia, cancellazione allo scadere. I comandi stanno in
`/admin-bot-config reset` (cogs/utility/config_history.py); qui ci sono la finestra di conferma con il nome del server e
i lavori dello scheduler.
Funzioni coperte: SPEC §19 (NF-04), catalogo #128 (UTL-228)
Dipende da: core/azzeramento_dati_logic.py, core/scheduler.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core import azzeramento_dati_logic as logica
from core.bot_ready import attendi_bot_pronto
from core.database import db
from core.i18n import lingua_server, t, testo_per
from core.scheduler import scheduler
from core.ui_base import BaseModal

logger = logging.getLogger("iyokai.azzeramento")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
INTERVALLO_ORE_RETE = 6


def quando(data: datetime) -> str:
    return f"<t:{int(data.timestamp())}:F> (<t:{int(data.timestamp())}:R>)"


class ConfermaNomeModal(BaseModal):
    """Il nome del server scritto a mano: senza, la richiesta non parte (e non riparte)."""

    def __init__(self, titolo: str, etichetta: str, riprendi: bool = False) -> None:
        super().__init__(title=titolo[:45], timeout=300)
        self.riprendi = riprendi
        self.nome = discord.ui.TextInput(label=etichetta[:45], min_length=1, max_length=100, required=True)
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        # Tutto si ricontrolla ora: tra il comando e la finestra il proprietario può essere cambiato.
        if not logica.puo_chiedere(interaction.user.id, guild.owner_id):
            await interaction.response.send_message(await testo_per(interaction, "az_solo_proprietario"), ephemeral=True)
            return
        if not logica.nome_confermato(self.nome.value, guild.name):
            await interaction.response.send_message(await testo_per(interaction, "az_nome_sbagliato"), ephemeral=True)
            return
        if self.riprendi:
            richiesta = await logica.riprendi(guild.id, interaction.user.id, guild.owner_id)
            chiave = "az_ripresa"
        else:
            richiesta = await logica.chiedi(guild.id, interaction.user.id, guild.owner_id)
            chiave = "az_richiesta"
        if richiesta is None:
            await interaction.response.send_message(await testo_per(interaction, "az_gia_richiesta"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, chiave, quando=quando(richiesta.esegui_il), giorni=logica.GIORNI_RITARDO),
            ephemeral=True,
        )
        await avvisa(interaction.client, guild, interaction.user.id, "az_dm_inizio", quando=quando(richiesta.esegui_il))

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.warning("Finestra dell'azzeramento fallita (%s).", type(error).__name__)


async def avvisa(bot, guild, user_id: int, chiave: str, **valori) -> bool:
    """Un messaggio privato al proprietario; se non si può, una riga nel canale dei log del server. Mai solleva."""
    lingua = await lingua_server(guild.id)
    testo = t(chiave, lingua, server=discord.utils.escape_markdown(guild.name)[:100], **valori)
    try:
        utente = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await utente.send(testo, allowed_mentions=NESSUNA_MENZIONE)
        return True
    except (discord.HTTPException, AttributeError):
        pass
    try:
        from core import channel_router as router

        dest = await router.destinazione(guild, router.TIPO_SERVER)
        if dest is not None:
            return await router.invia_a(dest, guild, router.TIPO_SERVER, content=testo[:2000], allowed_mentions=NESSUNA_MENZIONE)
    except Exception:  # noqa: BLE001
        logger.warning("Avviso dell'azzeramento non consegnato (server %s).", guild.id, exc_info=True)
    return False


class AzzeramentoDatiCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        scheduler.register_handler(logica.AZIONE_PREAVVISO, self.preavviso)
        scheduler.register_handler(logica.AZIONE_ESEGUI, self.esegui)
        self._rete.start()

    async def cog_unload(self) -> None:
        self._rete.cancel()

    # ---- lavori dello scheduler: la verità è nel database, non nel payload ----
    async def _controlla_proprietario(self, guild) -> bool:
        """True se la richiesta è stata sospesa perché il proprietario è cambiato (nuovo proprietario avvisato)."""
        sospesa = await logica.sospendi_se_cambiato(guild.id, guild.owner_id)
        if sospesa is None:
            return False
        await avvisa(self.bot, guild, guild.owner_id, "az_dm_sospesa")
        return True

    async def preavviso(self, guild_id: int, user_id: int, payload: dict) -> None:
        richiesta = await logica.azzeramento_repo.get(guild_id)
        if richiesta is None or richiesta.stato != logica.STATO_ATTIVA:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise logica.ServerNonPronto(f"Server {guild_id} non in memoria.")
        if await self._controlla_proprietario(guild):
            return
        await avvisa(self.bot, guild, guild.owner_id, "az_dm_preavviso", quando=quando(richiesta.esegui_il))

    async def esegui(self, guild_id: int, user_id: int, payload: dict) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is not None and await self._controlla_proprietario(guild):
            return
        lingua = await lingua_server(guild_id)
        esito, _ = await logica.esegui(db.pool, guild_id, guild.owner_id if guild else None)
        if esito == logica.ESEGUITA and guild is not None:
            testo = t("az_dm_fatto", lingua, server=discord.utils.escape_markdown(guild.name)[:100])
            try:
                utente = self.bot.get_user(guild.owner_id) or await self.bot.fetch_user(guild.owner_id)
                await utente.send(testo, allowed_mentions=NESSUNA_MENZIONE)
            except discord.HTTPException:
                logger.info("Conferma dell'azzeramento non consegnata (server %s).", guild_id)
        elif esito == logica.SOSPESA and guild is not None:
            await avvisa(self.bot, guild, guild.owner_id, "az_dm_sospesa")

    # ---- proprietario cambiato ----
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if before.owner_id == after.owner_id:
            return
        try:
            await self._controlla_proprietario(after)
        except Exception:  # noqa: BLE001
            logger.warning("Controllo del proprietario fallito (server %s).", after.id, exc_info=True)

    # ---- rete di sicurezza: richieste scadute che lo scheduler non ha eseguito ----
    @tasks.loop(hours=INTERVALLO_ORE_RETE)
    async def _rete(self) -> None:
        for guild_id in await logica.azzeramento_repo.attive_scadute(datetime.now(timezone.utc)):
            try:
                await self.esegui(guild_id, 0, {})
            except Exception:  # noqa: BLE001 - riprova al prossimo giro
                logger.warning("Azzeramento del server %s non eseguito.", guild_id, exc_info=True)

    @_rete.before_loop
    async def _prima(self) -> None:
        await attendi_bot_pronto(self.bot)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AzzeramentoDatiCog(bot))

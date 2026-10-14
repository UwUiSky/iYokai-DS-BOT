"""
cogs/utility/birthdays.py
=========================
Compleanni (NF-26, SPEC §23.4): ogni utente registra giorno e mese (niente anno) e può
cancellarli; il giorno giusto il bot fa gli auguri in un canale e può dare un ruolo per 24 ore.
Comandi: `/level compleanno imposta|rimuovi` (utente), `/moduli compleanni canale|ruolo` (admin).
Il giro è in core/birthday_worker.py ed è ospitato da questo cog.
Funzioni coperte: SPEC §23 (NF-26)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.admin_mentions_logic import utente_puo_pingare_ruoli
from core.birthday_logic import MAX_MESSAGGIO, data_valida
from core.birthday_worker import BIRTHDAY_ROLE_ACTION_TYPE, MODULE_BIRTHDAYS, BirthdayWorker
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.birthday_repo import birthday_repo
from core.role_safety import check_role_assignable
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.birthdays")

_SG_COMPLEANNO = ("compleanno", "Il tuo compleanno")
_SG_COMPLEANNI = ("compleanni", "Auguri di compleanno del server")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre")


class BirthdaysCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._worker = BirthdayWorker(birthday_repo, scheduler)

        @tasks.loop(minutes=30)
        async def _giro() -> None:
            try:
                await self._worker.tick(self.bot)
            except Exception:
                logger.exception("Errore nel giro dei compleanni")

        @_giro.before_loop
        async def _prima() -> None:
            await self.bot.wait_until_ready()

        self._giro = _giro

    async def cog_load(self) -> None:
        await super().cog_load()
        if not self._giro.is_running():
            self._giro.start()

    async def cog_unload(self) -> None:
        self._giro.cancel()
        await super().cog_unload()

    async def handle_ruolo_scaduto(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler: toglie il ruolo del compleanno dopo 24 ore."""
        guild = self.bot.get_guild(guild_id)
        role_id = payload.get("role_id")
        if guild is None or role_id is None:
            return
        membro, ruolo = guild.get_member(user_id), guild.get_role(role_id)
        if membro is None or ruolo is None or ruolo not in membro.roles:
            return
        await membro.remove_roles(ruolo, reason="Compleanno finito")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Chi esce dal server perde il compleanno registrato (dato personale, NF-04)."""
        if member.bot:
            return
        try:
            await birthday_repo.remove_birthday(member.guild.id, member.id)
        except Exception:
            logger.exception("Errore nel cancellare il compleanno di %s", member.id)

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_BIRTHDAYS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    # ---- utente
    @comando_di_gruppo("level", nome="imposta", descrizione="Registra il tuo compleanno (solo giorno e mese).", sottogruppo=_SG_COMPLEANNO)
    @app_commands.describe(giorno="Il giorno", mese="Il mese (1-12)")
    async def imposta(
        self,
        interaction: discord.Interaction,
        giorno: app_commands.Range[int, 1, 31],
        mese: app_commands.Range[int, 1, 12],
    ) -> None:
        if not await self._pronto(interaction):
            return
        if not data_valida(giorno, mese):
            await interaction.response.send_message(f"Il {giorno} {_MESI[mese - 1]} non esiste.", ephemeral=True)
            return
        await birthday_repo.set_birthday(interaction.guild.id, interaction.user.id, giorno, mese)
        await interaction.response.send_message(
            f"Compleanno registrato: {giorno} {_MESI[mese - 1]}. Non salvo l'anno. "
            "Gli auguri partono nella giornata in UTC; lo cancelli con `/level compleanno rimuovi`.",
            ephemeral=True,
        )

    @comando_di_gruppo("level", nome="rimuovi", descrizione="Cancella il tuo compleanno.", sottogruppo=_SG_COMPLEANNO)
    async def rimuovi(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        fatto = await birthday_repo.remove_birthday(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            "Compleanno cancellato." if fatto else "Non avevi un compleanno registrato.", ephemeral=True
        )

    @comando_di_gruppo("level", nome="mostra", descrizione="Mostra il compleanno che hai registrato.", sottogruppo=_SG_COMPLEANNO)
    async def mostra(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        data = await birthday_repo.get_birthday(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"Hai registrato il {data[0]} {_MESI[data[1] - 1]}." if data else "Non hai registrato nessun compleanno.",
            ephemeral=True,
        )

    # ---- admin
    @comando_di_gruppo("moduli", nome="canale", descrizione="Scegli il canale degli auguri (vuoto per spegnerli).", sottogruppo=_SG_COMPLEANNI)
    @app_commands.describe(
        canale="Dove fare gli auguri",
        messaggio=f"Il testo, con {{users}} al posto dei festeggiati (massimo {MAX_MESSAGGIO} caratteri)",
    )
    async def canale(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel | None = None,
        messaggio: app_commands.Range[str, 1, MAX_MESSAGGIO] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        if canale is None:
            await birthday_repo.set_channel(interaction.guild.id, None, None, False)
            await interaction.response.send_message("Auguri di compleanno spenti.", ephemeral=True)
            return
        permessi = canale.permissions_for(interaction.guild.me)
        if not (permessi.view_channel and permessi.send_messages):
            await interaction.response.send_message(
                f"In {canale.mention} al bot servono i permessi per vedere e scrivere.",
                ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
            )
            return
        await birthday_repo.set_channel(
            interaction.guild.id, canale.id, messaggio, utente_puo_pingare_ruoli(interaction.user)
        )
        await interaction.response.send_message(
            f"Auguri in {canale.mention}: un solo messaggio al giorno per tutti i festeggiati.",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("moduli", nome="ruolo", descrizione="Un ruolo per 24 ore a chi compie gli anni (vuoto per toglierlo).", sottogruppo=_SG_COMPLEANNI)
    @app_commands.describe(ruolo="Il ruolo del compleanno")
    async def ruolo(self, interaction: discord.Interaction, ruolo: discord.Role | None = None) -> None:
        if not await self._pronto(interaction):
            return
        if ruolo is not None:
            motivo = check_role_assignable(interaction.guild, ruolo, interaction.user, self_service=True)
            if motivo is not None:
                await interaction.response.send_message(motivo, ephemeral=True)
                return
        await birthday_repo.set_role(interaction.guild.id, ruolo.id if ruolo else None)
        await interaction.response.send_message(
            f"Il ruolo {ruolo.mention} durerà 24 ore." if ruolo else "Nessun ruolo di compleanno.",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_BIRTHDAYS,
            display_name="Compleanni",
            category="community",
            description="Auguri nel canale il giorno del compleanno e ruolo per 24 ore.",
            premium_capable=False,
        )
    )
    cog = BirthdaysCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(BIRTHDAY_ROLE_ACTION_TYPE, cog.handle_ruolo_scaduto)

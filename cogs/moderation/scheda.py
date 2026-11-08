"""
cogs/moderation/scheda.py
=========================
La scheda di moderazione di un utente e i comandi legati: `/mod-casi scheda` (anche per chi è fuori dal server),
il menu col tasto destro «Scheda moderazione» (sull'utente, con 5 tasti rapidi), il menu «Segnala messaggio»
(sul messaggio, per tutti) e `/utility mie-sanzioni` (i propri casi, mai note né casi nascosti).
Le sanzioni dei tasti le esegue il comando vero (warn, timeout, kick, ban) dopo aver controllato il livello.
Funzioni coperte: SPEC §5.7 (MOD-105, MOD-106, MOD-114, MOD-115)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_CASE_SYSTEM, MODULE_REPORT, ensure_module_enabled
from cogs.moderation.report import invia_segnalazione
from cogs.moderation.rischio_staff import testo_rischio_membro
from core import moderation_opzioni, moderation_scheda
from core.command_access import Livello, puo_usare
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.duration_logic import parse_duration
from core.i18n import testo_per
from core.repositories.moderation_repo import moderation_repo
from core.ui_base import BaseModal, BaseView

NOME_MENU_SCHEDA = "Scheda moderazione"
NOME_MENU_SEGNALA = "Segnala messaggio"
SECONDI_VISTA = 600
MAX_MOTIVO = 512
MAX_NOTA = 1000
MAX_SEGNALAZIONE = 500
AZIONI = ("warn", "timeout", "kick", "ban", "nota")
AZIONI_DEL_MODBAN = ("kick", "ban")
_STILE = {
    "warn": discord.ButtonStyle.secondary, "timeout": discord.ButtonStyle.secondary,
    "kick": discord.ButtonStyle.danger, "ban": discord.ButtonStyle.danger, "nota": discord.ButtonStyle.primary,
}


async def _testi_scheda(interaction: discord.Interaction) -> dict[str, str]:
    chiavi = ("titolo", "account", "entrato", "fuori", "attivi", "nessuno", "totali", "ultimi", "note", "rischio")
    return {c: await testo_per(interaction, f"scheda_{c}") for c in chiavi}


async def costruisci_scheda(interaction: discord.Interaction, utente: discord.abc.User) -> discord.Embed:
    """La scheda di `utente` nel server di `interaction`; il rischio c'è solo per chi è nel server."""
    guild = interaction.guild
    membro = utente if isinstance(utente, discord.Member) else guild.get_member(utente.id)
    rischio = await testo_rischio_membro(guild, membro) if membro is not None else None
    dati = await moderation_scheda.leggi_scheda(guild.id, utente, membro, rischio)
    return moderation_scheda.embed_scheda(dati, await _testi_scheda(interaction))


class ModuloAzione(BaseModal):
    """La finestra di un tasto rapido: motivo (e durata per timeout e ban), oppure il testo di una nota."""

    def __init__(self, cog, azione: str, utente: discord.abc.User, titolo: str, etichette: dict[str, str]) -> None:
        super().__init__(title=titolo[:45], timeout=SECONDI_VISTA)
        self.cog = cog
        self.azione = azione
        self.utente = utente
        self.motivo = discord.ui.TextInput(
            label=etichette["nota" if azione == "nota" else "motivo"][:45],
            style=discord.TextStyle.paragraph,
            max_length=MAX_NOTA if azione == "nota" else MAX_MOTIVO,
        )
        self.add_item(self.motivo)
        self.durata = None
        if azione in ("timeout", "ban"):
            self.durata = discord.ui.TextInput(label=etichette["durata"][:45], max_length=20, required=azione == "timeout")
            self.add_item(self.durata)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        livello = Livello.MODBAN if self.azione in AZIONI_DEL_MODBAN else Livello.MOD
        if not await puo_usare(interaction, livello):  # il livello può cambiare mentre la finestra è aperta
            await interaction.response.send_message(await testo_per(interaction, "scheda_serve_staff"), ephemeral=True)
            return
        if self.azione == "nota":
            await moderation_repo.add_note(interaction.guild.id, self.utente.id, interaction.user.id, self.motivo.value.strip())
            await interaction.response.send_message(await testo_per(interaction, "scheda_nota_salvata"), ephemeral=True)
            return
        membro = interaction.guild.get_member(self.utente.id)
        if membro is None:
            await interaction.response.send_message(await testo_per(interaction, "scheda_non_nel_server", nome=self.utente.name), ephemeral=True)
            return
        argomenti: dict = {"member": membro, "reason": self.motivo.value.strip()}
        cog_azioni = interaction.client.get_cog("ModerationActionsCog")
        comando = {"warn": "warn", "timeout": "timeout", "kick": "kick", "ban": "ban"}[self.azione]
        if self.durata is not None and self.durata.value.strip():
            try:
                secondi = parse_duration(self.durata.value)
            except ValueError as errore:
                await interaction.response.send_message(str(errore), ephemeral=True)
                return
            argomenti["duration"] = f"{secondi}s"
            if self.azione == "ban":
                comando = "tempban"
        await getattr(cog_azioni, comando).callback(cog_azioni, interaction, **argomenti)


class VistaScheda(BaseView):
    """Sotto la scheda: Warn, Timeout, Kick, Ban, Nota (una riga di 5)."""

    def __init__(self, cog, autore_id: int, utente: discord.abc.User, nel_server: bool, puo_modban: bool, etichette: dict[str, str]) -> None:
        super().__init__(timeout=SECONDI_VISTA)
        self.cog = cog
        self.autore_id = autore_id
        self.utente = utente
        self.etichette = etichette
        for azione in AZIONI:
            bottone = discord.ui.Button(
                label=etichette[azione][:45], style=_STILE[azione], custom_id=f"mq:{azione}:{utente.id}", row=0,
                disabled=(azione != "nota" and not nel_server) or (azione in AZIONI_DEL_MODBAN and not puo_modban),
            )
            bottone.callback = self._crea_callback(azione)
            self.add_item(bottone)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(await testo_per(interaction, "scheda_serve_staff"), ephemeral=True)
            return False
        return True

    def _crea_callback(self, azione: str):
        async def callback(interaction: discord.Interaction) -> None:
            titolo = await testo_per(interaction, "scheda_modulo_titolo", azione=self.etichette[azione], nome=self.utente.name)
            await interaction.response.send_modal(ModuloAzione(self.cog, azione, self.utente, titolo, self.etichette))

        return callback


class ModuloSegnala(BaseModal):
    """MOD-105: un solo campo, il motivo (fino a 500 caratteri)."""

    def __init__(self, messaggio: discord.Message, titolo: str, campo: str) -> None:
        super().__init__(title=titolo[:45], timeout=SECONDI_VISTA)
        self.messaggio = messaggio
        self.motivo = discord.ui.TextInput(label=campo[:45], style=discord.TextStyle.paragraph, min_length=3, max_length=MAX_SEGNALAZIONE)
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await invia_segnalazione(interaction, self.messaggio.author, self.motivo.value.strip(), None, self.messaggio)


class ModerationSchedaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu_scheda = app_commands.ContextMenu(name=NOME_MENU_SCHEDA, callback=self.menu_scheda)
        self._menu_scheda.guild_only = True
        self._menu_scheda.default_permissions = discord.Permissions(moderate_members=True)
        self._menu_segnala = app_commands.ContextMenu(name=NOME_MENU_SEGNALA, callback=self.menu_segnala)
        self._menu_segnala.guild_only = True

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.tree.add_command(self._menu_scheda)
        self.bot.tree.add_command(self._menu_segnala)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(NOME_MENU_SCHEDA, type=discord.AppCommandType.user)
        self.bot.tree.remove_command(NOME_MENU_SEGNALA, type=discord.AppCommandType.message)
        await super().cog_unload()

    # ---------------------------------------------------------------- MOD-106
    @comando_di_gruppo("mod-casi", nome="scheda", descrizione="La scheda di un utente: date, casi, note e rischio (anche fuori dal server).")
    @app_commands.describe(utente="L'utente, anche se non è nel server")
    async def scheda(self, interaction: discord.Interaction, utente: discord.User) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        await interaction.response.defer(ephemeral=True)
        embed = await costruisci_scheda(interaction, utente)
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    # ---------------------------------------------------------------- MOD-115
    async def menu_scheda(self, interaction: discord.Interaction, utente: discord.User) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if not await puo_usare(interaction, Livello.MOD):
            await interaction.response.send_message(await testo_per(interaction, "scheda_serve_staff"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = await costruisci_scheda(interaction, utente)
        etichette = {a: await testo_per(interaction, f"scheda_azione_{a}") for a in AZIONI}
        etichette["motivo"] = await testo_per(interaction, "scheda_modulo_motivo")
        etichette["durata"] = await testo_per(interaction, "scheda_modulo_durata")
        etichette["nota"] = await testo_per(interaction, "scheda_modulo_nota")
        nel_server = interaction.guild.get_member(utente.id) is not None
        vista = VistaScheda(self, interaction.user.id, utente, nel_server, await puo_usare(interaction, Livello.MODBAN), etichette)
        await interaction.followup.send(embed=embed, view=vista, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    # ---------------------------------------------------------------- MOD-105
    async def menu_segnala(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        if not await ensure_module_enabled(interaction, MODULE_REPORT):
            return
        if messaggio.guild is None or messaggio.guild.id != interaction.guild.id:
            await interaction.response.send_message(await testo_per(interaction, "segnala_altro_server"), ephemeral=True)
            return
        if messaggio.author.id == interaction.user.id:
            await interaction.response.send_message(await testo_per(interaction, "segnala_se_stesso"), ephemeral=True)
            return
        titolo = await testo_per(interaction, "segnala_modulo_titolo")
        campo = await testo_per(interaction, "segnala_modulo_motivo")
        await interaction.response.send_modal(ModuloSegnala(messaggio, titolo, campo))

    # ---------------------------------------------------------------- MOD-114
    @comando_di_gruppo("utility", nome="mie-sanzioni", descrizione="Le sanzioni che hai ricevuto in questo server (solo tu le vedi).")
    async def mie_sanzioni(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "miesanz_nessuna"), ephemeral=True)
            return
        opzioni = await moderation_opzioni.leggi(guild.id)
        if not opzioni.utente_vede_casi:
            await interaction.response.send_message(await testo_per(interaction, "miesanz_spento"), ephemeral=True)
            return
        casi = await moderation_repo.list_visible_cases_for_user(guild.id, interaction.user.id, moderation_scheda.MAX_MIE)
        if not casi:
            await interaction.response.send_message(await testo_per(interaction, "miesanz_nessuna"), ephemeral=True)
            return
        staff_di = await testo_per(interaction, "miesanz_staff_di", server=guild.name) if opzioni.anonimo else None
        nomi = {}
        for c in casi:
            membro = guild.get_member(c.moderator_id)
            nomi[c.moderator_id] = membro.display_name if membro else str(c.moderator_id)
        embed = discord.Embed(
            title=(await testo_per(interaction, "miesanz_titolo", server=guild.name))[:256],
            description=moderation_scheda.righe_mie_sanzioni(casi, staff_di, nomi)[:4000],
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationSchedaCog(bot))

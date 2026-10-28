"""
cogs/user_app/impostazioni.py
=============================
Impostazioni personali e storico dei propri comandi di iYokai App (SPEC §B.10, §D.7): `/impostazioni
mostra|lingua|risposte|dm|storico|profilo` e `/storico elenco|azzera`. Lo storico si salva solo se la persona lo
accende (90 giorni, 100 righe). Si carica solo sul client dell'app (core/user_app_bot.py).
Funzioni coperte: SPEC §B.10, §D.7 (NF-36, #107)
Dipende da: core/repositories/user_app_repo.py, core/user_app_impostazioni.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.i18n import imposta_lingua_utente, lingua_interazione, lingua_server, lingua_utente, t, testo_per
from core.repositories.user_app_repo import MAX_STORICO, user_app_repo
from core.user_app_bot import e_istanza_app

logger = logging.getLogger("iyokai.user_app")

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
RIGHE_STORICO = 25


def nome_comando(comando) -> str:
    """Il nome con la barra per un comando slash (compreso il sotto-comando), il nome del menu per un menu del tasto destro."""
    if isinstance(comando, app_commands.ContextMenu):
        return comando.name
    return f"/{comando.qualified_name}"


class ImpostazioniCog(commands.Cog):
    impostazioni = app_commands.Group(
        name="impostazioni", description="Le tue impostazioni personali di iYokai App.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )
    storico = app_commands.Group(
        name="storico", description="Gli ultimi comandi che hai usato (solo se lo accendi).",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, comando) -> None:
        """Salva il comando nello storico, ma solo per chi l'ha acceso (e non salva mai i comandi dello storico)."""
        try:
            if not (await user_app_repo.impostazioni(interaction.user.id)).storico:
                return
            nome = nome_comando(comando)
            if nome.startswith("/storico") or nome.startswith("/impostazioni"):
                return
            await user_app_repo.registra_comando(interaction.user.id, nome, interaction.guild_id)
        except Exception:  # noqa: BLE001 - lo storico non deve mai disturbare il comando
            logger.warning("Storico dei comandi non scritto.", exc_info=True)

    # ---------------------------------------------------------------- impostazioni
    @impostazioni.command(name="mostra", description="Le tue impostazioni di adesso.")
    async def mostra(self, interaction: discord.Interaction) -> None:
        s = await user_app_repo.impostazioni(interaction.user.id)
        lingua = await lingua_interazione(interaction)
        mia = await lingua_utente(interaction.user.id)
        si, no = t("app_si", lingua), t("app_no", lingua)
        righe = [
            f"**{t('app_imp_lingua', lingua)}:** {mia or t('app_imp_lingua_server', lingua)}",
            f"**{t('app_imp_risposte', lingua)}:** {t('app_imp_private', lingua) if s.risposte_private else t('app_imp_pubbliche', lingua)}",
            f"**{t('app_imp_dm', lingua)}:** {si if s.dm_ok else no}",
            f"**{t('app_imp_storico', lingua)}:** {si if s.storico else no}",
            f"**{t('app_imp_profilo', lingua)}:** {si if s.profilo_pubblico else no}",
        ]
        embed = discord.Embed(title=t("app_imp_titolo", lingua), description="\n".join(righe), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @impostazioni.command(name="lingua", description="Italiano o inglese per le risposte che vedi solo tu.")
    @app_commands.describe(lingua="La lingua; «server» torna a quella del server")
    @app_commands.choices(lingua=[
        app_commands.Choice(name="Italiano", value="it"), app_commands.Choice(name="English", value="en"),
        app_commands.Choice(name="Server", value="server"),
    ])
    async def lingua(self, interaction: discord.Interaction, lingua: app_commands.Choice[str]) -> None:
        salvata = await imposta_lingua_utente(interaction.user.id, lingua.value)
        if salvata:
            testo = t("lingua_utente_impostata", salvata, lingua=salvata)
        else:
            testo = t("lingua_utente_azzerata", await lingua_server(None))
        await interaction.response.send_message(testo, ephemeral=True)

    async def _imposta(self, interaction: discord.Interaction, campo: str, valore: bool, chiave: str) -> None:
        await user_app_repo.imposta(interaction.user.id, campo, valore)
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)

    @impostazioni.command(name="risposte", description="Le risposte dei comandi le vedi solo tu, o le vedono tutti.")
    @app_commands.describe(private="Sì: solo tu (consigliato). No: tutti nel canale")
    async def risposte(self, interaction: discord.Interaction, private: bool) -> None:
        await self._imposta(interaction, "risposte_private", private, "app_imp_risposte_private" if private else "app_imp_risposte_pubbliche")

    @impostazioni.command(name="dm", description="L'app può scriverti in DM (promemoria, ricordamelo)?")
    @app_commands.describe(attivi="Sì: promemoria e avvisi in DM. No: niente DM")
    async def dm(self, interaction: discord.Interaction, attivi: bool) -> None:
        await self._imposta(interaction, "dm_ok", attivi, "app_imp_dm_si" if attivi else "app_imp_dm_no")

    @impostazioni.command(name="storico", description="Salvare i tuoi ultimi comandi (spegnere cancella lo storico).")
    @app_commands.describe(attivo="Sì: salvo gli ultimi comandi. No: non salvo e cancello quelli che ho")
    async def storico_acceso(self, interaction: discord.Interaction, attivo: bool) -> None:
        await self._imposta(interaction, "storico", attivo, "app_imp_storico_si" if attivo else "app_imp_storico_no")

    @impostazioni.command(name="profilo", description="Gli altri vedono il tuo profilo globale (livello, clan, medaglie).")
    @app_commands.describe(visibile="Sì: chi guarda il tuo profilo vede anche i dati di tutti i server. No: solo tu")
    async def profilo(self, interaction: discord.Interaction, visibile: bool) -> None:
        await self._imposta(interaction, "profilo_pubblico", visibile, "app_imp_profilo_si" if visibile else "app_imp_profilo_no")

    # ---------------------------------------------------------------- storico
    @storico.command(name="elenco", description="I tuoi ultimi comandi.")
    async def elenco(self, interaction: discord.Interaction) -> None:
        lingua = await lingua_interazione(interaction)
        if not (await user_app_repo.impostazioni(interaction.user.id)).storico:
            await interaction.response.send_message(t("app_storico_spento", lingua), ephemeral=True)
            return
        righe = await user_app_repo.storico(interaction.user.id, RIGHE_STORICO)
        if not righe:
            await interaction.response.send_message(t("app_storico_vuoto", lingua), ephemeral=True)
            return
        dove = lambda g: t("app_storico_dm", lingua) if g is None else t("app_storico_server", lingua, server=g)  # noqa: E731
        corpo = "\n".join(f"{discord.utils.format_dt(r['used_at'], 'R')} · `{r['comando'][:60]}` · {dove(r['guild_id'])}" for r in righe)
        embed = discord.Embed(title=t("app_storico_titolo", lingua), description=corpo[:4000], color=discord.Color.blurple())
        embed.set_footer(text=t("app_storico_nota", lingua, massimo=MAX_STORICO))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @storico.command(name="azzera", description="Cancella il tuo storico dei comandi.")
    async def azzera(self, interaction: discord.Interaction) -> None:
        cancellate = await user_app_repo.azzera_storico(interaction.user.id)
        await interaction.response.send_message(await testo_per(interaction, "app_storico_azzerato", quante=cancellate), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if e_istanza_app(bot):
        await bot.add_cog(ImpostazioniCog(bot))

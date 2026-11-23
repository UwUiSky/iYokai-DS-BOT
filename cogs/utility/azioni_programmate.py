"""
cogs/utility/azioni_programmate.py
==================================
`/admin-automazioni programma`: azioni sicure fatte più tardi (UTL-111): dare o togliere un ruolo, scrivere un messaggio,
sbloccare un canale. Fino a 5 per server, da 1 minuto a 30 giorni. Mai comandi di moderazione o di amministrazione.
I permessi di chi l'ha messa si controllano due volte: ora e quando scatta.
Funzioni coperte: UTL-111
Dipende da: core/azioni_programmate.py, core/azioni_sicure.py
"""

from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core import azioni_programmate as ap
from core import azioni_sicure as az
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.duration_logic import parse_duration
from core.i18n import testo_per
from core.role_safety import check_role_assignable
from core.scheduler import scheduler

NESSUNA_MENZIONE = discord.AllowedMentions.none()


class AzioniProgrammateCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        scheduler.register_handler(ap.AZIONE_SCHEDULER, self._scatta)

    async def _scatta(self, guild_id: int, user_id: int, payload: dict) -> None:
        motivo = await ap.alla_scadenza(self.bot, guild_id, user_id, payload)
        if motivo == "server non raggiungibile":
            raise RuntimeError(motivo)  # la riga non è stata presa: lo scheduler riprova più tardi
        # gli altri motivi (permessi persi, ruolo cambiato) non si ritentano: sono già nel log

    @comando_di_gruppo(
        "admin-automazioni",
        nome="programma",
        descrizione="Programma un'azione sicura per più tardi (ruolo, messaggio, sblocco canale): fino a 5.",
    )
    @app_commands.describe(
        operazione="Aggiungi, elenco o togli", tipo="Che azione (per «aggiungi»)", tra="Fra quanto: 30m, 12h, 7d (da 1 minuto a 30 giorni)",
        ruolo="Il ruolo da dare o togliere", utente="A chi dare o togliere il ruolo", canale="Il canale (messaggio o sblocco)",
        testo="Il testo del messaggio (massimo 200, senza menzioni)", numero="L'azione da togliere (il numero dell'elenco)",
    )
    @app_commands.choices(
        operazione=[app_commands.Choice(name=n, value=n) for n in ("aggiungi", "elenco", "togli")],
        tipo=[app_commands.Choice(name=n.replace("_", " "), value=n) for n in az.TIPI_PROGRAMMATE],
    )
    @richiedi(Livello.ADMIN)
    async def programma(
        self,
        interaction: discord.Interaction,
        operazione: app_commands.Choice[str],
        tipo: app_commands.Choice[str] | None = None,
        tra: app_commands.Range[str, 2, 6] | None = None,
        ruolo: discord.Role | None = None,
        utente: discord.Member | None = None,
        canale: discord.TextChannel | None = None,
        testo: app_commands.Range[str, 1, az.MAX_TESTO] | None = None,
        numero: app_commands.Range[int, 1, 2**31 - 1] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if operazione.value == "elenco":
            righe = await ap.elenco(guild.id)
            if not righe:
                await interaction.response.send_message(await testo_per(interaction, "programma_nessuna"), ephemeral=True)
                return
            import json

            testo_elenco = "\n".join(
                f"`{r['id']}` {discord.utils.format_dt(r['quando'], 'R')} · "
                f"{(json.loads(r['azione']) if isinstance(r['azione'], str) else r['azione'])['tipo'].replace('_', ' ')}"
                for r in righe
            )
            await interaction.response.send_message(testo_elenco[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        if operazione.value == "togli":
            ok = numero is not None and await ap.togli(guild.id, numero)
            await interaction.response.send_message(await testo_per(interaction, "programma_tolta" if ok else "programma_non_trovata"), ephemeral=True)
            return
        try:
            azione = az.da_dict(
                {"tipo": tipo.value if tipo else None, "ruolo_id": ruolo.id if ruolo else None, "canale_id": canale.id if canale else None,
                 "testo": testo, "utente_id": utente.id if utente else None},
                ammessi=az.TIPI_PROGRAMMATE,
            )
            if azione.tipo in ("dai_ruolo", "togli_ruolo") and utente is None:
                raise az.AzioneNonValida("serve la persona")
            attesa = timedelta(seconds=parse_duration(tra)) if tra else None
        except (az.AzioneNonValida, ValueError) as errore:
            await interaction.response.send_message(await testo_per(interaction, "tag_azione_non_valida", motivo=str(errore)), ephemeral=True)
            return
        if attesa is None:
            await interaction.response.send_message(await testo_per(interaction, "programma_serve_tra"), ephemeral=True)
            return
        # I permessi si controllano subito (e di nuovo quando scatta).
        permessi = interaction.user.guild_permissions
        motivo = None
        if ruolo is not None:
            motivo = (None if permessi.manage_roles else "serve «Gestire i ruoli»") or check_role_assignable(guild, ruolo, interaction.user, self_service=False)
        elif azione.tipo == "sblocca_canale" and not permessi.manage_channels:
            motivo = "serve «Gestire i canali»"
        elif azione.tipo == "messaggio" and canale is not None and not canale.permissions_for(interaction.user).send_messages:
            motivo = "non puoi scrivere in quel canale"
        if motivo is not None:
            await interaction.response.send_message(await testo_per(interaction, "tag_azione_non_valida", motivo=motivo), ephemeral=True)
            return
        try:
            nuovo = await ap.programma(guild.id, interaction.user.id, azione, attesa)
        except ap.TroppeProgrammate:
            await interaction.response.send_message(await testo_per(interaction, "programma_piene", massimo=az.MAX_PROGRAMMATE), ephemeral=True)
            return
        except ap.AttesaNonValida:
            await interaction.response.send_message(await testo_per(interaction, "programma_attesa"), ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "programma_ok", numero=nuovo), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AzioniProgrammateCog(bot))

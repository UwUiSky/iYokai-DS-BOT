"""
cogs/security/lockdown.py
=========================
Blocco totale del server e modalita' panico (NF-29, #100).
Comandi: `/mod blocco attiva|togli` (chi gestisce il server) e
`/security panico attiva|togli|configura|stato` (amministratori).
Il lavoro con Discord sta in `core/lockdown_service.py`, le regole in
`core/lockdown_logic.py`, lo stato in `core/repositories/lockdown_repo.py`.
Funzioni coperte: SPEC §23 (NF-29), catalogo SIC-011..015

Differenza tra i due: il blocco e' una scelta dello staff; il panico e' lo
stesso blocco piu' le regole d'emergenza (ping ai ruoli scelti, comandi di moderazione
riservati a proprietario e fidati, sblocco automatico, avvio da solo dopo un
attacco di anti-nuke o anti-raid). Modulo sempre gratuito.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import lockdown_service as servizio
from core.bot_ready import attendi_bot_pronto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.lockdown_logic import (
    MAX_CATEGORIE_ESCLUSE,
    MAX_MOTIVO,
    MAX_RUOLI_AVVISO,
    MAX_SBLOCCO_MINUTI,
    STATO_IN_RIAPERTURA,
    TIPO_BLOCCO,
    TIPO_PANICO,
    puo_agire_in_panico,
)
from core.repositories.lockdown_repo import lockdown_repo
from core.repositories.security_repo import security_repo

logger = logging.getLogger("iyokai.lockdown")

Motivo = app_commands.Range[str, 3, MAX_MOTIVO]


def _gestisce(interaction: discord.Interaction) -> bool:
    permessi = interaction.user.guild_permissions
    return permessi.administrator or permessi.manage_guild


async def _rifiuta_senza_gestione(interaction: discord.Interaction) -> bool:
    if _gestisce(interaction):
        return False
    await interaction.response.send_message(
        "Serve il permesso «Gestire il server» per bloccare o riaprire il server.", ephemeral=True
    )
    return True


async def _puo_riaprire_panico(interaction: discord.Interaction) -> bool:
    """Un panico con i comandi riservati lo toglie solo chi, in quel panico, ha poteri (SIC-012)."""
    guild = interaction.guild
    if not servizio.panico_riservato(guild.id):
        return True
    impostazioni = await security_repo.get_settings(guild.id)
    if puo_agire_in_panico(interaction.user.id, guild.owner_id, impostazioni.anti_nuke):
        return True
    await interaction.response.send_message(
        "Il panico e' acceso con i comandi riservati: lo toglie solo il proprietario o un utente fidato "
        "dell'anti-nuke.",
        ephemeral=True,
    )
    return False


class LockdownCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self._sblocco_automatico.start()
        await super().cog_load()

    async def cog_unload(self) -> None:
        self._sblocco_automatico.cancel()
        await super().cog_unload()

    # ------------------------------------------------------------ lavoro comune
    async def _attiva(self, interaction: discord.Interaction, tipo: str, motivo: str | None) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)  # 500 canali: ben oltre i 3 secondi
        try:
            esito = await servizio.attiva(
                interaction.guild, tipo=tipo, avviato_da=interaction.user.id,
                motivo=motivo or "nessun motivo indicato", riepilogo_in=interaction.channel,
            )
        except Exception:
            logger.exception("Blocco non riuscito (server %s)", interaction.guild.id)
            await interaction.followup.send(
                "Errore imprevisto: il blocco potrebbe essere rimasto a meta'. "
                "Usa «togli» per riaprire tutto com'era.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(esito.messaggio[:2000], ephemeral=True)

    async def _togli(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            esito = await servizio.togli(interaction.guild, riepilogo_in=interaction.channel)
        except Exception:
            logger.exception("Sblocco non riuscito (server %s)", interaction.guild.id)
            await interaction.followup.send(
                "Errore imprevisto durante la riapertura. Rilancia «togli»: riprende da dove si e' fermato.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(esito.messaggio[:2000], ephemeral=True)

    # ------------------------------------------------------------ /mod blocco
    @comando_di_gruppo(
        "mod",
        nome="attiva",
        descrizione="Blocca tutti i canali, gli inviti e gli ingressi del server.",
        sottogruppo=("blocco", "Blocco totale del server."),
    )
    @app_commands.describe(motivo="Perche' si blocca il server")
    async def blocco_attiva(self, interaction: discord.Interaction, motivo: Motivo | None = None) -> None:
        if await _rifiuta_senza_gestione(interaction):
            return
        await self._attiva(interaction, TIPO_BLOCCO, motivo)

    @comando_di_gruppo(
        "mod",
        nome="togli",
        descrizione="Riapre il server com'era prima del blocco.",
        sottogruppo=("blocco", "Blocco totale del server."),
    )
    async def blocco_togli(self, interaction: discord.Interaction) -> None:
        if await _rifiuta_senza_gestione(interaction) or not await _puo_riaprire_panico(interaction):
            return
        await self._togli(interaction)

    # ------------------------------------------------------------ /security panico
    @comando_di_gruppo(
        "security",
        nome="attiva",
        descrizione="Accende il panico: blocco totale con le regole d'emergenza.",
        sottogruppo=("panico", "Modalita' panico: blocco d'emergenza del server."),
    )
    @app_commands.describe(motivo="Perche' si accende il panico")
    async def panico_attiva(self, interaction: discord.Interaction, motivo: Motivo | None = None) -> None:
        await self._attiva(interaction, TIPO_PANICO, motivo)

    @comando_di_gruppo(
        "security",
        nome="togli",
        descrizione="Spegne il panico e riapre il server com'era.",
        sottogruppo=("panico", "Modalita' panico: blocco d'emergenza del server."),
    )
    async def panico_togli(self, interaction: discord.Interaction) -> None:
        if not await _puo_riaprire_panico(interaction):
            return
        await self._togli(interaction)

    @comando_di_gruppo(
        "security",
        nome="configura",
        descrizione="Scelte del panico: ruoli avvisati, categorie escluse, sblocco, regole.",
        sottogruppo=("panico", "Modalita' panico: blocco d'emergenza del server."),
    )
    @app_commands.describe(
        aggiungi_ruolo="Ruolo da avvisare con un ping quando scatta il panico",
        togli_ruolo="Ruolo da non avvisare piu'",
        escludi_categoria="Categoria che il blocco non tocca",
        includi_categoria="Categoria da bloccare di nuovo",
        sblocco_minuti="Dopo quanti minuti il panico si spegne da solo (0 = mai)",
        solo_proprietario="Durante il panico la moderazione solo a proprietario e fidati",
        automatico="Il panico parte da solo dopo un attacco di anti-nuke o anti-raid",
    )
    async def panico_configura(
        self,
        interaction: discord.Interaction,
        aggiungi_ruolo: discord.Role | None = None,
        togli_ruolo: discord.Role | None = None,
        escludi_categoria: discord.CategoryChannel | None = None,
        includi_categoria: discord.CategoryChannel | None = None,
        sblocco_minuti: app_commands.Range[int, 0, MAX_SBLOCCO_MINUTI] | None = None,
        solo_proprietario: bool | None = None,
        automatico: bool | None = None,
    ) -> None:
        guild = interaction.guild
        settings = await security_repo.get_settings(guild.id)
        # Come per le soglie dell'anti-nuke: chi puo' spegnere la difesa la gestisce solo il proprietario.
        if interaction.user.id != guild.owner_id and not puo_agire_in_panico(
            interaction.user.id, guild.owner_id, settings.anti_nuke
        ):
            await interaction.response.send_message(
                "Solo il proprietario o un utente fidato dell'anti-nuke cambia le scelte del panico.",
                ephemeral=True,
            )
            return
        config = await lockdown_repo.get_config(guild.id)
        ruoli = [r for r in config.ruoli_avviso if not (togli_ruolo and r == togli_ruolo.id)]
        if aggiungi_ruolo is not None and aggiungi_ruolo.id not in ruoli:
            ruoli.append(aggiungi_ruolo.id)
        categorie = [c for c in config.categorie_escluse if not (includi_categoria and c == includi_categoria.id)]
        if escludi_categoria is not None and escludi_categoria.id not in categorie:
            categorie.append(escludi_categoria.id)
        if len(ruoli) > MAX_RUOLI_AVVISO:
            await interaction.response.send_message(
                f"Al massimo {MAX_RUOLI_AVVISO} ruoli da avvisare: toglierne qualcuno prima.", ephemeral=True
            )
            return
        if len(categorie) > MAX_CATEGORIE_ESCLUSE:
            await interaction.response.send_message(
                f"Al massimo {MAX_CATEGORIE_ESCLUSE} categorie escluse: includerne qualcuna prima.",
                ephemeral=True,
            )
            return
        nuova = replace(
            config,
            ruoli_avviso=tuple(ruoli),
            categorie_escluse=tuple(categorie),
            sblocco_auto_minuti=config.sblocco_auto_minuti if sblocco_minuti is None else sblocco_minuti,
            solo_proprietario=config.solo_proprietario if solo_proprietario is None else solo_proprietario,
            automatico=config.automatico if automatico is None else automatico,
        )
        await lockdown_repo.save_config(guild.id, nuova)
        await interaction.response.send_message(self._testo_config(nuova), ephemeral=True)

    @staticmethod
    def _testo_config(c) -> str:
        ruoli = ", ".join(f"<@&{r}>" for r in c.ruoli_avviso) or "nessuno"
        categorie = ", ".join(f"<#{x}>" for x in c.categorie_escluse) or "nessuna"
        return (
            f"**Ruoli avvisati**: {ruoli}\n**Categorie escluse**: {categorie}\n"
            f"**Sblocco automatico**: {f'dopo {c.sblocco_auto_minuti} minuti' if c.sblocco_auto_minuti else 'no'}\n"
            f"**Moderazione riservata durante il panico**: {'si' if c.solo_proprietario else 'no'}\n"
            f"**Parte da solo dopo un attacco**: {'si' if c.automatico else 'no'}"
        )[:1900]

    @comando_di_gruppo(
        "security",
        nome="stato",
        descrizione="Mostra se il server e' bloccato e le scelte del panico.",
        sottogruppo=("panico", "Modalita' panico: blocco d'emergenza del server."),
    )
    async def panico_stato(self, interaction: discord.Interaction) -> None:
        stato = await lockdown_repo.get_stato(interaction.guild.id)
        config = await lockdown_repo.get_config(interaction.guild.id)
        if stato is None:
            riga = "**Il server non e' bloccato.**"
        else:
            nome = "panico" if stato.tipo == TIPO_PANICO else "blocco totale"
            riga = (
                f"**Attivo: {nome}** ({stato.stato.replace('_', ' ')}) dal "
                f"<t:{int(stato.avviato_il.timestamp())}:f>, avviato da <@{stato.avviato_da}>."
            )
            if stato.finisce_il is not None:
                riga += f" Si riapre <t:{int(stato.finisce_il.timestamp())}:R>."
        await interaction.response.send_message(
            f"{riga}\n\n{self._testo_config(config)}"[:2000],
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ------------------------------------------------------------ sblocco automatico (SIC-015)
    @tasks.loop(seconds=60)
    async def _sblocco_automatico(self) -> None:
        try:
            scaduti = await lockdown_repo.scaduti(datetime.now(timezone.utc))
        except Exception:
            logger.exception("Errore nello sblocco automatico del panico")
            return
        for guild_id in scaduti:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            try:
                stato = await lockdown_repo.get_stato(guild_id)
                # Una riapertura rimasta a meta' si riprova ogni minuto, senza ripetere l'annuncio del fallimento.
                ritenta = stato is not None and stato.stato == STATO_IN_RIAPERTURA
                await servizio.togli(guild, ritenta=ritenta)
            except Exception:
                logger.exception("Errore nello sblocco automatico del panico (server %s)", guild_id)

    @_sblocco_automatico.before_loop
    async def _prima_dello_sblocco(self) -> None:
        await attendi_bot_pronto(self.bot)
        try:
            await servizio.carica_panici()  # i server rimasti in panico prima del riavvio
        except Exception:
            logger.exception("Panici in corso non riletti dal database")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LockdownCog(bot))

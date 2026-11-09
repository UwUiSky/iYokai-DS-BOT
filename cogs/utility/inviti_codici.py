"""
cogs/utility/inviti_codici.py
=============================
Codici d'invito (D69 B12): elenco dei codici di un membro, nome e ruolo per un codice, invito nuovo senza
scadenza, cancellazione a gruppi (un invito al secondo, ci si ferma al primo rifiuto di Discord).
Comandi: `/admin-inviti codici|etichetta|crea|cancella` e `/level inviti codici`.
Funzioni coperte: catalogo UTL-166, 167, 174, 180, 181
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility.invites import MODULE_INVITES, _SG_INVITI
from core import invite_service
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.invite_tracker import invite_tracker
from core.inviti_codici_logic import (
    CODICI_PER_PAGINA, MAX_CANCELLAZIONI_PER_GIRO, MAX_ETICHETTA, MAX_INVITI_SERVER, MAX_USI_INVITO,
    da_cancellare, da_invito, pagine, riga_codice,
)
from core.repositories.invite_links_repo import invite_links_repo
from core.repositories.inviti_extra_repo import TroppeEtichette, inviti_extra_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.inviti_codici")

PAUSA_CANCELLAZIONE = 1.0  # secondi tra un invito e l'altro
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
SECONDI_CONFERMA = 120


async def inviti_del_server(guild: discord.Guild):
    """Tutti gli inviti del server, o None se al bot manca «Gestire il server»."""
    try:
        return await guild.invites()
    except (discord.Forbidden, discord.HTTPException):
        return None


async def motivo_ruolo_non_dato(interaction: discord.Interaction, ruolo: discord.Role) -> str | None:
    """Chiave del catalogo se il ruolo non si può legare a un invito, None se va bene. Chi configura non può
    dare un ruolo più alto del suo (a meno che sia il proprietario del server)."""
    guild = interaction.guild
    if ruolo.is_default() or ruolo.managed:
        return "invites_ruolo_non_valido"
    if not guild.me.guild_permissions.manage_roles or ruolo.position >= guild.me.top_role.position:
        return "invites_ruolo_troppo_alto_per_il_bot"
    utente = interaction.user
    if utente.id != guild.owner_id and ruolo.position >= getattr(utente.top_role, "position", 0):
        return "invites_ruolo_troppo_alto_per_te"
    return None


class ConfermaCancellazione(BaseView):
    """Mostra quanti inviti si cancellano e aspetta il sì di chi ha dato il comando."""

    def __init__(self, cog: "InvitiCodiciCog", proprietario: int, guild: discord.Guild, codici: list[str]) -> None:
        super().__init__(timeout=SECONDI_CONFERMA)
        self.cog = cog
        self.proprietario = proprietario
        self.guild = guild
        self.codici = codici

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await testo_per(interaction, "invites_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Cancella", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.guild.id in self.cog.in_corso:
            await interaction.response.send_message(await testo_per(interaction, "invites_cancellazione_in_corso"), ephemeral=True)
            return
        self.stop()
        self.cog.in_corso.add(self.guild.id)
        try:
            await interaction.response.edit_message(
                content=await testo_per(interaction, "invites_cancellazione_parte", n=len(self.codici)), view=None
            )
            fatti, fermato = await self.cog.cancella_a_uno_al_secondo(self.guild, self.codici, interaction.user.id)
        finally:
            self.cog.in_corso.discard(self.guild.id)
        chiave = "invites_cancellazione_fermata" if fermato else "invites_cancellazione_finita"
        await interaction.followup.send(await testo_per(interaction, chiave, fatti=fatti, totale=len(self.codici)), ephemeral=True)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "invites_annullato"), view=None)


class InvitiCodiciCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.in_corso: set[int] = set()

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_INVITES):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    async def _elenco(self, interaction: discord.Interaction, membro: discord.Member, pagina: int) -> None:
        await interaction.response.defer(ephemeral=True)
        inviti = await inviti_del_server(interaction.guild)
        if inviti is None:
            await interaction.followup.send(await testo_per(interaction, "invites_serve_gestire_server"))
            return
        suoi = [da_invito(i) for i in inviti if getattr(i.inviter, "id", None) == membro.id]
        if not suoi:
            await interaction.followup.send(
                await testo_per(interaction, "invites_nessun_codice", membro=membro.mention), allowed_mentions=_NESSUNA_MENZIONE
            )
            return
        totale_pagine = pagine(len(suoi))
        pagina = min(pagina, totale_pagine)
        parte = suoi[(pagina - 1) * CODICI_PER_PAGINA: pagina * CODICI_PER_PAGINA]
        etichette = await inviti_extra_repo.etichette_di(interaction.guild.id, [i.codice for i in parte])
        righe = [riga_codice(i, etichette.get(i.codice, (None, None))[0]) for i in parte]
        titolo = await testo_per(
            interaction, "invites_codici_titolo", membro=membro.mention, totale=len(suoi), pagina=pagina, pagine=totale_pagine
        )
        await interaction.followup.send(f"{titolo}\n" + "\n".join(righe), allowed_mentions=_NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-inviti", nome="codici", descrizione="I codici d'invito creati da un membro, a pagine da 10.")
    @app_commands.describe(membro="Di chi vedere i codici", pagina="Pagina dell'elenco")
    @richiedi(Livello.ADMIN)
    async def codici(
        self, interaction: discord.Interaction, membro: discord.Member, pagina: app_commands.Range[int, 1, 100] = 1
    ) -> None:
        if await self._pronto(interaction):
            await self._elenco(interaction, membro, pagina)

    @comando_di_gruppo("level", nome="codici", descrizione="I tuoi codici d'invito, a pagine da 10.", sottogruppo=_SG_INVITI)
    @app_commands.describe(pagina="Pagina dell'elenco")
    async def codici_miei(self, interaction: discord.Interaction, pagina: app_commands.Range[int, 1, 100] = 1) -> None:
        if await self._pronto(interaction):
            await self._elenco(interaction, interaction.user, pagina)

    # ---------------------------------------------------------------- etichetta
    async def _completa_codice(self, interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        noti = sorted(invite_tracker.codici(interaction.guild.id) or [])
        corrente = corrente.strip().lower()[:64]
        return [app_commands.Choice(name=c, value=c) for c in noti if corrente in c.lower()][:25]

    @comando_di_gruppo("admin-inviti", nome="etichetta", descrizione="Dai un nome a un codice, con un ruolo per chi entra.")
    @app_commands.describe(
        codice="Il codice dell'invito", testo="Il nome del codice", ruolo="Ruolo dato a chi entra con questo codice",
    )
    @app_commands.autocomplete(codice=_completa_codice)
    @richiedi(Livello.ADMIN)
    async def etichetta(
        self, interaction: discord.Interaction, codice: app_commands.Range[str, 2, 64],
        testo: app_commands.Range[str, 1, MAX_ETICHETTA], ruolo: discord.Role | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        codice = codice.rsplit("/", 1)[-1].strip()
        if codice not in (invite_tracker.codici(interaction.guild.id) or set()):
            inviti = await inviti_del_server(interaction.guild)
            if inviti is None or codice not in {i.code for i in inviti}:
                await interaction.response.send_message(await testo_per(interaction, "invites_codice_sconosciuto"), ephemeral=True)
                return
        if ruolo is not None:
            chiave = await motivo_ruolo_non_dato(interaction, ruolo)
            if chiave:
                await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
                return
        try:
            await inviti_extra_repo.imposta_etichetta(interaction.guild.id, codice, testo, ruolo.id if ruolo else None)
        except TroppeEtichette:
            await interaction.response.send_message(await testo_per(interaction, "invites_troppe_etichette"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "invites_etichetta_salvata", codice=codice, testo=testo), ephemeral=True,
            allowed_mentions=_NESSUNA_MENZIONE,
        )

    # ---------------------------------------------------------------- crea
    @comando_di_gruppo("admin-inviti", nome="crea", descrizione="Crea un invito senza scadenza, con nome e ruolo.")
    @app_commands.describe(
        canale="Il canale dell'invito", usi=f"Quante volte si può usare (0 = sempre, al massimo {MAX_USI_INVITO})",
        etichetta="Il nome del codice", ruolo="Ruolo dato a chi entra con questo codice",
    )
    @richiedi(Livello.ADMIN)
    async def crea(
        self, interaction: discord.Interaction,
        canale: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.ForumChannel,
        usi: app_commands.Range[int, 0, MAX_USI_INVITO] = 0,
        etichetta: app_commands.Range[str, 1, MAX_ETICHETTA] | None = None, ruolo: discord.Role | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        if not canale.permissions_for(interaction.user).create_instant_invite:
            await interaction.response.send_message(await testo_per(interaction, "invites_tu_non_puoi_creare"), ephemeral=True)
            return
        if not canale.permissions_for(guild.me).create_instant_invite:
            await interaction.response.send_message(await testo_per(interaction, "invites_bot_non_puo_creare"), ephemeral=True)
            return
        if ruolo is not None:
            chiave = await motivo_ruolo_non_dato(interaction, ruolo)
            if chiave:
                await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
                return
        await interaction.response.defer(ephemeral=True)
        esistenti = await inviti_del_server(guild)
        if esistenti is not None and len(esistenti) >= MAX_INVITI_SERVER:
            await interaction.followup.send(await testo_per(interaction, "invites_troppi_inviti", massimo=MAX_INVITI_SERVER))
            return
        try:
            invito = await canale.create_invite(max_age=0, max_uses=usi, unique=True, reason=f"Creato da {interaction.user} (iYokai)")
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "invites_creazione_fallita"))
            return
        invite_tracker.registra_invito(guild.id, invito.code, getattr(guild.me, "id", None))
        if etichetta or ruolo:
            try:
                await inviti_extra_repo.imposta_etichetta(guild.id, invito.code, etichetta or invito.code, ruolo.id if ruolo else None)
            except TroppeEtichette:
                await interaction.followup.send(await testo_per(interaction, "invites_troppe_etichette"))
        await interaction.followup.send(await testo_per(interaction, "invites_creato", indirizzo=f"https://discord.gg/{invito.code}"))

    # ---------------------------------------------------------------- cancella
    @comando_di_gruppo("admin-inviti", nome="cancella", descrizione="Cancella inviti: uno, quelli poco usati o quelli di un canale.")
    @app_commands.describe(
        codice="Il codice da cancellare", usi_sotto="Cancella gli inviti usati meno di tante volte",
        canale="Cancella tutti gli inviti di questo canale",
    )
    @richiedi(Livello.ADMIN)
    async def cancella(
        self, interaction: discord.Interaction, codice: app_commands.Range[str, 2, 64] | None = None,
        usi_sotto: app_commands.Range[int, 1, 100000] | None = None,
        canale: discord.abc.GuildChannel | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        if sum(x is not None for x in (codice, usi_sotto, canale)) != 1:
            await interaction.response.send_message(await testo_per(interaction, "invites_un_solo_criterio"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        inviti = await inviti_del_server(interaction.guild)
        if inviti is None:
            await interaction.followup.send(await testo_per(interaction, "invites_serve_gestire_server"))
            return
        protetti = await invite_links_repo.codici_personali(interaction.guild.id)
        scelti = da_cancellare(
            [da_invito(i) for i in inviti], codice=codice.rsplit("/", 1)[-1].strip() if codice else None,
            usi_sotto=usi_sotto, canale_id=canale.id if canale else None, protetti=protetti,
        )
        if not scelti:
            await interaction.followup.send(await testo_per(interaction, "invites_nessuno_da_cancellare"))
            return
        questo_giro = [i.codice for i in scelti[:MAX_CANCELLAZIONI_PER_GIRO]]
        testo = await testo_per(interaction, "invites_conferma_cancella", n=len(scelti), giro=len(questo_giro))
        await interaction.followup.send(
            testo, view=ConfermaCancellazione(self, interaction.user.id, interaction.guild, questo_giro)
        )

    async def cancella_a_uno_al_secondo(self, guild: discord.Guild, codici: list[str], chi: int) -> tuple[int, bool]:
        """Cancella gli inviti uno al secondo. Ritorna (cancellati, fermato): ci si ferma al primo rifiuto."""
        fatti = 0
        inviti = await inviti_del_server(guild)
        per_codice = {i.code: i for i in (inviti or [])}
        for codice in codici:
            invito = per_codice.get(codice)
            if invito is None:
                continue  # già sparito
            try:
                await invito.delete(reason=f"Cancellato da {chi} (iYokai)")
            except discord.Forbidden:
                return fatti, True
            except discord.NotFound:
                pass
            except discord.HTTPException:
                return fatti, True
            invite_service.invito_cancellato(codice)
            await inviti_extra_repo.togli_etichetta(guild.id, codice)
            fatti += 1
            await asyncio.sleep(PAUSA_CANCELLAZIONE)
        return fatti, False


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InvitiCodiciCog(bot))

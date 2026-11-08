"""
cogs/moderation/clear.py
===========================
Cancellazione di massa dei messaggi, con filtri opzionali. Modulo
CANDIDATO PREMIUM (MODULE_CLEAR), come da schema.

Nota sul limite dei 14 giorni: discord.py gestisce già da solo la
differenza tra bulk-delete (messaggi più recenti di 14 giorni, veloce,
un'unica chiamata per gruppi fino a 100) e cancellazione singola
(messaggi più vecchi, una richiesta alla volta, molto più lenta) —
non serve reimplementare questa logica qui, `channel.purge()` la fa
già internamente. Il limite resta comunque REALE: cancellare molti
messaggi vecchi può richiedere diversi secondi per via del rate limit
sulle cancellazioni singole.

Filtri (core/clear_filter_logic.py): utente, ruolo, solo bot, solo persone,
allegati, testo contenuto o non contenuto, link, inviti, embed, menzioni,
salta i fissati, tipo (webhook, iYokai, solo emoji, solo testo,
sospetti), modo del testo (contiene, inizia, finisce, uguale, regex), prima/dopo un
messaggio e età. Fino a 1.000 messaggi, di cui al massimo 100 vecchi. Il testo dei messaggi serve il Message Content Intent
(acceso in main.py; sotto i 10.000 utenti basta l'interruttore nel
Developer Portal, da 10.000 serve la domanda a Discord, da rifare ogni
anno). Il canale può essere diverso da quello del comando; chi usa il comando
deve poter vedere e gestire i messaggi di quel canale. Ogni pulizia
scrive una riga nel log di moderazione (M 1.8).
Funzioni coperte: SPEC §5.4 (MOD-069-072, 073-079, 080-089)
"""

from __future__ import annotations

from typing import Literal

import asyncio
import time

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from core.i18n import testo_per
from core.premium import PremiumModule, registry, requires_module
from core.clear_filter_logic import (
    MAX_CLEAR_AMOUNT,
    MAX_VECCHI,
    FiltriClear,
    crea_controllo,
    descrivi_filtri,
    leggi_riferimento_messaggio,
)
from core.duration_logic import parse_duration
from core.message_log_logic import regex_non_valida
from cogs.moderation._shared import (
    MODULE_CLEAR,
    ensure_module_enabled,
    post_to_mod_log,
    truncate_text,
)

PAUSA_REAZIONI = 0.3  # secondi tra una modifica e l'altra: niente raffiche
MAX_REAZIONI = 100
MAX_403_DI_FILA = 3
FINESTRA_RISPOSTA_S = 14 * 60  # il token dell'interazione dura 15 minuti


class ModerationClearCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "mod-canali",
        nome="clear",
        descrizione="Cancella un numero di messaggi, con filtri opzionali.",
    )
    @app_commands.describe(
        amount="Quanti messaggi controllare (max 1000)",
        member="Cancella solo i messaggi di questo utente",
        bots_only="Cancella solo i messaggi inviati da bot o webhook",
        attachments_only="Cancella solo i messaggi con allegati",
        channel="Il canale da pulire (default: quello attuale)",
        humans_only="Cancella solo i messaggi di persone (non bot)",
        contains="Cancella solo i messaggi che contengono questo testo",
        not_contains="Cancella solo i messaggi che NON contengono questo testo",
        links_only="Cancella solo i messaggi con link",
        invites_only="Cancella solo i messaggi con inviti Discord",
        embeds_only="Cancella solo i messaggi con embed",
        mentions_only="Cancella solo i messaggi con menzioni",
        role="Cancella solo i messaggi di chi ha questo ruolo",
        skip_pinned="Salta i messaggi fissati",
        tipo="Cancella solo un tipo di messaggi (webhook, iYokai, solo emoji, solo testo, sospetti)",
        modo="Come cercare il testo di «contains» (default: contiene)",
        dopo="Solo i messaggi dopo questo (ID o link, dello stesso canale)",
        prima="Solo i messaggi prima di questo (ID o link, dello stesso canale)",
        piu_vecchi_di="Solo i messaggi più vecchi di questa durata (es. 2h, 3d)",
        piu_nuovi_di="Solo i messaggi più nuovi di questa durata (es. 30m)",
    )
    @requires_module(MODULE_CLEAR)
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, MAX_CLEAR_AMOUNT],
        member: discord.Member | None = None,
        bots_only: bool = False,
        attachments_only: bool = False,
        channel: discord.TextChannel | None = None,
        humans_only: bool = False,
        contains: app_commands.Range[str, 1, 100] | None = None,
        not_contains: app_commands.Range[str, 1, 100] | None = None,
        links_only: bool = False,
        invites_only: bool = False,
        embeds_only: bool = False,
        mentions_only: bool = False,
        role: discord.Role | None = None,
        skip_pinned: bool = False,
        tipo: Literal["webhook", "iyokai", "emoji", "solo-testo", "sospetti"] | None = None,
        modo: Literal["contiene", "inizia", "finisce", "uguale", "regex"] = "contiene",
        dopo: app_commands.Range[str, 1, 100] | None = None,
        prima: app_commands.Range[str, 1, 100] | None = None,
        piu_vecchi_di: app_commands.Range[str, 1, 20] | None = None,
        piu_nuovi_di: app_commands.Range[str, 1, 20] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CLEAR):
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "channelcontr_questo_comando_funziona_solo_su"), ephemeral=True
            )
            return

        # Il permesso vale nel canale scelto, non solo nel server: chi non vede
        # un canale (o non può gestirne i messaggi) non può pulirlo da qui.
        permessi = target.permissions_for(interaction.user)
        if not (permessi.view_channel and permessi.manage_messages):
            await interaction.response.send_message(
                await testo_per(interaction, "clear_non_hai_il_permesso_gestire", mention=target.mention), ephemeral=True
            )
            return

        if bots_only and humans_only:
            await interaction.response.send_message(
                await testo_per(interaction, "clear_solo_bot_solo_persone_insieme"), ephemeral=True
            )
            return
        errore = await self._valida_nuovi(interaction, target, contains, modo, dopo, prima, piu_vecchi_di, piu_nuovi_di)
        if errore is None:
            return
        dopo_id, prima_id, vecchi_s, nuovi_s = errore

        filtri = FiltriClear(
            autore_id=member.id if member else None,
            solo_bot=bots_only,
            solo_persone=humans_only,
            solo_allegati=attachments_only,
            contiene=contains,
            non_contiene=not_contains,
            solo_link=links_only,
            solo_inviti=invites_only,
            solo_embed=embeds_only,
            solo_menzioni=mentions_only,
            ruolo_id=role.id if role else None,
            salta_fissati=skip_pinned,
            tipo=tipo,
            modo=modo,
            bot_id=getattr(getattr(interaction.client, "user", None), "id", None),
            piu_vecchi_di_s=vecchi_s,
            piu_nuovi_di_s=nuovi_s,
        )

        # Risponde SUBITO in modo ephemeral, prima di iniziare la
        # cancellazione: se ci sono molti messaggi vecchi (>14 giorni)
        # l'operazione può richiedere diversi secondi, e Discord
        # scade l'interazione dopo 3 secondi se non si risponde prima.
        await interaction.response.defer(ephemeral=True)

        inizio = time.monotonic()
        controllo, stato = crea_controllo(filtri)
        extra = {}
        if dopo_id:
            extra["after"] = discord.Object(id=dopo_id)
        if prima_id:
            extra["before"] = discord.Object(id=prima_id)
        try:
            # Sempre dal più nuovo, anche con «dopo»: discord.py, appena trova un messaggio
            # oltre i 14 giorni, cancella uno per uno anche tutti quelli che seguono.
            eliminati = await target.purge(limit=amount, check=controllo, oldest_first=False, **extra)
        except discord.HTTPException:
            await interaction.followup.send(
                await testo_per(interaction, "clear_non_sono_riuscito_cancellare_messaggi"),
                ephemeral=True,
            )
            return

        # Dopo 14 minuti il token non vale più: il risultato resta nel log di moderazione.
        if time.monotonic() - inizio < FINESTRA_RISPOSTA_S:
            risposta = await testo_per(interaction, "clear_messaggi_cancellati", v1=len(eliminati))
            if stato.vecchi_saltati:
                risposta += " " + await testo_per(
                    interaction, "clear_restano_vecchi", v1=stato.vecchi_saltati, v2=MAX_VECCHI
                )
            await interaction.followup.send(risposta, ephemeral=True)
        embed = discord.Embed(title=await testo_per(interaction, "clear_clear", pubblica=True), color=discord.Color.light_grey())
        embed.add_field(name=await testo_per(interaction, "clear_canale", pubblica=True), value=target.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "clear_cancellati", pubblica=True), value=str(len(eliminati)), inline=True)
        embed.add_field(
            name=await testo_per(interaction, "clear_filtri", pubblica=True), value=truncate_text(descrivi_filtri(filtri), 1000), inline=False
        )
        await post_to_mod_log(interaction.guild, embed)

    async def _valida_nuovi(self, interaction, target, contains, modo, dopo, prima, piu_vecchi_di, piu_nuovi_di):
        """Controlla regex, riferimenti e durate. Ritorna (dopo, prima, vecchi_s, nuovi_s) o None dopo aver risposto."""
        async def rifiuta(chiave, **valori):
            await interaction.response.send_message(await testo_per(interaction, chiave, **valori), ephemeral=True)

        if modo == "regex":
            if not contains:
                await rifiuta("clear_regex_serve_testo")
                return None
            motivo = regex_non_valida(contains)
            if motivo:
                await rifiuta("clear_regex_non_valida", motivo=motivo)
                return None
        try:
            dopo_id = leggi_riferimento_messaggio(dopo, target.id) if dopo else None
            prima_id = leggi_riferimento_messaggio(prima, target.id) if prima else None
            vecchi_s = parse_duration(piu_vecchi_di) if piu_vecchi_di else None
            nuovi_s = parse_duration(piu_nuovi_di) if piu_nuovi_di else None
        except ValueError as errore:
            await rifiuta("clear_valore_non_valido", motivo=str(errore))
            return None
        return dopo_id, prima_id, vecchi_s, nuovi_s

    @comando_di_gruppo(
        "mod-canali",
        nome="reazioni",
        descrizione="Toglie le reazioni dagli ultimi messaggi di un canale, senza cancellarli.",
    )
    @app_commands.describe(
        quanti="Quanti messaggi controllare (da 1 a 100)",
        canale="Il canale da pulire (default: quello attuale)",
        emoji="Toglie solo questa emoji (default: tutte)",
    )
    @requires_module(MODULE_CLEAR)
    async def reazioni(
        self,
        interaction: discord.Interaction,
        quanti: app_commands.Range[int, 1, MAX_REAZIONI],
        canale: discord.TextChannel | None = None,
        emoji: app_commands.Range[str, 1, 100] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CLEAR):
            return
        target = canale or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "channelcontr_questo_comando_funziona_solo_su"), ephemeral=True
            )
            return
        permessi = target.permissions_for(interaction.user)
        if not (permessi.view_channel and permessi.manage_messages):
            await interaction.response.send_message(
                await testo_per(interaction, "clear_non_hai_il_permesso_gestire", mention=target.mention), ephemeral=True
            )
            return
        del_bot = target.permissions_for(interaction.guild.me)
        if not (del_bot.view_channel and del_bot.manage_messages and del_bot.read_message_history):
            await interaction.response.send_message(
                await testo_per(interaction, "clear_reazioni_bot_senza_permesso", mention=target.mention), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        puliti = 0
        di_fila = 0
        async for messaggio in target.history(limit=quanti):
            giuste = [r for r in messaggio.reactions if emoji is None or str(r.emoji) == emoji]
            if not giuste:
                continue
            try:
                if emoji is None:
                    await messaggio.clear_reactions()
                else:
                    await messaggio.clear_reaction(emoji)
                puliti += 1
                di_fila = 0
            except discord.Forbidden:
                di_fila += 1
                if di_fila >= MAX_403_DI_FILA:  # tre 403 di fila: ci si ferma (rischio blocco IP)
                    break
            except discord.HTTPException:
                break
            await asyncio.sleep(PAUSA_REAZIONI)

        await interaction.followup.send(
            await testo_per(interaction, "clear_reazioni_fatto", v1=puliti), ephemeral=True
        )
        embed = discord.Embed(
            title=await testo_per(interaction, "clear_reazioni_titolo", pubblica=True), color=discord.Color.light_grey()
        )
        embed.add_field(name=await testo_per(interaction, "clear_canale", pubblica=True), value=target.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "clear_cancellati", pubblica=True), value=str(puliti), inline=True)
        await post_to_mod_log(interaction.guild, embed)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CLEAR,
            display_name="Moderazione — Clear avanzato",
            category="moderation",
            description="Cancellazione di massa dei messaggi con filtri.",
            premium_capable=True,
        )
    )
    await bot.add_cog(ModerationClearCog(bot))

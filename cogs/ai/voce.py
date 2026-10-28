"""
cogs/ai/voce.py
===============
La voce di Yokai: veri messaggi vocali di Discord scritti dal bot, con sotto «Trascrivi» e «Nella mia lingua»
(vedono la risposta solo chi preme, nella lingua del loro client); `/ai voce imposta|parla`, `/utility ai parla`,
saluti a voce nei canali scelti. Il menu «Trascrivi vocale» sui vocali delle persone sta nell'app (cogs/user_app/voce_app.py). Senza motore vocale il bot manda
solo il testo. Il motore si accende da `.env` (VOCE_MODELLO_DIR).
Funzioni coperte: SPEC §14.19, §25.102, §25.103, §25.104, §25.105 (AI-R-109..112, D22)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import NESSUNA_MENZIONE, SOTTO_AI, chiedi, registra_modulo_ai, taglia
from cogs.ai.traduzione import istruzioni_traduzione
from core import voice_saluti_logic as saluti
from core.ai_guardrail_logic import richiesta_vietata
from core.ai_servizio import RichiestaAI
from core.ai_testi_logic import LINGUE, riconosci_lingua
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.discord_raw import invia_vocale
from core.repositories.ai_repo import ai_repo
from core.repositories.ai_voce_repo import ai_voce_repo
from core.trascrizione import trascrittore, vocale_accettabile
from core.voice_client import servizio_voce
from core.voice_profile import TONI, profilo, tono_consentito
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ai_voce")

SOTTO_VOCE = ("voce", "La voce di Yokai: vocali scritti dal bot")
MAX_TESTO = 300
COOLDOWN_UTENTE = 30.0
MAX_AL_GIORNO = 20
SPENTA = "La voce di Yokai non è attiva su questo bot: scrivo solo il testo."


def lingua_del_client(interaction: discord.Interaction) -> str:
    """Il codice lingua (due lettere) del client di chi preme; se non è tra quelle note, inglese."""
    codice = str(getattr(interaction.locale, "value", interaction.locale) or "en").split("-")[0].lower()
    return codice if codice in LINGUE else "en"


async def parla(
    bot: commands.Bot, canale: discord.abc.Messageable, testo: str, contesto: str, *, guild_id: int | None, chi: discord.abc.User | None = None,
    nomi: dict[int, str] | None = None, fisso: bool = False, risposta_a: int | None = None,
) -> bool:
    """Manda un vocale nel canale (con i bottoni sotto); se la voce non c'è manda il solo testo. True se è partito un vocale."""
    cfg = await ai_voce_repo.config(guild_id) if guild_id else None
    tono = cfg.tono if cfg else "scherzosa"
    nsfw = bool(getattr(canale, "is_nsfw", lambda: False)())
    voce = await servizio_voce().genera(testo, profilo(contesto, tono, nsfw), nomi=nomi, fisso=fisso)
    if voce is None:
        await canale.send(taglia(testo, 1900), allowed_mentions=NESSUNA_MENZIONE)
        return False
    try:
        vocale_id = await invia_vocale(bot.http, canale.id, voce.ogg, voce.durata, voce.onda, risposta_a=risposta_a)
        sotto = await canale.send(
            "Vocale di Yokai" + (f" · richiesto da {chi.mention}" if chi else ""),
            view=VocaleView(), reference=discord.MessageReference(message_id=vocale_id, channel_id=canale.id, fail_if_not_exists=False),
            allowed_mentions=NESSUNA_MENZIONE,
        )
    except discord.HTTPException:
        logger.warning("Vocale non inviato.", exc_info=True)
        await canale.send(taglia(testo, 1900), allowed_mentions=NESSUNA_MENZIONE)
        return False
    await ai_voce_repo.salva_vocale(sotto.id, guild_id, canale.id, voce.testo, riconosci_lingua(voce.testo))
    return True


class VocaleView(BaseView):
    """Bottoni persistenti sotto ogni vocale: la risposta la vede solo chi preme (AI-R-110)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Trascrivi", style=discord.ButtonStyle.secondary, custom_id="aivc:tr")
    async def trascrivi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        v = await ai_voce_repo.vocale(interaction.message.id)
        if v is None:
            await interaction.response.send_message("Non ho più il testo di questo vocale.", ephemeral=True)
            return
        await interaction.response.send_message(taglia(v.testo, 1900), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @discord.ui.button(label="Nella mia lingua", style=discord.ButtonStyle.secondary, custom_id="aivc:tl")
    async def nella_mia_lingua(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        v = await ai_voce_repo.vocale(interaction.message.id)
        if v is None:
            await interaction.response.send_message("Non ho più il testo di questo vocale.", ephemeral=True)
            return
        lingua = lingua_del_client(interaction)
        if lingua == v.lingua:
            await interaction.response.send_message(taglia(v.testo, 1900), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        await interaction.response.defer(ephemeral=True)
        risposta, locale = await chiedi(RichiestaAI(
            user_id=interaction.user.id, funzione="vocale_traduci", tipo="traduzione", testo=v.testo, guild_id=interaction.guild_id,
            channel_id=interaction.channel_id, istruzioni=istruzioni_traduzione(lingua), lingua=lingua, messaggi_utenti=True,
        ))
        testo = risposta.testo if risposta else f"{locale}\n\nTesto originale: {v.testo}"
        await interaction.followup.send(taglia(testo, 1900), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def trascrivi_e_traduci(interaction: discord.Interaction, messaggio: discord.Message) -> None:
    """Menu «Trascrivi vocale» (AI-R-111): testo del vocale di una persona e traduzione nella lingua del client."""
    vocale = next((a for a in messaggio.attachments if a.is_voice_message()), None)
    if vocale is None:
        await interaction.response.send_message("Questo messaggio non è un vocale.", ephemeral=True)
        return
    motivo = vocale_accettabile(vocale.duration, vocale.size)
    if motivo:
        await interaction.response.send_message(motivo, ephemeral=True)
        return
    if not trascrittore().attivo:
        await interaction.response.send_message("La trascrizione dei vocali non è attiva su questo bot.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    testo = await trascrittore().trascrivi(await vocale.read(), vocale.filename)
    if not testo:
        await interaction.followup.send("Non sono riuscita a trascrivere il vocale.", ephemeral=True)
        return
    lingua = lingua_del_client(interaction)
    corpo = f"**Testo**\n{taglia(testo, 900)}"
    if riconosci_lingua(testo, "?") != lingua:
        risposta, _ = await chiedi(RichiestaAI(
            user_id=interaction.user.id, funzione="vocale_persona_traduci", tipo="traduzione", testo=testo, guild_id=interaction.guild_id,
            channel_id=interaction.channel_id, istruzioni=istruzioni_traduzione(lingua), lingua=lingua, messaggi_utenti=True,
        ))
        if risposta:
            corpo += f"\n\n**{LINGUE[lingua].capitalize()}**\n{taglia(risposta.testo, 900)}"
    await interaction.followup.send(corpo, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


class AiVoceCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.raccolta = saluti.RaccoltaSaluti()
        self._recenti: dict[int, list[float]] = {}

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.add_view(VocaleView())

    # ---------------------------------------------------------------- comandi
    def _limite_utente(self, user_id: int) -> str | None:
        ora = time.monotonic()
        colpi = [t for t in self._recenti.get(user_id, []) if ora - t < 86400]
        if colpi and ora - colpi[-1] < COOLDOWN_UTENTE:
            return f"Aspetta {int(COOLDOWN_UTENTE - (ora - colpi[-1])) + 1} secondi."
        if len(colpi) >= MAX_AL_GIORNO:
            return "Hai usato la voce abbastanza per oggi."
        self._recenti[user_id] = [*colpi, ora]
        return None

    async def _controlla_testo(self, guild_id: int, testo: str) -> str | None:
        """I filtri del server prima di diventare voce: parole vietate e testo troppo lungo."""
        cfg = await ai_repo.get_config(guild_id)
        if richiesta_vietata(testo, cfg.parole_vietate) is not None:
            return "Questo testo non si può trasformare in voce."
        return None

    @comando_di_gruppo("ai", nome="imposta", descrizione="Voce di Yokai: accesa o spenta, tono e canali dei saluti.", sottogruppo=SOTTO_VOCE)
    @app_commands.describe(attiva="Sì: la voce è accesa nel server", tono="Il tono della voce (piccante solo nei canali NSFW)",
                           saluti_canale="Aggiunge o toglie un canale dove Yokai risponde ai saluti a voce")
    @app_commands.choices(tono=[app_commands.Choice(name=t, value=t) for t in TONI])
    async def voce_imposta(self, interaction: discord.Interaction, attiva: bool | None = None, tono: str | None = None,
                           saluti_canale: discord.TextChannel | None = None) -> None:
        campi: dict = {k: v for k, v in {"attiva": attiva, "tono": tono}.items() if v is not None}
        if saluti_canale is not None:
            attuali = list((await ai_voce_repo.config(interaction.guild_id)).canali_saluti)
            if saluti_canale.id in attuali:
                attuali.remove(saluti_canale.id)
            elif len(attuali) >= 10:
                await interaction.response.send_message("Al massimo 10 canali per i saluti.", ephemeral=True)
                return
            else:
                attuali.append(saluti_canale.id)
            campi["canali_saluti"] = attuali
        if campi:
            await ai_voce_repo.imposta(interaction.guild_id, **campi)
        c = await ai_voce_repo.config(interaction.guild_id)
        testo = (
            f"Voce {'accesa' if c.attiva else 'spenta'}, tono {c.tono}"
            + (f" (nei canali non NSFW suona {tono_consentito(c.tono, False)})" if c.tono == "piccante" else "")
            + (f". Saluti a voce in: {', '.join(f'<#{x}>' for x in c.canali_saluti)}." if c.canali_saluti else ". Nessun canale per i saluti.")
            + ("" if servizio_voce().attivo else " Attenzione: il motore vocale non è configurato, quindi scrivo solo il testo.")
        )
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("ai", nome="parla", descrizione="Yokai dice un annuncio a voce in un canale.", sottogruppo=SOTTO_VOCE)
    @app_commands.describe(testo="Cosa dire", canale="Dove (vuoto: qui)")
    async def voce_parla(self, interaction: discord.Interaction, testo: app_commands.Range[str, 3, MAX_TESTO], canale: discord.TextChannel | None = None) -> None:
        destinazione = canale or interaction.channel
        if not isinstance(destinazione, discord.TextChannel):
            await interaction.response.send_message("Scegli un canale di testo.", ephemeral=True)
            return
        errore = await self._controlla_testo(interaction.guild_id, testo)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        partito = await parla(self.bot, destinazione, testo, "ANNOUNCEMENT", guild_id=interaction.guild_id, chi=interaction.user)
        await interaction.followup.send(f"Vocale in {destinazione.mention}." if partito else SPENTA, ephemeral=True)

    @comando_di_gruppo("utility", nome="parla", descrizione="Yokai dice una frase a voce in questo canale.", sottogruppo=SOTTO_AI)
    @app_commands.describe(testo="Cosa dire")
    async def utility_parla(self, interaction: discord.Interaction, testo: app_commands.Range[str, 3, MAX_TESTO]) -> None:
        if interaction.guild_id is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Si usa in un canale di testo di un server.", ephemeral=True)
            return
        if not (await ai_voce_repo.config(interaction.guild_id)).attiva:
            await interaction.response.send_message("La voce di Yokai non è accesa in questo server.", ephemeral=True)
            return
        errore = await self._controlla_testo(interaction.guild_id, testo) or self._limite_utente(interaction.user.id)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        partito = await parla(self.bot, interaction.channel, testo, "PUBLIC", guild_id=interaction.guild_id, chi=interaction.user)
        await interaction.followup.send("Fatto." if partito else SPENTA, ephemeral=True)

    # ---------------------------------------------------------------- saluti a voce
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not message.content:
            return
        saluto = saluti.riconosci_saluto(message.content)
        if saluto is None:
            return
        try:
            cfg = await ai_voce_repo.config(message.guild.id)
            if not cfg.attiva or message.channel.id not in cfg.canali_saluti:
                return
            adesso = datetime.now(timezone.utc)
            if self.raccolta.aggiungi(message.channel.id, saluto, message.author.display_name, adesso):
                asyncio.create_task(self._rispondi_ai_saluti(message.channel, message.guild.id, message.id))
        except Exception:  # noqa: BLE001 - un saluto non deve mai dare errori
            logger.warning("Saluto non gestito.", exc_info=True)

    async def _rispondi_ai_saluti(self, canale: discord.abc.Messageable, guild_id: int, primo_id: int) -> None:
        await asyncio.sleep(saluti.ATTESA_RACCOLTA)
        raccolta = self.raccolta.chiudi(canale.id, datetime.now(timezone.utc))
        if raccolta is None:
            return
        saluto, nomi = raccolta
        frase, fissa = saluti.frase_saluto(saluto, nomi)
        try:
            await parla(self.bot, canale, frase, "WELCOME", guild_id=guild_id, fisso=fissa, risposta_a=primo_id)
        except Exception:  # noqa: BLE001
            logger.warning("Saluto a voce non inviato.", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiVoceCog(bot))

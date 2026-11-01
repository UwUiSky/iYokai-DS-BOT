"""
cogs/security/verify.py
==========================
Verify Base (SPEC.md §4.1, §4.4, §4.5, §4.6). Modulo SEMPRE GRATUITO,
come da schema.

Due modalità mutuamente esclusive, scelte a `/security verify setup`:
- button: bottone persistente (stesso pattern di TicketPanelView) —
  supporta il captcha, perché un click su bottone È un'Interaction e
  può aprire un Modal.
- reaction: l'utente reagisce a un messaggio con un'emoji — NON
  supporta il captcha: una reazione non è un'Interaction, non può
  aprire un Modal. La combinazione reaction+captcha viene rifiutata
  esplicitamente a `/security verify setup`, non implementata a metà con un
  flusso DM fragile.

Ruoli (impostazioni del server, `/security verify opzioni`): un ruolo
«non verificato» dato all'ingresso e tolto alla verifica (VER-014) e fino
a tre ruoli in più dati insieme a quello di verifica (VER-015). Lo staff
può verificare a mano un membro (VER-016), cercare i tentativi di un
utente (VER-031) e vedere le statistiche (VER-030).

Captcha (`/security verify setup`, opzione `captcha_tipo`): «testo» e' una
somma scritta nel modulo; «immagine» (NF-18) manda un'immagine con lettere
storte e un bottone che apre il modulo per ricopiarle. Tempo massimo 3 minuti,
3 tentativi (core/captcha_image.py).

Il membro può verificarsi anche con /utility verifica (VER-010), lo stesso
percorso del bottone del pannello.

Tempi e azioni (`/security verify tempi`): promemoria in DM dopo X minuti
(VER-008; con i DM chiusi un avviso nel canale del pannello che sparisce dopo
pochi secondi, VER-009), tempo massimo con kick o ban alla scadenza
(VER-011, scadenze nello scheduler: reggono un riavvio), azione su chi non
passa (VER-012: quarantena, kick, ban o niente; per il captcha sbagliato solo
dopo 3 fallimenti di fila) e verifica solo per gli account sospetti (VER-013:
gli altri ricevono subito i ruoli).

Account troppo giovane (VER-019, `tempi azione_eta`): resta in attesa e riceve
un DM quando raggiunge l'età (promemoria e scadenza partono da allora), oppure
viene espulso all'ingresso. Modalità cieca (VER-020, `tempi sospendi_ore`): per
qualche ora chi entra riceve subito i ruoli e il log lo scrive (mai durante
un raid, mai saltando l'età minima con «solo sospetti»). Lo staff può
rimandare l'invito in DM (`invia`, VER-017), vedere le statistiche complete
(VER-030) ed esportare i tentativi in CSV (`tentativi csv:`, VER-031).

A verifica riuscita, in un server con backup, la proposta di consenso al
ripristino (M 12.12/12.14, `proponi_consenso_restore`).

Modalità «Pagina web» (NF-21, §4.2–4.3): il bottone dà un link personale
alla pagina di verifica del pannello web; lì il bot salva un'impronta (mai
l'IP in chiaro) e avvisa lo staff se trova un account doppio
(`core/panel_bridge.py`, `cogs/security/alt_detection.py`).
Funzioni coperte: SPEC §4.1–§4.6 (VER-008…017, 019, 020, 029–031; NF-21)
"""

from __future__ import annotations

import asyncio
import csv
import io
import time
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from core import captcha_image
from core.i18n import testo_per
from core.bounded_cache import BoundedCache
from core.panel_bridge import METODO_WEB, link_verifica_web
from core.command_groups import CogConGruppi, comando_di_gruppo

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.verify_repo import verify_repo
from cogs.moderation._shared import ensure_module_enabled
from core.role_safety import check_role_assignable
from core.ui_base import BaseModal, BaseView
from core.scheduler import in_seconds, scheduler
from core.security_quarantine import ruolo_quarantena
from core.security_raid_state import raid_in_corso
from core.verify_logic import (
    AZIONI_FALLITA,
    FALLIMENTI_CAPTCHA_PRIMA_DELL_AZIONE,
    VerifyOutcome,
    AZIONI_ETA,
    account_sospetto,
    quando_maggiorenne,
    sospesa_adesso,
    azione_dopo_fallimento,
    esiti_nella_finestra,
    decide_verify_outcome,
    meets_account_age,
    meets_mutual_servers,
)

logger = logging.getLogger("iyokai.verify")

MODULE_VERIFY = "verify"

# Impostazioni dei ruoli extra (guild_config.settings).
SETTING_RUOLO_NON_VERIFICATO = "verify_unverified_role_id"
SETTING_RUOLI_EXTRA = "verify_extra_role_ids"
SETTING_LOG_COMPATTO = "verify_log_compatto"  # VER-029: True = una riga, False = scheda completa
SETTING_CAPTCHA_TIPO = "verify_captcha_tipo"  # captcha_image.TIPO_TESTO | TIPO_IMMAGINE
SETTING_PROMEMORIA_MINUTI = "verify_promemoria_minuti"  # VER-008: 0 = spento
SETTING_SCADENZA_MINUTI = "verify_scadenza_minuti"  # VER-011: 0 = spento
SETTING_AZIONE_SCADENZA = "verify_azione_scadenza"  # VER-011: kick | ban
SETTING_AZIONE_FALLITA = "verify_azione_fallita"  # VER-012: niente | quarantena | kick | ban
SETTING_SOLO_SOSPETTI = "verify_solo_sospetti"  # VER-013
SETTING_AZIONE_ETA = "verify_azione_eta"  # VER-019: attendi | kick
SETTING_SOSPESA_FINO = "verify_sospesa_fino"  # VER-020: epoch di fine della modalità cieca (0 = spenta)
MAX_RUOLI_EXTRA = 3

VERIFY_PROMEMORIA = "verify_promemoria"
VERIFY_SCADENZA = "verify_scadenza"
VERIFY_ETA = "verify_eta"  # VER-019: l'account ha raggiunto l'età minima
# VER-031: l'esportazione di tutto il server si può chiedere una volta all'ora.
SECONDI_TRA_CSV = 3600
_ultimo_csv: BoundedCache = BoundedCache(max_size=10_000)
# VER-009: l'avviso nel canale del pannello sparisce dopo questi secondi.
SECONDI_AVVISO_CANALE = 15

VERIFY_BUTTON_CUSTOM_ID = "iyokai_verify_button"
VERIFY_REACTION_EMOJI = "✅"


class CaptchaModal(BaseModal, title="Verification"):
    """
    Captcha testuale (nessuna immagine — evita di introdurre Pillow
    come dipendenza solo per questo). Una semplice domanda di somma,
    generata al momento del click, diversa ogni volta: filtra i bot
    di join automatico più semplici, che non elaborano Modal.
    """

    def __init__(self, cog: "VerifyCog", guild_id: int, user_id: int) -> None:
        super().__init__()
        a, b = random.randint(1, 9), random.randint(1, 9)
        self._expected_answer = str(a + b)
        # discord.ui.Label che avvolge il TextInput è il pattern
        # corretto e non deprecato (TextInput.label= produce un
        # DeprecationWarning reale con discord.py 2.7.1, verificato
        # prima di scrivere questo file — stessa correzione applicata
        # a StaffReplyModal in cogs/security/spam_trap.py). Il
        # riferimento a self.answer_input resta valido per leggere
        # .value in on_submit, perché è lo stesso oggetto passato
        # come component= al Label.
        self.answer_input = discord.ui.TextInput(max_length=5)
        self.add_item(
            discord.ui.Label(text=f"What is {a} + {b}?", component=self.answer_input)
        )
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Risposta subito (3 secondi): controlli, ruolo e log vengono dopo.
        await interaction.response.defer(ephemeral=True)

        captcha_ok = self.answer_input.value.strip() == self._expected_answer
        guild = interaction.client.get_guild(self.guild_id)
        member = guild.get_member(self.user_id) if guild is not None else None
        if member is None:
            await interaction.followup.send(await testo_per(interaction, "verify_qualcosa_storto"), ephemeral=True)
            return

        outcome = await self.cog.run_checks_and_finalize(guild, member, captcha_ok)
        await interaction.followup.send(outcome.reason, ephemeral=True)
        await proponi_consenso_restore(
            lambda t, view: interaction.followup.send(t, view=view, ephemeral=True),
            guild, member, outcome,
        )


class CaptchaImmagineModal(BaseModal, title="Verifica"):
    """Campo per ricopiare le lettere dell'immagine (etichetta sotto i 45 caratteri)."""

    def __init__(self, cog: "VerifyCog", guild_id: int, user_id: int) -> None:
        super().__init__()
        self.answer_input = discord.ui.TextInput(max_length=captcha_image.LUNGHEZZA_CODICE + 3)
        self.add_item(discord.ui.Label(text="Scrivi le lettere dell'immagine", component=self.answer_input))
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        chiave = (self.guild_id, self.user_id)
        sfida = self.cog.sfide.get(chiave)
        if sfida is None:
            await interaction.followup.send("Il tempo e' scaduto: premi di nuovo «Verify».", ephemeral=True)
            return
        esito = sfida.prova(self.answer_input.value)
        if esito == "sbagliata":
            await interaction.followup.send(
                f"Non e' giusto. Ti restano {sfida.tentativi_rimasti} tentativi: premi «Scrivi il codice» "
                "sotto l'immagine.",
                ephemeral=True,
            )
            return
        self.cog.sfide.delete(chiave)
        guild = interaction.client.get_guild(self.guild_id)
        member = guild.get_member(self.user_id) if guild is not None else None
        if member is None:
            await interaction.followup.send("Qualcosa e' andato storto, riprova.", ephemeral=True)
            return
        outcome = await self.cog.run_checks_and_finalize(guild, member, esito == "ok")
        if esito == "ok":
            await interaction.followup.send(outcome.reason, ephemeral=True)
            await proponi_consenso_restore(
                lambda t, view: interaction.followup.send(t, view=view, ephemeral=True),
                guild, member, outcome,
            )
        else:
            motivo = "i tentativi sono finiti" if esito == "esaurita" else "il tempo e' scaduto"
            await interaction.followup.send(
                f"Verifica non riuscita: {motivo}. Premi di nuovo «Verify» per un codice nuovo.", ephemeral=True
            )


class CaptchaImmagineView(BaseView):
    """Il bottone sotto l'immagine: apre il modulo (deve essere la prima risposta)."""

    def __init__(self, cog: "VerifyCog", guild_id: int, user_id: int) -> None:
        super().__init__(timeout=captcha_image.TEMPO_MASSIMO_SECONDI)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    @discord.ui.button(label="Scrivi il codice", style=discord.ButtonStyle.primary)
    async def scrivi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Questo codice e' di un altro utente.", ephemeral=True)
            return
        sfida = self.cog.sfide.get((self.guild_id, self.user_id))
        if sfida is None or sfida.chiusa or sfida.scaduta():
            self.cog.sfide.delete((self.guild_id, self.user_id))
            await interaction.response.send_message("Il tempo e' scaduto: premi di nuovo «Verify».", ephemeral=True)
            return
        await interaction.response.send_modal(CaptchaImmagineModal(self.cog, self.guild_id, self.user_id))


class VerifyPanelView(BaseView):
    """Persistente — stesso motivo/pattern di TicketPanelView e CreateVoiceView."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id=VERIFY_BUTTON_CUSTOM_ID,
    )
    async def verify_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await avvia_verifica(interaction)


class LinkVerificaView(BaseView):
    """Un solo bottone-link verso la pagina di verifica (NF-21)."""

    def __init__(self, link: str) -> None:
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Verificami sul sito", url=link, style=discord.ButtonStyle.link))


async def proponi_consenso_restore(invia, guild: discord.Guild, member: discord.Member, outcome) -> None:
    """
    M 12.12/12.14: a verifica riuscita, la proposta di consenso per il ripristino
    (cogs/utility/restore.py). `invia(testo, view=...)` è il followup o il DM.
    """
    if not outcome.success:
        return
    from cogs.utility.restore import proposta_consenso_restore

    proposta = await proposta_consenso_restore(guild.id, member.id)
    if proposta is None:
        return
    testo, view = proposta
    try:
        await invia(testo, view=view)
    except discord.HTTPException:
        pass  # DM chiusi: la verifica è comunque riuscita


async def avvia_verifica(interaction: discord.Interaction) -> None:
    """
    Il percorso di verifica di un membro: lo usano il bottone del pannello e
    il comando /utility verifica (VER-010). Nessun controllo del panico: è
    una funzione per i membri, non per lo staff.
    """
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        # Un clic senza risposta resta "interazione non riuscita".
        await interaction.response.send_message(
            "La verifica funziona solo dentro un server.", ephemeral=True
        )
        return

    if not await db.is_module_active_for_guild(guild.id, MODULE_VERIFY):
        await interaction.response.send_message(
            "Verify non è attivo su questo server.", ephemeral=True
        )
        return

    cog = interaction.client.get_cog("VerifyCog")
    if cog is None:
        await interaction.response.send_message(
            "La verifica non è disponibile in questo momento. Riprova tra poco.", ephemeral=True
        )
        return

    # Una sola lettura prima di rispondere: serve a sapere se va
    # aperto il modulo del captcha, che può essere solo la PRIMA
    # risposta (dopo un defer non si può più aprire).
    config = await verify_repo.get_config(guild.id)
    # Chi ha già il ruolo non deve risolvere un captcha per sentirsi dire che è già verificato.
    if config.verified_role_id is not None and any(
        r.id == config.verified_role_id for r in interaction.user.roles
    ):
        await interaction.response.send_message(await testo_per(interaction, "verify_gia_verificato"), ephemeral=True)
        return
    if config.method == METODO_WEB:
        link = link_verifica_web(guild.id, interaction.user.id)
        if link is None:
            await interaction.response.send_message(
                "La verifica dalla pagina web non è disponibile: il pannello web del bot è spento. "
                "Avvisa lo staff del server.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "Apri il link e premi «Verificami». Il link è solo tuo e vale 15 minuti.",
            view=LinkVerificaView(link),
            ephemeral=True,
        )
        return
    if config.captcha_enabled and await db.get_guild_setting(
        guild.id, SETTING_CAPTCHA_TIPO, captcha_image.TIPO_TESTO
    ) == captcha_image.TIPO_IMMAGINE:
        await cog.manda_captcha_immagine(interaction, guild.id)
        await verify_repo.registra_evento(guild.id, interaction.user.id, "captcha_inviato")
        return
    if config.captcha_enabled:
        await interaction.response.send_modal(
            CaptchaModal(cog, guild.id, interaction.user.id)
        )
        await verify_repo.registra_evento(guild.id, interaction.user.id, "captcha_inviato")
        return

    # Senza captcha: risposta subito (3 secondi), poi controlli,
    # ruolo e log.
    await interaction.response.defer(ephemeral=True)
    outcome = await cog.run_checks_and_finalize(guild, interaction.user, captcha_ok=True)
    await interaction.followup.send(outcome.reason, ephemeral=True)
    await proponi_consenso_restore(
        lambda t, view: interaction.followup.send(t, view=view, ephemeral=True),
        guild, interaction.user, outcome,
    )


class VerifyCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # (server, utente) -> sfida aperta; in memoria e con tetto: dopo un riavvio si chiede un codice nuovo.
        self.sfide: BoundedCache = BoundedCache(2000)

    async def manda_captcha_immagine(self, interaction: discord.Interaction, guild_id: int) -> None:
        """Risponde al clic con l'immagine e il bottone che apre il modulo."""
        await interaction.response.defer(ephemeral=True)
        sfida = captcha_image.nuova_sfida()
        png = await asyncio.to_thread(captcha_image.disegna_immagine, sfida.codice)
        self.sfide.set((guild_id, interaction.user.id), sfida)
        await interaction.followup.send(
            "Ricopia le lettere dell'immagine (hai 3 minuti e 3 tentativi).",
            file=discord.File(io.BytesIO(png), filename="verifica.png"),
            view=CaptchaImmagineView(self, guild_id, interaction.user.id),
            ephemeral=True,
        )

    def _count_mutual_guilds(self, user_id: int, excluding_guild_id: int) -> int:
        """
        Quanti server, TRA QUELLI IN CUI SI TROVA QUESTO BOT, hanno
        anche loro questo utente come membro — non tutti i server
        dell'utente in assoluto (Discord non lo espone a un bot).
        Segnale debole, non prova — vedi core/verify_logic.py.
        """
        count = 0
        for guild in self.bot.guilds:
            if guild.id == excluding_guild_id:
                continue
            if guild.get_member(user_id) is not None:
                count += 1
        return count

    async def dai_ruoli_di_verifica(
        self, guild: discord.Guild, member: discord.Member, verified_role_id: int
    ) -> bool:
        """
        Dà il ruolo di verifica e gli eventuali ruoli extra, toglie il ruolo
        «non verificato». Ogni ruolo passa dal controllo dei permessi pericolosi
        (SEC-4/SEC-17: può averli presi dopo il setup). False se Discord rifiuta.
        """
        non_verificato_id = await db.get_guild_setting(guild.id, SETTING_RUOLO_NON_VERIFICATO)
        extra = list(await db.get_guild_setting(guild.id, SETTING_RUOLI_EXTRA) or [])
        da_dare = []
        for ruolo_id in [verified_role_id, *extra]:
            ruolo = guild.get_role(ruolo_id)
            if ruolo is None or check_role_assignable(guild, ruolo, guild.me, self_service=True) is not None:
                if ruolo_id == verified_role_id:
                    # Senza il ruolo di verifica non si completa niente, e il
                    # «non verificato» resta: altrimenti l'utente perde l'accesso.
                    logger.warning(
                        "Ruolo di verifica non assegnabile nel server %s: verifica non completata.",
                        guild.id,
                    )
                    return False
                continue
            da_dare.append(ruolo)
        try:
            await member.add_roles(*da_dare, reason="iYokai Verify")
        except discord.HTTPException as errore:
            logger.warning(
                "Impossibile assegnare il ruolo verify nel server %s: %s", guild.id, errore
            )
            return False
        non_verificato = guild.get_role(non_verificato_id) if non_verificato_id else None
        # Se coincide con un ruolo appena dato, toglierlo annullerebbe la verifica;
        # se è uguale o sopra il bot, Discord rifiuta: si salta senza tentare.
        if (
            non_verificato is not None
            and non_verificato.id not in {r.id for r in da_dare}
            and non_verificato in member.roles
            and non_verificato < guild.me.top_role
        ):
            try:
                await member.remove_roles(non_verificato, reason="iYokai Verify")
            except discord.HTTPException:
                logger.warning("Ruolo non verificato non tolto (server %s).", guild.id)
        return True

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """
        All'ingresso: verifica saltata per chi non è sospetto (VER-013), ruolo
        «non verificato» (VER-014), promemoria e scadenza nello scheduler (VER-008/011).
        """
        if member.bot or not await db.is_module_active_for_guild(member.guild.id, MODULE_VERIFY):
            return
        guild = member.guild
        await verify_repo.registra_evento(guild.id, member.id, "ingresso")
        config = await verify_repo.get_config(guild.id)
        # Un rientro riparte da zero: le scadenze dell'ingresso di prima non valgono più.
        for tipo in (VERIFY_PROMEMORIA, VERIFY_SCADENZA, VERIFY_ETA):
            await scheduler.cancel_for_user(guild.id, member.id, tipo)
        # Durante un raid nessuno riceve il ruolo senza verifica: potrebbe aprire
        # i canali che la quarantena chiude.
        if (
            config.verified_role_id is not None
            and not raid_in_corso(guild.id)
            and not await verify_repo.is_blacklisted(guild.id, member.id)
        ):
            # VER-020: modalità cieca, il ruolo arriva subito e il log lo dice.
            if sospesa_adesso(await db.get_guild_setting(guild.id, SETTING_SOSPESA_FINO, 0)):
                if await self.dai_ruoli_di_verifica(guild, member, config.verified_role_id):
                    await verify_repo.log_attempt(guild.id, member.id, True, "Modalità cieca: verifica sospesa")
                    return
            elif (
                await db.get_guild_setting(guild.id, SETTING_SOLO_SOSPETTI, False)
                and not account_sospetto(member.created_at, member.avatar is not None)
                and meets_account_age(member.created_at, config.min_account_age_days)
            ):
                if await self.dai_ruoli_di_verifica(guild, member, config.verified_role_id):
                    await verify_repo.log_attempt(guild.id, member.id, True, "Account non sospetto: verifica saltata")
                    return
        attesa = 0
        if config.min_account_age_days > 0 and not meets_account_age(member.created_at, config.min_account_age_days):
            if not await verify_repo.is_whitelisted(guild.id, member.id):
                maggiorenne = quando_maggiorenne(member.created_at, config.min_account_age_days)
                if (await db.get_guild_setting(guild.id, SETTING_AZIONE_ETA, "attendi") or "attendi") == "kick":
                    await verify_repo.log_attempt(guild.id, member.id, False, "Account troppo giovane: espulso")
                    await self._punisci(guild, member, "kick", "iYokai Verify: account troppo giovane")
                    return
                attesa = max(0, int((maggiorenne - discord.utils.utcnow()).total_seconds()))
                await scheduler.schedule(guild.id, member.id, VERIFY_ETA, maggiorenne)
        ruolo_id = await db.get_guild_setting(guild.id, SETTING_RUOLO_NON_VERIFICATO)
        ruolo = guild.get_role(ruolo_id) if ruolo_id else None
        if ruolo is not None and check_role_assignable(guild, ruolo, guild.me, self_service=True) is None:
            try:
                await member.add_roles(ruolo, reason="iYokai Verify: in attesa di verifica")
            except discord.HTTPException:
                logger.warning("Ruolo non verificato non dato a %s (server %s).", member.id, guild.id)
        if config.verified_role_id is None:
            return
        for chiave, tipo in ((SETTING_PROMEMORIA_MINUTI, VERIFY_PROMEMORIA), (SETTING_SCADENZA_MINUTI, VERIFY_SCADENZA)):
            minuti = await db.get_guild_setting(guild.id, chiave, 0) or 0
            if minuti > 0:
                await scheduler.schedule(guild.id, member.id, tipo, in_seconds(attesa + minuti * 60))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """VER-030: le uscite entrano nelle statistiche."""
        if member.bot or not await db.is_module_active_for_guild(member.guild.id, MODULE_VERIFY):
            return
        await verify_repo.registra_evento(member.guild.id, member.id, "uscita")

    async def _da_verificare(self, guild_id: int, user_id: int):
        """Il membro ancora senza il ruolo di verifica, con il server e la configurazione; altrimenti None."""
        guild = self.bot.get_guild(guild_id)
        if guild is None or not await db.is_module_active_for_guild(guild_id, MODULE_VERIFY):
            return None
        member = guild.get_member(user_id)
        config = await verify_repo.get_config(guild_id)
        if member is None or config.verified_role_id is None:
            return None
        if any(r.id == config.verified_role_id for r in member.roles):
            return None
        return guild, member, config

    async def handle_promemoria(self, guild_id: int, user_id: int, payload: dict) -> None:
        """VER-008/009: promemoria in DM; con i DM chiusi un avviso breve nel canale del pannello."""
        trovato = await self._da_verificare(guild_id, user_id)
        if trovato is None or raid_in_corso(guild_id):
            return  # durante un raid niente messaggi ai nuovi arrivati
        guild, member, config = trovato
        if await self._manda_dm(member, self._testo_invito(guild, config, "Promemoria: per entrare in")):
            return
        canale = guild.get_channel(config.panel_channel_id) if config.panel_channel_id else None
        if isinstance(canale, discord.TextChannel):
            try:
                await canale.send(
                    f"{member.mention} hai i messaggi privati chiusi: completa la verifica qui.",
                    delete_after=SECONDI_AVVISO_CANALE,
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
            except discord.HTTPException:
                pass

    @staticmethod
    def _testo_invito(guild: discord.Guild, config, inizio: str) -> str:
        dove = f" in <#{config.panel_channel_id}>" if config.panel_channel_id else ""
        return f"{inizio} **{guild.name}** devi ancora completare la verifica{dove}."

    @staticmethod
    async def _manda_dm(member: discord.Member, testo: str) -> bool:
        """True se il DM è partito; False se i messaggi privati sono chiusi."""
        try:
            await member.send(testo)
        except discord.HTTPException:
            return False
        return True

    async def handle_eta(self, guild_id: int, user_id: int, payload: dict) -> None:
        """VER-019: l'account ha l'età richiesta, avviso a chi aspettava."""
        trovato = await self._da_verificare(guild_id, user_id)
        if trovato is None or raid_in_corso(guild_id):
            return
        guild, member, config = trovato
        await self._manda_dm(member, self._testo_invito(guild, config, "Il tuo account ora ha l'età richiesta: per entrare in"))

    async def handle_scadenza(self, guild_id: int, user_id: int, payload: dict) -> None:
        """VER-011: tempo scaduto senza verifica: kick o ban."""
        trovato = await self._da_verificare(guild_id, user_id)
        if trovato is None:
            return
        guild, member, _ = trovato
        azione = await db.get_guild_setting(guild_id, SETTING_AZIONE_SCADENZA, "kick") or "kick"
        await verify_repo.log_attempt(guild_id, user_id, False, f"Tempo per la verifica scaduto: {azione}")
        await self._punisci(guild, member, azione, "iYokai Verify: tempo per la verifica scaduto")

    async def _punisci(self, guild: discord.Guild, member: discord.Member, azione: str, motivo: str) -> bool:
        """Quarantena, kick o ban di chi non passa la verifica. Il DM parte prima di kick e ban."""
        try:
            if azione == "quarantena":
                ruolo = await ruolo_quarantena(guild, allinea=False)
                if ruolo is None:
                    return False
                await member.add_roles(ruolo, reason=motivo)
            elif azione in ("kick", "ban"):
                try:
                    await member.send(f"{guild.name}: {motivo.split(': ', 1)[-1]}.")
                except discord.HTTPException:
                    pass
                if azione == "kick":
                    await member.kick(reason=motivo)
                else:
                    await guild.ban(member, reason=motivo, delete_message_seconds=0)
            else:
                return False
        except discord.HTTPException:
            logger.warning("Verify: %s non riuscito su %s (server %s).", azione, member.id, guild.id)
            return False
        return True

    async def run_checks_and_finalize(
        self, guild: discord.Guild, member: discord.Member, captcha_ok: bool
    ):
        config = await verify_repo.get_config(guild.id)

        # Chi ha già il ruolo è già verificato: niente nuovo tentativo, niente riga nel log.
        if config.verified_role_id is not None and any(
            r.id == config.verified_role_id for r in member.roles
        ):
            return VerifyOutcome(True, "You are already verified.")

        is_whitelisted = await verify_repo.is_whitelisted(guild.id, member.id)
        is_blacklisted = await verify_repo.is_blacklisted(guild.id, member.id)
        age_ok = meets_account_age(member.created_at, config.min_account_age_days)
        mutual_count = self._count_mutual_guilds(member.id, guild.id)
        mutual_ok = meets_mutual_servers(mutual_count, config.min_mutual_servers)

        outcome = decide_verify_outcome(
            is_whitelisted, is_blacklisted, age_ok, mutual_ok, captcha_ok
        )

        if not outcome.success and not age_ok and not is_blacklisted:
            fino = int(quando_maggiorenne(member.created_at, config.min_account_age_days).timestamp())
            outcome = VerifyOutcome(False, f"{outcome.reason} You can verify from <t:{fino}:D>.")

        await verify_repo.log_attempt(guild.id, member.id, outcome.success, outcome.reason)

        if not outcome.success:
            # VER-012: azione scelta dal server su chi non passa.
            azione = await db.get_guild_setting(guild.id, SETTING_AZIONE_FALLITA, "niente") or "niente"
            # VER-019 «attendi»: chi preme troppo presto aspetta, non viene punito.
            if not age_ok and not is_whitelisted and not is_blacklisted and (
                await db.get_guild_setting(guild.id, SETTING_AZIONE_ETA, "attendi") or "attendi"
            ) == "attendi":
                azione = "niente"
            if azione != "niente":
                tentativi = await verify_repo.get_recent_attempts(
                    guild.id, member.id, FALLIMENTI_CAPTCHA_PRIMA_DELL_AZIONE
                )
                ultimi = esiti_nella_finestra(tentativi, discord.utils.utcnow())
                azione = azione_dopo_fallimento(azione, outcome.reason, ultimi)
                if azione != "niente":
                    await self._punisci(guild, member, azione, "iYokai Verify: verifica non superata")

        if outcome.success and config.verified_role_id is not None:
            if not await self.dai_ruoli_di_verifica(guild, member, config.verified_role_id):
                outcome = VerifyOutcome(
                    True,
                    "All checks passed, but I couldn't give you the role. "
                    "Please contact the server staff.",
                )

        if config.log_channel_id is not None:
            log_channel = guild.get_channel(config.log_channel_id)
            if isinstance(log_channel, discord.TextChannel):
                compatto = await db.get_guild_setting(guild.id, SETTING_LOG_COMPATTO, False)
                embed = discord.Embed(
                    title="Verify succeeded" if outcome.success else "Verify failed",
                    color=discord.Color.green() if outcome.success else discord.Color.red(),
                )
                if compatto:
                    embed.description = f"{member.mention} ({member.id}): {outcome.reason}"[:400]
                else:
                    embed.add_field(
                        name="User", value=f"{member.mention} ({member.id})", inline=False
                    )
                    embed.add_field(name="Reason", value=outcome.reason, inline=False)
                try:
                    await log_channel.send(embed=embed)
                except discord.HTTPException:
                    pass

        return outcome

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "security",
        nome="setup",
        descrizione="Configura il Verify.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(
        method="Modalità: bottone (supporta captcha), reazione o pagina web (riconosce gli account doppi)",
        verified_role="Ruolo da assegnare dopo la verifica",
        min_account_age_days="Età minima dell'account in giorni (0 = disattivato)",
        min_mutual_servers="Server in comune minimi richiesti (0 = disattivato)",
        captcha_enabled="Richiedi un captcha (solo modalità bottone)",
        captcha_tipo="Tipo di captcha: somma scritta o immagine con lettere storte",
        log_channel="Canale dove loggare ogni tentativo",
    )
    @app_commands.choices(
        method=[
            app_commands.Choice(name="Button", value="button"),
            app_commands.Choice(name="Reaction", value="reaction"),
            app_commands.Choice(name="Pagina web", value=METODO_WEB),
        ],
        captcha_tipo=[
            app_commands.Choice(name="Somma scritta", value=captcha_image.TIPO_TESTO),
            app_commands.Choice(name="Immagine", value=captcha_image.TIPO_IMMAGINE),
        ],
    )
    async def setup_cmd(
        self,
        interaction: discord.Interaction,
        method: app_commands.Choice[str],
        verified_role: discord.Role,
        min_account_age_days: app_commands.Range[int, 0, 3650] = 0,
        min_mutual_servers: app_commands.Range[int, 0, 100] = 0,
        captcha_enabled: bool = False,
        log_channel: discord.TextChannel | None = None,
        captcha_tipo: app_commands.Choice[str] | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        # Scegliere il tipo «immagine» accende il captcha da solo.
        immagine = captcha_tipo is not None and captcha_tipo.value == captcha_image.TIPO_IMMAGINE
        captcha_enabled = captcha_enabled or immagine
        if method.value == "reaction" and captcha_enabled:
            await interaction.response.send_message(
                "Il captcha non è supportato in modalità reaction: una "
                "reazione non può aprire una finestra di verifica. Usa la "
                "modalità Button se vuoi il captcha.",
                ephemeral=True,
            )
            return
        if method.value == METODO_WEB and captcha_enabled:
            await interaction.response.send_message(
                "La pagina web sostituisce il captcha: scegli la pagina web senza captcha, "
                "oppure il bottone con il captcha.",
                ephemeral=True,
            )
            return
        if method.value == METODO_WEB and link_verifica_web(interaction.guild.id, interaction.user.id) is None:
            await interaction.response.send_message(
                "La verifica dalla pagina web richiede il pannello web del bot acceso: per ora non lo è. "
                "Scegli il bottone o la reazione.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            return

        motivo_rifiuto = check_role_assignable(
            interaction.guild, verified_role, interaction.user, self_service=True
        )
        if motivo_rifiuto is not None:
            await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
            return

        await verify_repo.set_config(
            guild_id=interaction.guild.id,
            method=method.value,
            verified_role_id=verified_role.id,
            min_account_age_days=min_account_age_days,
            min_mutual_servers=min_mutual_servers,
            captcha_enabled=captcha_enabled,
            log_channel_id=log_channel.id if log_channel else None,
        )
        if captcha_tipo is not None:
            await db.set_guild_setting(
                interaction.guild.id, SETTING_CAPTCHA_TIPO, captcha_tipo.value, changed_by=interaction.user.id
            )

        await interaction.response.send_message(
            f"Verify configurato: modalità **{method.name}**, ruolo "
            f"{verified_role.mention}. Usa /security verify panel per pubblicare "
            f"il pannello.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "security",
        nome="panel",
        descrizione="Pubblica il pannello di verifica.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    async def panel_cmd(self, interaction: discord.Interaction) -> None:
        # Un pannello pubblicato con il modulo spento risponderebbe "Verify non è attivo".
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return

        config = await verify_repo.get_config(interaction.guild.id)
        if config.verified_role_id is None:
            await interaction.response.send_message(
                "Configura prima il Verify con /security verify setup.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="✅ Server Verification",
            description="Click the button below to verify and gain access to the server."
            if config.method in ("button", METODO_WEB)
            else f"React with {VERIFY_REACTION_EMOJI} to verify and gain access to the server.",
            color=discord.Color.blurple(),
        )

        if config.method in ("button", METODO_WEB):
            await interaction.response.send_message(embed=embed, view=VerifyPanelView())
            sent = await interaction.original_response()
        else:
            await interaction.response.send_message(embed=embed)
            sent = await interaction.original_response()
            try:
                await sent.add_reaction(VERIFY_REACTION_EMOJI)
            except discord.HTTPException:
                await interaction.followup.send(
                    f"Non riesco ad aggiungere la reazione {VERIFY_REACTION_EMOJI} al pannello "
                    "(mi manca Aggiungi reazioni?). Aggiungila a mano: il pannello funziona lo stesso.",
                    ephemeral=True,
                )

        await verify_repo.set_panel_message(interaction.guild.id, sent.channel.id, sent.id)

    @comando_di_gruppo(
        "security",
        nome="whitelist-add",
        descrizione="Aggiungi un utente alla whitelist.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(member="L'utente (anche se non è nel server)")
    async def whitelist_add(self, interaction: discord.Interaction, member: discord.User) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        await verify_repo.add_whitelist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} aggiunto alla whitelist.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="whitelist-remove",
        descrizione="Rimuovi un utente dalla whitelist.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(member="L'utente (anche se non è nel server)")
    async def whitelist_remove(self, interaction: discord.Interaction, member: discord.User) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        await verify_repo.remove_whitelist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} rimosso dalla whitelist.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="blacklist-add",
        descrizione="Aggiungi un utente alla blacklist.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(member="L'utente (anche se non è nel server)")
    async def blacklist_add(self, interaction: discord.Interaction, member: discord.User) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        await verify_repo.add_blacklist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} aggiunto alla blacklist.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="blacklist-remove",
        descrizione="Rimuovi un utente dalla blacklist.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(member="L'utente (anche se non è nel server)")
    async def blacklist_remove(self, interaction: discord.Interaction, member: discord.User) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        await verify_repo.remove_blacklist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} rimosso dalla blacklist.", ephemeral=True)


    @comando_di_gruppo(
        "security",
        nome="opzioni",
        descrizione="Ruolo «non verificato» e ruoli extra.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(
        non_verificato="Dato all'ingresso, tolto alla verifica",
        extra_1="Ruolo extra alla verifica",
        extra_2="Altro ruolo extra",
        extra_3="Altro ruolo extra",
        azzera="Togli questi ruoli",
        log_compatto="Nel log una riga sola per tentativo, invece della scheda completa",
    )
    async def options_cmd(
        self,
        interaction: discord.Interaction,
        non_verificato: discord.Role | None = None,
        extra_1: discord.Role | None = None,
        extra_2: discord.Role | None = None,
        extra_3: discord.Role | None = None,
        azzera: bool = False,
        log_compatto: bool | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        guild = interaction.guild
        if log_compatto is not None:
            await db.set_guild_setting(guild.id, SETTING_LOG_COMPATTO, log_compatto, changed_by=interaction.user.id)
        if azzera:
            await db.set_guild_setting(guild.id, SETTING_RUOLO_NON_VERIFICATO, None)
            await db.set_guild_setting(guild.id, SETTING_RUOLI_EXTRA, None)
            await interaction.response.send_message("Ruoli extra della verifica tolti.", ephemeral=True)
            return
        extra = [r for r in (extra_1, extra_2, extra_3) if r is not None]
        for ruolo in ([non_verificato] if non_verificato else []) + extra:
            motivo = check_role_assignable(guild, ruolo, interaction.user, self_service=True)
            if motivo is not None:
                await interaction.response.send_message(f"{ruolo.mention}: {motivo}", ephemeral=True)
                return
        if non_verificato is not None:
            await db.set_guild_setting(
                guild.id, SETTING_RUOLO_NON_VERIFICATO, non_verificato.id, changed_by=interaction.user.id
            )
        if extra:
            await db.set_guild_setting(
                guild.id, SETTING_RUOLI_EXTRA, [r.id for r in extra][:MAX_RUOLI_EXTRA],
                changed_by=interaction.user.id,
            )
        await interaction.response.send_message("Opzioni della verifica salvate.", ephemeral=True)

    @comando_di_gruppo(
        "utility",
        nome="verifica",
        descrizione="Verificati in questo server (come il bottone del pannello).",
    )
    async def verifica_cmd(self, interaction: discord.Interaction) -> None:
        """VER-010: lo stesso percorso del bottone, per chi non trova il pannello."""
        await avvia_verifica(interaction)

    @comando_di_gruppo(
        "security",
        nome="tempi",
        descrizione="Promemoria, tempo massimo, azione su chi fallisce, verifica solo ai sospetti.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(
        promemoria_minuti="DM di promemoria dopo questi minuti (0 = spento)",
        scadenza_minuti="Tempo massimo per verificarsi, in minuti (0 = nessun limite)",
        azione_scadenza="Cosa fare a chi non si verifica in tempo",
        azione_fallita="Cosa fare a chi non passa la verifica",
        solo_sospetti="Verifica solo account giovani (meno di 7 giorni) o senza avatar",
        azione_eta="Account più giovane dell'età minima: aspetta il via libera o viene espulso",
        sospendi_ore="Modalità cieca: per queste ore chi entra riceve subito il ruolo (0 = spenta)",
    )
    @app_commands.choices(
        azione_scadenza=[
            app_commands.Choice(name="Kick", value="kick"),
            app_commands.Choice(name="Ban", value="ban"),
        ],
        azione_fallita=[app_commands.Choice(name=a.capitalize(), value=a) for a in AZIONI_FALLITA],
        azione_eta=[app_commands.Choice(name=a.capitalize(), value=a) for a in AZIONI_ETA],
    )
    async def tempi_cmd(
        self,
        interaction: discord.Interaction,
        promemoria_minuti: app_commands.Range[int, 0, 1440] | None = None,
        scadenza_minuti: app_commands.Range[int, 0, 1440] | None = None,
        azione_scadenza: app_commands.Choice[str] | None = None,
        azione_fallita: app_commands.Choice[str] | None = None,
        solo_sospetti: bool | None = None,
        azione_eta: app_commands.Choice[str] | None = None,
        sospendi_ore: app_commands.Range[int, 0, 720] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        gid, chi = interaction.guild.id, interaction.user.id
        for chiave, valore in (
            (SETTING_PROMEMORIA_MINUTI, promemoria_minuti),
            (SETTING_SCADENZA_MINUTI, scadenza_minuti),
            (SETTING_AZIONE_SCADENZA, azione_scadenza.value if azione_scadenza else None),
            (SETTING_AZIONE_FALLITA, azione_fallita.value if azione_fallita else None),
            (SETTING_SOLO_SOSPETTI, solo_sospetti),
            (SETTING_AZIONE_ETA, azione_eta.value if azione_eta else None),
            (SETTING_SOSPESA_FINO, None if sospendi_ore is None else (
                int(time.time()) + sospendi_ore * 3600 if sospendi_ore else 0)),
        ):
            if valore is not None:
                await db.set_guild_setting(gid, chiave, valore, changed_by=chi)
        promemoria = await db.get_guild_setting(gid, SETTING_PROMEMORIA_MINUTI, 0) or 0
        scadenza = await db.get_guild_setting(gid, SETTING_SCADENZA_MINUTI, 0) or 0
        await interaction.response.send_message(
            f"Promemoria: {f'dopo {promemoria} minuti' if promemoria else 'spento'}. "
            f"Tempo massimo: {f'{scadenza} minuti, poi ' + (await db.get_guild_setting(gid, SETTING_AZIONE_SCADENZA, 'kick') or 'kick') if scadenza else 'nessuno'}. "
            f"Chi non passa: {await db.get_guild_setting(gid, SETTING_AZIONE_FALLITA, 'niente') or 'niente'}. "
            f"Solo account sospetti: {'sì' if await db.get_guild_setting(gid, SETTING_SOLO_SOSPETTI, False) else 'no'}. "
            f"Account troppo giovane: {await db.get_guild_setting(gid, SETTING_AZIONE_ETA, 'attendi') or 'attendi'}. "
            f"Modalità cieca: "
            f"{'attiva fino a <t:' + str(fino) + ':f>' if sospesa_adesso(fino := await db.get_guild_setting(gid, SETTING_SOSPESA_FINO, 0)) else 'spenta'}. "
            "Valgono per chi entra da adesso.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "security",
        nome="manuale",
        descrizione="Verifica a mano un membro, senza controlli.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(member="Il membro da verificare")
    async def manual_cmd(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        config = await verify_repo.get_config(interaction.guild.id)
        if config.verified_role_id is None:
            await interaction.response.send_message(
                "Configura prima il Verify con /security verify setup.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        if not await self.dai_ruoli_di_verifica(interaction.guild, member, config.verified_role_id):
            await interaction.followup.send(
                "Non sono riuscito a dare i ruoli: controlla i miei permessi.", ephemeral=True
            )
            return
        await verify_repo.log_attempt(
            interaction.guild.id, member.id, True, f"Verificato a mano da {interaction.user.id}"
        )
        await interaction.followup.send(f"{member.mention} verificato a mano.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="invia",
        descrizione="Rimanda a un membro il messaggio per verificarsi.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(membro="Il membro a cui mandare l'invito in DM")
    async def send_cmd(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        """VER-017."""
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        trovato = await self._da_verificare(interaction.guild.id, membro.id)
        if trovato is None:
            await interaction.response.send_message(
                "Il membro è già verificato, oppure il Verify non è configurato.", ephemeral=True
            )
            return
        guild, _, config = trovato
        if await self._manda_dm(membro, self._testo_invito(guild, config, "Per entrare in")):
            await interaction.response.send_message(f"Invito inviato a {membro.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"{membro.mention} ha i messaggi privati chiusi: non ho potuto scrivergli.", ephemeral=True
            )

    @comando_di_gruppo(
        "security",
        nome="tentativi",
        descrizione="Tentativi di verifica di un utente.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(
        member="L'utente (anche se non è nel server)",
        csv="Esporta in un file CSV (senza utente: tutto il server, una volta all'ora)",
    )
    async def attempts_cmd(
        self, interaction: discord.Interaction, member: discord.User | None = None, csv: bool = False
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        if member is None and not csv:
            await interaction.response.send_message(
                "Indica un utente, oppure scegli l'esportazione CSV di tutto il server.", ephemeral=True
            )
            return
        gid = interaction.guild.id
        if csv:
            await self._esporta_csv(interaction, gid, member)
            return
        tentativi = await verify_repo.get_recent_attempts(gid, member.id, 15)
        if not tentativi:
            await interaction.response.send_message("Nessun tentativo registrato.", ephemeral=True)
            return
        righe = [
            f"{'✅' if ok else '❌'} {quando.strftime('%d/%m/%Y %H:%M')} — {motivo[:150]}"
            for ok, motivo, quando in tentativi
        ]
        embed = discord.Embed(
            title=f"Tentativi di {member}", description="\n".join(righe)[:4000], color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @staticmethod
    async def _esporta_csv(interaction: discord.Interaction, gid: int, member: discord.User | None) -> None:
        """VER-031: CSV dei tentativi (ultimi 5000). Quello di tutto il server, una volta all'ora."""
        if member is None:
            ultimo = _ultimo_csv.get(gid)
            if ultimo is not None and time.monotonic() - ultimo < SECONDI_TRA_CSV:
                await interaction.response.send_message(
                    "L'esportazione di tutto il server si può chiedere una volta all'ora. "
                    "Riprova più tardi, oppure indica un utente.",
                    ephemeral=True,
                )
                return
            _ultimo_csv.set(gid, time.monotonic())
        await interaction.response.defer(ephemeral=True)
        righe = await verify_repo.tentativi_per_csv(gid, member.id if member else None)
        buffer = io.StringIO()
        scrittore = csv.writer(buffer)
        scrittore.writerow(["utente", "esito", "motivo", "data"])
        for utente, ok, motivo, quando in righe:
            # Un motivo che inizia con = + - @ sarebbe una formula in un foglio di calcolo.
            sicuro = "'" + motivo if motivo[:1] in ("=", "+", "-", "@") else motivo
            scrittore.writerow([utente, "ok" if ok else "no", sicuro, quando.strftime("%Y-%m-%d %H:%M:%S")])
        file = discord.File(io.BytesIO(buffer.getvalue().encode("utf-8")), filename="verifica_tentativi.csv")
        await interaction.followup.send(f"{len(righe)} tentativi esportati.", file=file, ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="statistiche",
        descrizione="Ingressi, uscite, captcha e verifiche.",
        sottogruppo=("verify", "Sistema di verifica dei nuovi membri."),
    )
    @app_commands.describe(giorni="Giorni indietro (default 7)")
    async def stats_cmd(
        self, interaction: discord.Interaction, giorni: app_commands.Range[int, 1, 365] = 7
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_VERIFY):
            return
        s = await verify_repo.statistiche(interaction.guild.id, giorni)
        await interaction.response.send_message(
            f"Ultimi {giorni} giorni.\n"
            f"Ingressi: **{s['ingressi']}**, uscite: **{s['uscite']}**.\n"
            f"Captcha inviati: **{s['captcha_inviati']}**, falliti: **{s['captcha_falliti']}**.\n"
            f"Verifiche completate: **{s['completate']}**.\n"
            f"Espulsi o bannati per tempo scaduto: **{s['scaduti']}**.",
            ephemeral=True,
        )

    # ================================================================
    # Modalità reaction
    # ================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None or payload.member.bot:
            return
        if str(payload.emoji) != VERIFY_REACTION_EMOJI:
            return

        # SEC-10: un utente in blacklist non deve potersi verificare
        # reagendo al pannello.
        if await blacklist_repo.is_user_blacklisted(payload.member.id):
            return

        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_VERIFY):
            return

        config = await verify_repo.get_config(payload.guild_id)
        if config.method != "reaction" or config.panel_message_id != payload.message_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        outcome = await self.run_checks_and_finalize(guild, payload.member, captcha_ok=True)

        try:
            await payload.member.send(outcome.reason)
        except discord.HTTPException:
            return  # DM chiusi: l'esito resta comunque nel log
        await proponi_consenso_restore(payload.member.send, guild, payload.member, outcome)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_VERIFY,
            display_name="Verify",
            category="security",
            description="Verifica dei nuovi membri: bottone/reazione, captcha, età account, mutual servers.",
            premium_capable=False,
        )
    )
    cog = VerifyCog(bot)
    await bot.add_cog(cog)
    bot.add_view(VerifyPanelView())
    scheduler.register_handler(VERIFY_PROMEMORIA, cog.handle_promemoria)
    scheduler.register_handler(VERIFY_SCADENZA, cog.handle_scadenza)
    scheduler.register_handler(VERIFY_ETA, cog.handle_eta)

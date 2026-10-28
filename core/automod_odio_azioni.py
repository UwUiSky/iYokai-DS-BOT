"""
core/automod_odio_azioni.py
===========================
Azioni della difesa dalle parole d'odio (D35) che parlano con Discord: la regola nativa
di blocco preventivo (creata e tenuta allineata dal bot) e il trattamento di una parola
sospetta (giudizio dell'AI, messaggio cancellato, richiamo all'utente che si cancella da
solo, timeout dopo N richiami in X minuti). La logica sta in core/odio_*.py.
Funzioni coperte: SPEC §6 (D35)
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta

import discord

from core import bot_roles
from core import channel_router as router
from core import odio_moderazione
from core.automod_odio_nativo_logic import RULE_NAME_ODIO, costruisci_regex
from core.automod_parole_logic import trova
from core.odio_opzioni import OpzioniOdio
from core.odio_opzioni import leggi as leggi_opzioni
from core.odio_richiami_logic import ContatoreRichiami
from core.repositories.automod_advanced_repo import automod_advanced_repo

logger = logging.getLogger("iyokai.automod_odio")

MAX_REGOLE_A_PAROLE = 6  # regole «parole chiave» per server (LIMITI.md 1.7)
SECONDI_RICHIAMO_VISIBILE = 10
VIOLATION_PAROLE_SOSPETTE = "parole_sospette"

contatore = ContatoreRichiami()


async def sincronizza_blocco(guild: discord.Guild, opz: OpzioniOdio) -> str | None:
    """
    Crea, aggiorna o toglie la regola nativa di blocco preventivo. Restituisce un avviso
    per l'admin (limite di Discord, permessi) oppure None.
    """
    try:
        regole = await guild.fetch_automod_rules()
    except discord.Forbidden:
        return "Non ho il permesso di gestire le regole AutoMod di questo server (serve Gestire server)."
    except discord.HTTPException as errore:
        return f"Discord non mi ha fatto leggere le regole AutoMod: {str(errore)[:200]}"
    nostra = next((r for r in regole if r.name == RULE_NAME_ODIO), None)
    try:
        if not opz.blocco:
            if nostra is not None:
                await nostra.delete(reason="Blocco preventivo delle frasi d'odio spento")
            return None
        regex = costruisci_regex()
        trigger = discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.keyword, regex_patterns=list(regex.pattern))
        azioni = [discord.AutoModRuleAction(custom_message=opz.messaggio)]
        if nostra is not None:
            await nostra.edit(trigger=trigger, actions=azioni, enabled=True, reason="Blocco preventivo delle frasi d'odio")
        else:
            a_parole = sum(1 for r in regole if r.trigger.type == discord.AutoModRuleTriggerType.keyword)
            if a_parole >= MAX_REGOLE_A_PAROLE:
                return (
                    f"Questo server ha già {MAX_REGOLE_A_PAROLE} regole AutoMod a parole chiave, il massimo di Discord: "
                    "non posso creare il blocco. Elimina una regola dal pannello di Discord e riprova."
                )
            await guild.create_automod_rule(
                name=RULE_NAME_ODIO, event_type=discord.AutoModRuleEventType.message_send, trigger=trigger,
                actions=azioni, enabled=True, reason="Blocco preventivo delle frasi d'odio",
            )
        if regex.insulti_esclusi:
            return f"{regex.insulti_esclusi} insulti non sono entrati nella regola (limite di Discord): li ferma comunque il filtro del bot."
    except discord.HTTPException as errore:
        return f"Discord ha rifiutato la regola: {str(errore)[:200]}"
    return None


def _protetto(membro: discord.Member) -> bool:
    """Mai il timeout automatico a chi gestisce il server o a chi lo possiede."""
    return membro.guild.owner_id == membro.id or membro.guild_permissions.administrator or membro.guild_permissions.manage_guild


async def controlla_sospetta(message: discord.Message, testo: str, filtro_sospette, archivio=None) -> bool:
    """
    True se il messaggio e' stato trattato come insulto (cancellato, richiamo dato): chi chiama
    non deve fare altro. False se non c'e' parola sospetta o l'AI dice che e' un uso normale.
    """
    if not testo or trova(testo, filtro_sospette) is None:
        return False
    guild, autore = message.guild, message.author
    esito = await odio_moderazione.giudica_sospetta(guild.id, message.channel.id, autore.id, testo)
    if not esito.cancella:
        return False
    if esito.giudizio is not None:
        await odio_moderazione.segnala_varianti(guild.id, testo, esito.giudizio, archivio)
    cancellato = False
    try:
        await bot_roles.cancella_messaggio(message)
        cancellato = True
    except (discord.NotFound, discord.Forbidden):
        pass
    opz = await leggi_opzioni(guild.id, archivio)
    n = contatore.registra(guild.id, autore.id, time.monotonic(), opz.minuti * 60)
    azioni = ["delete"] if cancellato else []
    timeout = n >= opz.soglia and not _protetto(autore)
    if timeout:
        try:
            await bot_roles.isola(
                autore, timedelta(minutes=opz.timeout_minuti), reason=f"AutoMod: {opz.soglia} richiami per parole d'odio in {opz.minuti} minuti"
            )
            azioni.append("timeout")
            contatore.azzera(guild.id, autore.id)
        except (discord.Forbidden, discord.HTTPException):
            timeout = False
    await _avvisa_utente(message, n, opz, timeout, esito.motivo)
    await _registra(message, azioni, esito.motivo, n, opz)
    return True


def _testo_richiamo(n: int, opz: OpzioniOdio, timeout: bool, ai_ferma: bool) -> str:
    base = "Messaggio rimosso: contenuto offensivo o razzista. Rispetta le regole del server."
    if ai_ferma:
        base = "Messaggio rimosso per sicurezza: contiene una parola vietata e non ho potuto controllare il contesto."
    if timeout:
        return f"{base} Richiamo {n} di {opz.soglia}: timeout di {opz.timeout_minuti} minuti."
    return f"{base} Richiamo {n} di {opz.soglia} in {opz.minuti} minuti."


async def _avvisa_utente(message: discord.Message, n: int, opz: OpzioniOdio, timeout: bool, motivo: str) -> None:
    """Risposta nel canale che si cancella dopo pochi secondi; se il canale non lo permette, DM."""
    testo = _testo_richiamo(n, opz, timeout, motivo in (odio_moderazione.MOTIVO_AI_FERMA, odio_moderazione.MOTIVO_AI_INCERTA))
    menzioni = discord.AllowedMentions(users=[message.author], roles=False, everyone=False)
    try:
        await message.channel.send(
            f"{message.author.mention} {testo}", delete_after=SECONDI_RICHIAMO_VISIBILE, allowed_mentions=menzioni
        )
        return
    except (discord.Forbidden, discord.HTTPException):
        pass
    try:
        await message.author.send(f"{message.guild.name}: {testo}")
    except (discord.Forbidden, discord.HTTPException):
        pass  # DM chiusi: il log dello staff dice comunque cosa e' successo


async def _registra(message: discord.Message, azioni: list[str], motivo: str, n: int, opz: OpzioniOdio) -> None:
    guild = message.guild
    contenuto = (message.content or "")[:200]
    await automod_advanced_repo.log_action(
        guild.id, message.author.id, message.channel.id, VIOLATION_PAROLE_SOSPETTE, tuple(azioni), contenuto
    )
    impostazioni = await automod_advanced_repo.get_settings(guild.id)
    canale = await router.destinazione(guild, router.TIPO_AUTOMOD, impostazioni.log_channel_id)
    if canale is None:
        return
    embed = discord.Embed(title="🛡️ AutoMod — Parola sospetta giudicata", color=discord.Color.orange())
    embed.add_field(name="Utente", value=f"{message.author.mention} ({message.author.id})", inline=False)
    embed.add_field(name="Canale", value=message.channel.mention, inline=True)
    embed.add_field(name="Azioni eseguite", value=", ".join(azioni) or "nessuna", inline=True)
    embed.add_field(name="Giudizio", value=_etichetta_motivo(motivo), inline=True)
    embed.add_field(name="Richiami", value=f"{n} di {opz.soglia} in {opz.minuti} min", inline=True)
    if contenuto:
        embed.add_field(name="Contenuto", value=contenuto, inline=False)
    await router.invia_a(canale, guild, router.TIPO_AUTOMOD, embed=embed)


def _etichetta_motivo(motivo: str) -> str:
    return {
        odio_moderazione.MOTIVO_AI: "l'AI ha letto un insulto",
        odio_moderazione.MOTIVO_CACHE: "stessa frase già giudicata (insulto)",
        odio_moderazione.MOTIVO_AI_FERMA: "AI ferma o spenta: lato sicuro",
        odio_moderazione.MOTIVO_AI_INCERTA: "risposta dell'AI non chiara: lato sicuro",
    }.get(motivo, motivo)

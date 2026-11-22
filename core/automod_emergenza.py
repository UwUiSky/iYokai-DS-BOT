"""
core/automod_emergenza.py
=========================
Due difese di emergenza dell'AutoMod: il blocco automatico dei canali quando arrivano troppe menzioni in pochi secondi
(AMD-057) e la modalità panico, che dopo un'ondata di violazioni mette in timeout subito gli account sospetti che
violano ancora una regola (AMD-071). Stato in memoria, con tetto. La scelta (soglie, durate) è una sola chiave di
impostazione per server: `automod_emergenza`.
Funzioni coperte: AMD-057, AMD-071 (usa core/lockdown_service.py per il blocco)
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import discord

from core import bot_roles
from core.automod_azioni import e_protetto, fuori_portata
from core.bounded_cache import BoundedCache
from core.database import db

logger = logging.getLogger("iyokai.automod.emergenza")

SETTING_EMERGENZA = "automod_emergenza"
BASE = {
    "menzioni_soglia": 0,  # 0 = spento; altrimenti da 5 a 500 menzioni
    "menzioni_secondi": 30,
    "menzioni_minuti": 30,  # il blocco si toglie da solo dopo questi minuti
    "panico": False,
    "panico_utenti": 5,  # persone diverse che violano una regola in un minuto
}
LIMITI = {"menzioni_soglia": (0, 500), "menzioni_secondi": (5, 300), "menzioni_minuti": (1, 1440), "panico_utenti": (3, 50)}
MAX_MENZIONI_PER_MESSAGGIO = 50  # @everyone vale 999: si conta al massimo così, un solo messaggio non basta da solo
FINESTRA_PANICO_SECONDI = 60
DURATA_PANICO_SECONDI = 600  # circa 10 minuti
TIMEOUT_PANICO = timedelta(minutes=10)
PAUSA_TRA_BLOCCHI_SECONDI = 600  # dopo un blocco automatico non se ne riparte un altro per 10 minuti
GIORNI_ACCOUNT_SOSPETTO = 7


def config_pulita(valore) -> dict:
    """La scelta del server, con ogni numero riportato nei limiti (valori strani: quelli di base)."""
    risultato = dict(BASE)
    if not isinstance(valore, dict):
        return risultato
    for chiave, (minimo, massimo) in LIMITI.items():
        v = valore.get(chiave)
        if isinstance(v, int) and not isinstance(v, bool) and minimo <= v <= massimo:
            risultato[chiave] = v
    if risultato["menzioni_soglia"] and risultato["menzioni_soglia"] < 5:
        risultato["menzioni_soglia"] = 0
    risultato["panico"] = valore.get("panico") is True
    return risultato


async def leggi_config(guild_id: int) -> dict:
    """Se l'impostazione non si legge, l'emergenza resta spenta: il resto dell'automod deve continuare a lavorare."""
    try:
        valore = await db.get_guild_setting(guild_id, SETTING_EMERGENZA)
    except Exception:  # noqa: BLE001
        logger.warning("Impostazioni di emergenza non lette (server %s).", guild_id, exc_info=True)
        valore = None
    return config_pulita(valore)


def account_sospetto(member, adesso: datetime | None = None) -> bool:
    """Account giovane (meno di 7 giorni) o senza avatar, come per la verifica solo-sospetti."""
    adesso = adesso or datetime.now(timezone.utc)
    giovane = member.created_at is not None and (adesso - member.created_at) < timedelta(days=GIORNI_ACCOUNT_SOSPETTO)
    return giovane or getattr(member, "avatar", None) is None


class Emergenza:
    def __init__(self) -> None:
        self._menzioni: BoundedCache[int, deque] = BoundedCache(max_size=5000)
        self._violazioni: BoundedCache[int, deque] = BoundedCache(max_size=5000)
        self._panico_fino: BoundedCache[int, float] = BoundedCache(max_size=5000)
        self._ultimo_blocco: BoundedCache[int, float] = BoundedCache(max_size=5000)

    def conta_menzioni(self, guild_id: int, quante: int, secondi: int, adesso: float | None = None) -> int:
        """Menzioni nel server negli ultimi `secondi`, compresa questa volta."""
        adesso = time.monotonic() if adesso is None else adesso
        coda = self._menzioni.get(guild_id) or deque()
        coda.append((adesso, min(max(quante, 0), MAX_MENZIONI_PER_MESSAGGIO)))
        while coda and adesso - coda[0][0] > secondi:
            coda.popleft()
        self._menzioni.set(guild_id, coda)
        return sum(n for _, n in coda)

    def blocco_permesso(self, guild_id: int, adesso: float | None = None) -> bool:
        """True (e si segna) se dall'ultimo blocco automatico sono passati almeno 10 minuti."""
        adesso = time.monotonic() if adesso is None else adesso
        ultimo = self._ultimo_blocco.get(guild_id)
        if ultimo is not None and adesso - ultimo < PAUSA_TRA_BLOCCHI_SECONDI:
            return False
        self._ultimo_blocco.set(guild_id, adesso)
        return True

    def registra_violazione(self, guild_id: int, user_id: int, adesso: float | None = None) -> int:
        """Persone diverse che hanno violato una regola nell'ultimo minuto, compresa questa."""
        adesso = time.monotonic() if adesso is None else adesso
        coda = self._violazioni.get(guild_id) or deque()
        coda.append((adesso, user_id))
        while coda and adesso - coda[0][0] > FINESTRA_PANICO_SECONDI:
            coda.popleft()
        self._violazioni.set(guild_id, coda)
        return len({u for _, u in coda})

    def accendi_panico(self, guild_id: int, adesso: float | None = None) -> None:
        adesso = time.monotonic() if adesso is None else adesso
        self._panico_fino.set(guild_id, adesso + DURATA_PANICO_SECONDI)

    def panico_attivo(self, guild_id: int, adesso: float | None = None) -> bool:
        adesso = time.monotonic() if adesso is None else adesso
        fino = self._panico_fino.get(guild_id)
        return fino is not None and adesso < fino


emergenza = Emergenza()


async def dopo_messaggio(message: discord.Message, config: dict) -> bool:
    """
    AMD-057: conta le menzioni del server; alla soglia blocca i canali per i minuti scelti. Messaggi dei bot e di chi
    è protetto (proprietario, amministratori) non contano. True se il blocco è partito.
    """
    if not config["menzioni_soglia"] or message.author.bot or message.guild is None:
        return False
    if isinstance(message.author, discord.Member) and e_protetto(message.author):
        return False
    quante = len(message.mentions) + len(message.role_mentions) + (MAX_MENZIONI_PER_MESSAGGIO if message.mention_everyone else 0)
    if not quante:
        return False
    totale = emergenza.conta_menzioni(message.guild.id, quante, config["menzioni_secondi"])
    if totale < config["menzioni_soglia"] or not emergenza.blocco_permesso(message.guild.id):
        return False
    from core import lockdown_service as servizio
    from core.lockdown_logic import TIPO_BLOCCO

    esito = await servizio.attiva(
        message.guild, tipo=TIPO_BLOCCO, avviato_da=message.guild.me.id,
        motivo=f"Troppe menzioni: {totale} in {config['menzioni_secondi']} secondi", durata_minuti=config["menzioni_minuti"],
    )
    return bool(esito.ok)


async def dopo_violazione(message: discord.Message, config: dict, esente: bool) -> bool:
    """
    AMD-071: conta chi viola una regola; a `panico_utenti` persone in un minuto la modalità panico dura 10 minuti.
    In panico un account sospetto che viola ancora una regola va subito in timeout (10 minuti). Mai chi è protetto
    o esente, mai chi sta sopra il bot. True se il timeout è partito.
    """
    if not config["panico"] or message.guild is None or not isinstance(message.author, discord.Member):
        return False
    guild_id, membro = message.guild.id, message.author
    if membro.bot or esente or e_protetto(membro):
        return False
    distinti = emergenza.registra_violazione(guild_id, membro.id)
    if distinti >= config["panico_utenti"] and not emergenza.panico_attivo(guild_id):
        emergenza.accendi_panico(guild_id)
        logger.warning("Modalità panico dell'AutoMod accesa nel server %s (%s persone).", guild_id, distinti)
    if not emergenza.panico_attivo(guild_id) or not account_sospetto(membro) or fuori_portata(membro):
        return False
    try:
        await bot_roles.isola(membro, TIMEOUT_PANICO, reason="AutoMod, modalità panico: account sospetto che viola una regola"[:512])
    except discord.HTTPException:
        return False
    try:
        from core.repositories.moderation_repo import moderation_repo

        await moderation_repo.create_case(
            guild_id, membro.id, message.guild.me.id, "timeout", "AutoMod, modalità panico: account sospetto",
            duration_seconds=int(TIMEOUT_PANICO.total_seconds()), origine="automod",
        )
    except Exception:  # il caso è un'aggiunta: il timeout è già dato
        logger.warning("Caso del timeout di panico non scritto (server %s).", guild_id, exc_info=True)
    return True

"""
core/counter_logic.py
=====================
Calcola il testo di ogni contatore (NF-16, SPEC §23.2): il numero da mostrare
per ogni tipo e il nome del canale. Funzioni pure.
Funzioni coperte: SPEC §23 (NF-16); STA-033..052 (tipi, segnaposto, traguardi, orologio, conto alla rovescia)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_CONTATORI = 20  # per server (D87: erano 5; una categoria di contatori ne usa fino a 8)
MAX_ETICHETTA = 80
MAX_NOME_CANALE = 100  # limite di Discord
INTERVALLO_SECONDI = 600  # LIM-3: 2 rinomine ogni 10 minuti per canale
FUSO_DI_BASE = "Europe/Rome"
MAX_TRAGUARDI = 10
MAX_OBIETTIVO = 10_000_000

TIPI = (
    "members", "users", "bots", "online", "offline", "boosts", "boost_tier", "goal", "tickets",
    "roles", "channels", "emojis", "role_with", "role_without", "last_member", "static", "clock",
    "countdown", "youtube", "twitch", "game", "multi",
)
ETICHETTE_DI_BASE = {
    "members": "👥 Membri: {n}",
    "users": "🙂 Utenti: {n}",
    "bots": "🤖 Bot: {n}",
    "online": "🟢 Online: {n}",
    "offline": "⚫ Offline: {n}",
    "boosts": "🚀 Boost: {n}",
    "boost_tier": "💎 Livello boost: {n}",
    "goal": "🎯 Obiettivo: {n}/{target}",
    "tickets": "🎫 Ticket aperti: {n}",
    "roles": "🏷️ Ruoli: {n}",
    "channels": "💬 Canali: {n}",
    "emojis": "😀 Emoji: {n}",
    "role_with": "🎖️ Con il ruolo: {n}",
    "role_without": "🚫 Senza il ruolo: {n}",
    "last_member": "👋 Ultimo arrivato: {ultimo}",
    "static": "📊 Statistiche",
    "clock": "🕒 Ore {ora}",
    "countdown": "⏳ Mancano {giorni} giorni",
    "youtube": "▶️ Iscritti: {breve}",
    "twitch": "📺 Spettatori live: {n}",
    "game": "🎮 Giocatori: {n}",
    "multi": "👥 {membri} · 🟢 {online}",
}
NOMI_TIPI = {
    "members": "membri",
    "users": "utenti (senza i bot)",
    "bots": "bot",
    "online": "membri online",
    "offline": "membri offline",
    "boosts": "boost",
    "boost_tier": "livello di boost",
    "goal": "obiettivo di membri",
    "tickets": "ticket aperti",
    "roles": "ruoli",
    "channels": "canali",
    "emojis": "emoji",
    "role_with": "membri con un ruolo",
    "role_without": "membri senza un ruolo",
    "last_member": "ultimo membro entrato",
    "static": "testo fisso",
    "clock": "orologio",
    "countdown": "conto alla rovescia",
    "youtube": "iscritti di un canale YouTube",
    "twitch": "spettatori live su Twitch",
    "game": "giocatori di un server Minecraft",
    "multi": "più numeri insieme",
}
# Tipi senza un numero solo: il nome si costruisce da altro (STA-043, 044, 052, 048).
TIPI_DI_TESTO = frozenset({"static", "clock", "countdown", "last_member", "multi"})
# Tipi che hanno bisogno di un parametro: un ruolo, un fuso, una data, un canale, un indirizzo.
TIPI_CON_PARAMETRO = frozenset({"role_with", "role_without", "clock", "countdown", "youtube", "twitch", "game"})
TIPI_SOCIAL = frozenset({"youtube", "twitch", "game"})

# Segnaposto con nome: valgono in ogni etichetta (STA-048: più numeri in un solo canale).
SEGNAPOSTO_NOMINATI = (
    "membri", "utenti", "bot", "online", "offline", "boost", "livello", "ruoli", "canali", "emoji", "ticket", "ultimo",
)

_RE_YOUTUBE = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
_RE_TWITCH = re.compile(r"^[A-Za-z0-9_]{3,25}$")
_RE_HOST_GIOCO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{1,98}(:[0-9]{2,5})?$")


@dataclass(frozen=True)
class Istantanea:
    member_count: int
    online_count: int | None  # None = non si sa (serve una richiesta a parte)
    boost_count: int
    ticket_aperti: int | None = None  # None = non letto (nessun contatore dei ticket nel server)
    ruoli: int = 0
    canali: int = 0
    emoji: int = 0
    bot: int = 0
    livello_boost: int = 0
    ultimo_membro: str | None = None
    per_ruolo: dict = field(default_factory=dict)  # id del ruolo -> quanti membri
    social: dict = field(default_factory=dict)  # "youtube:UC..." -> numero (None = non letto)

    @property
    def utenti(self) -> int:
        return max(0, self.member_count - self.bot)


def valore_del_contatore(kind: str, snap: Istantanea, param: str | None = None) -> int | None:
    """Il numero da mostrare; None se non è noto (il contatore resta com'è)."""
    if kind in ("members", "goal"):
        return snap.member_count
    if kind == "users":
        return snap.utenti
    if kind == "bots":
        return snap.bot
    if kind == "online":
        return snap.online_count
    if kind == "offline":
        return None if snap.online_count is None else max(0, snap.member_count - snap.online_count)
    if kind == "boosts":
        return snap.boost_count
    if kind == "boost_tier":
        return snap.livello_boost
    if kind == "tickets":
        return snap.ticket_aperti
    if kind == "roles":
        return snap.ruoli
    if kind == "channels":
        return snap.canali
    if kind == "emojis":
        return snap.emoji
    if kind in ("role_with", "role_without"):
        try:
            con = snap.per_ruolo.get(int(param))
        except (TypeError, ValueError):
            return None
        if con is None:
            return None
        return con if kind == "role_with" else max(0, snap.member_count - con)
    if kind in TIPI_SOCIAL:
        return snap.social.get(f"{kind}:{param}")
    return None


def leggi_traguardi(testo: str | None) -> list[int] | None:
    """STA-040: «1000, 2000, 5000» -> [1000, 2000, 5000]. None se il testo non è valido (vuoto = lista vuota)."""
    if testo is None or not testo.strip():
        return []
    try:
        numeri = sorted({int(p) for p in testo.replace(";", ",").split(",") if p.strip()})
    except ValueError:
        return None
    if not numeri or len(numeri) > MAX_TRAGUARDI or numeri[0] < 1 or numeri[-1] > MAX_OBIETTIVO:
        return None
    return numeri


def traguardo_corrente(valore: int, target: int | None, traguardi: str | None) -> int | None:
    """STA-040: il primo traguardo ancora da raggiungere (l'ultimo, se sono stati superati tutti)."""
    elenco = leggi_traguardi(traguardi) or []
    if not elenco:
        return target
    for t in elenco:
        if t > valore:
            return t
    return elenco[-1]


def abbrevia(numero: int) -> str:
    """STA-042: 1211 -> "1,21K", 2345678 -> "2,34M" (si tronca, non si arrotonda)."""
    for soglia, lettera in ((1_000_000, "M"), (1_000, "K")):
        if numero >= soglia:
            centesimi = numero * 100 // soglia
            intero, decimali = divmod(centesimi, 100)
            return f"{intero},{decimali:02d}".rstrip("0").rstrip(",") + lettera
    return str(numero)


def _fuso(nome: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(nome or FUSO_DI_BASE)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo(FUSO_DI_BASE)


def ora_a_scatti(adesso: datetime, fuso: str | None) -> str:
    """STA-044: «14:30», sempre a scatti di 10 minuti (il nome non si può cambiare più spesso)."""
    locale = adesso.astimezone(_fuso(fuso))
    return f"{locale.hour:02d}:{locale.minute // 10 * 10:02d}"


def mancano(scadenza_iso: str | None, adesso: datetime) -> tuple[int, int] | None:
    """STA-044: (giorni, ore) che mancano alla data; (0, 0) se è passata. None se la data non si legge."""
    scadenza = _leggi_data(scadenza_iso)
    if scadenza is None:
        return None
    resto = max(timedelta(0), scadenza - adesso)
    return resto.days, resto.seconds // 3600


def _leggi_data(testo: str | None) -> datetime | None:
    """«2026-12-25» o «2026-12-25 18:30» (ora d'Italia) -> istante in UTC."""
    if not testo:
        return None
    try:
        data = datetime.fromisoformat(testo.strip().replace("T", " "))
    except ValueError:
        return None
    if data.tzinfo is None:
        data = data.replace(tzinfo=_fuso(FUSO_DI_BASE))
    return data.astimezone(timezone.utc)


def _riempi_nominati(testo: str, snap: Istantanea) -> str:
    def v(x) -> str:
        return "?" if x is None else str(x)

    valori = {
        "membri": snap.member_count, "utenti": snap.utenti, "bot": snap.bot, "online": v(snap.online_count),
        "offline": v(None if snap.online_count is None else max(0, snap.member_count - snap.online_count)),
        "boost": snap.boost_count, "livello": snap.livello_boost, "ruoli": snap.ruoli, "canali": snap.canali,
        "emoji": snap.emoji, "ticket": v(snap.ticket_aperti), "ultimo": snap.ultimo_membro or "?",
    }
    for nome, valore in valori.items():
        testo = testo.replace("{" + nome + "}", str(valore))
    return testo


def nome_canale(etichetta: str, valore: int, target: int | None) -> str:
    """Il nome del canale (al massimo 100 caratteri, come vuole Discord)."""
    testo = etichetta.replace("{n}", str(valore)).replace("{breve}", abbrevia(valore))
    if target is not None:
        testo = testo.replace("{target}", str(target)).replace("{obiettivo}", str(target))
    return testo[:MAX_NOME_CANALE]


def nome_del_contatore(contatore, snap: Istantanea, adesso: datetime) -> str | None:
    """Il nome intero del canale per un contatore, o None se il numero non è noto (il canale resta com'è)."""
    kind = contatore.kind
    param = getattr(contatore, "param", None)
    etichetta = contatore.label
    if kind in TIPI_DI_TESTO:
        testo = etichetta
        if kind == "clock":
            testo = testo.replace("{ora}", ora_a_scatti(adesso, param))
        elif kind == "countdown":
            resto = mancano(param, adesso)
            if resto is None:
                return None
            testo = testo.replace("{giorni}", str(resto[0])).replace("{ore}", str(resto[1]))
        elif kind == "last_member":
            if not snap.ultimo_membro:
                return None
        return _riempi_nominati(testo, snap)[:MAX_NOME_CANALE]
    valore = valore_del_contatore(kind, snap, param)
    if valore is None:
        return None
    target = contatore.target
    if kind == "goal":
        target = traguardo_corrente(valore, target, getattr(contatore, "targets", None))
    return _riempi_nominati(nome_canale(etichetta, valore, target), snap)[:MAX_NOME_CANALE]


def valida_etichetta(etichetta: str, kind: str) -> str | None:
    """None se l'etichetta va bene, altrimenti il motivo."""
    if not etichetta:
        return "L'etichetta non può essere vuota."
    if len(etichetta) > MAX_ETICHETTA:
        return f"L'etichetta supera {MAX_ETICHETTA} caratteri."
    if kind == "static":
        return None
    if kind == "clock":
        return None if "{ora}" in etichetta else "Per l'orologio l'etichetta deve contenere {ora}."
    if kind == "countdown":
        if "{giorni}" in etichetta or "{ore}" in etichetta:
            return None
        return "Per il conto alla rovescia l'etichetta deve contenere {giorni} (o {ore})."
    if kind == "last_member":
        return None if "{ultimo}" in etichetta else "Per l'ultimo arrivato l'etichetta deve contenere {ultimo}."
    if kind == "multi":
        if any("{" + n + "}" in etichetta for n in SEGNAPOSTO_NOMINATI):
            return None
        return "Per più numeri l'etichetta deve contenere almeno un segnaposto: " + ", ".join("{" + n + "}" for n in SEGNAPOSTO_NOMINATI) + "."
    if "{n}" not in etichetta and "{breve}" not in etichetta:
        return "L'etichetta deve contenere {n} (o {breve}), il posto del numero."
    if kind == "goal" and "{target}" not in etichetta and "{obiettivo}" not in etichetta:
        return "Per l'obiettivo l'etichetta deve contenere anche {target} (o {obiettivo})."
    return None


def valida_parametro(kind: str, parametro: str | None) -> tuple[str | None, str | None]:
    """(parametro pulito, chiave del testo d'errore). Errore None = va bene. Il parametro è dell'utente: si controlla."""
    if kind not in TIPI_CON_PARAMETRO:
        return None, None
    testo = (parametro or "").strip()
    if kind in ("role_with", "role_without"):
        return (testo, None) if testo.isdigit() and len(testo) <= 20 else (None, "counters_param_ruolo")
    if kind == "clock":
        if not testo:
            return FUSO_DI_BASE, None
        try:
            ZoneInfo(testo)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            return None, "counters_param_fuso"
        return testo, None
    if kind == "countdown":
        data = _leggi_data(testo)
        if data is None:
            return None, "counters_param_data"
        return testo, None
    if kind == "youtube":
        return (testo, None) if _RE_YOUTUBE.fullmatch(testo) else (None, "counters_param_youtube")
    if kind == "twitch":
        return (testo.lower(), None) if _RE_TWITCH.fullmatch(testo) else (None, "counters_param_twitch")
    return (testo.lower(), None) if _RE_HOST_GIOCO.fullmatch(testo) else (None, "counters_param_gioco")

"""
core/clear_filter_logic.py
==========================
Filtri di /mod-canali clear, scritti come funzione semplice sui dati di un
messaggio: si provano senza Discord.
Funzioni coperte: SPEC §5.7 (MOD-069-072, 073-079, 081-087, 089)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.message_log_logic import corrisponde_regex

_LINK = re.compile(r"https?://\S+", re.IGNORECASE)
_INVITO = re.compile(
    r"(?:discord\.gg|discord(?:app)?\.com/invite)/[\w-]+", re.IGNORECASE
)
# Emoji: intervalli Unicode più usati, selettori di variante, giunzione ZWJ, bandiere
# e le emoji personalizzate del server (<:nome:id> e <a:nome:id>).
_EMOJI_PERSONALIZZATA = re.compile(r"<a?:\w+:\d+>")
_EMOJI_UNICODE = re.compile(
    "[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u2460-\u27BF\u2900-\u297F"
    "\u2B00-\u2BFF\u3030\u303D\u3297\u3299\u00A9\u00AE\u200D\u20E3\uFE0E\uFE0F]"
)

MAX_CLEAR_AMOUNT = 1000  # messaggi letti per comando (D66)
MAX_VECCHI = 100  # al massimo 100 messaggi oltre i 14 giorni per comando (uno per uno)
ETA_BULK = timedelta(days=14)
_RIF_LINK = re.compile(r"^https?://(?:\w+\.)?discord(?:app)?\.com/channels/(\d+|@me)/(\d+)/(\d+)$")

TIPI_CLEAR = ("webhook", "iyokai", "emoji", "solo-testo", "sospetti")
MODI_TESTO = ("contiene", "inizia", "finisce", "uguale", "regex")
ETA_SOSPETTO = timedelta(days=7)


@dataclass(frozen=True)
class FiltriClear:
    autore_id: int | None = None
    solo_bot: bool = False
    solo_persone: bool = False
    solo_allegati: bool = False
    contiene: str | None = None
    non_contiene: str | None = None
    solo_link: bool = False
    solo_inviti: bool = False
    solo_embed: bool = False
    solo_menzioni: bool = False
    ruolo_id: int | None = None
    salta_fissati: bool = False
    tipo: str | None = None
    modo: str = "contiene"
    bot_id: int | None = None  # serve al tipo «iyokai»
    piu_vecchi_di_s: int | None = None
    piu_nuovi_di_s: int | None = None


def _solo_emoji(testo: str) -> bool:
    """True se il testo ha solo emoji (e spazi): niente altre lettere."""
    resto = _EMOJI_PERSONALIZZATA.sub("", testo)
    resto = _EMOJI_UNICODE.sub("", resto)
    return bool(testo.strip()) and not resto.strip()


def _autore_sospetto(autore) -> bool:
    """Senza avatar, oppure solo il ruolo @everyone, oppure account sotto i 7 giorni."""
    if getattr(autore, "avatar", True) is None:
        return True
    ruoli = getattr(autore, "roles", None)
    if ruoli is not None and len(ruoli) <= 1:
        return True
    creato = getattr(autore, "created_at", None)
    if isinstance(creato, datetime):
        return datetime.now(timezone.utc) - creato < ETA_SOSPETTO
    return False


def _tipo_passa(msg, tipo: str, bot_id: int | None) -> bool:
    if tipo == "webhook":
        return getattr(msg, "webhook_id", None) is not None
    if tipo == "iyokai":
        return bot_id is not None and msg.author.id == bot_id
    if tipo == "emoji":
        return _solo_emoji(msg.content or "")
    if tipo == "solo-testo":
        return not (msg.attachments or msg.embeds or getattr(msg, "stickers", None))
    if tipo == "sospetti":
        return _autore_sospetto(msg.author)
    return True


def _testo_passa(testo: str, cercato: str, modo: str) -> bool:
    if modo == "regex":
        return corrisponde_regex((cercato,), testo)
    cercato = cercato.lower()
    if modo == "inizia":
        return testo.startswith(cercato)
    if modo == "finisce":
        return testo.endswith(cercato)
    if modo == "uguale":
        return testo == cercato
    return cercato in testo


def messaggio_passa(msg, filtri: FiltriClear) -> bool:
    """True se il messaggio va cancellato: deve rispettare tutti i filtri attivi."""
    testo = (msg.content or "").lower()
    if filtri.salta_fissati and getattr(msg, "pinned", False):
        return False
    if filtri.autore_id is not None and msg.author.id != filtri.autore_id:
        return False
    # Un webhook conta come bot: non è una persona.
    e_bot = bool(msg.author.bot) or getattr(msg, "webhook_id", None) is not None
    if filtri.solo_bot and not e_bot:
        return False
    if filtri.solo_persone and e_bot:
        return False
    if filtri.solo_allegati and not msg.attachments:
        return False
    if filtri.piu_vecchi_di_s or filtri.piu_nuovi_di_s:
        eta = datetime.now(timezone.utc) - msg.created_at
        if filtri.piu_vecchi_di_s and eta < timedelta(seconds=filtri.piu_vecchi_di_s):
            return False
        if filtri.piu_nuovi_di_s and eta > timedelta(seconds=filtri.piu_nuovi_di_s):
            return False
    # Il testo cercato resta com'è per la regex: le maiuscole le gestisce il motore.
    if filtri.contiene and not _testo_passa(
        msg.content or "" if filtri.modo == "regex" else testo, filtri.contiene, filtri.modo
    ):
        return False
    if filtri.tipo and not _tipo_passa(msg, filtri.tipo, filtri.bot_id):
        return False
    if filtri.non_contiene and filtri.non_contiene.lower() in testo:
        return False
    if filtri.solo_link and not _LINK.search(msg.content or ""):
        return False
    if filtri.solo_inviti and not _INVITO.search(msg.content or ""):
        return False
    if filtri.solo_embed and not msg.embeds:
        return False
    if filtri.solo_menzioni and not (msg.mentions or getattr(msg, "role_mentions", None)):
        return False
    if filtri.ruolo_id is not None:
        ruoli = getattr(msg.author, "roles", [])
        if not any(r.id == filtri.ruolo_id for r in ruoli):
            return False
    return True


def descrivi_filtri(filtri: FiltriClear) -> str:
    """Riassunto breve dei filtri attivi, per il log."""
    parti = []
    if filtri.autore_id:
        parti.append(f"autore {filtri.autore_id}")
    for nome, attivo in (
        ("solo bot", filtri.solo_bot),
        ("solo persone", filtri.solo_persone),
        ("solo allegati", filtri.solo_allegati),
        ("solo link", filtri.solo_link),
        ("solo inviti", filtri.solo_inviti),
        ("solo embed", filtri.solo_embed),
        ("solo menzioni", filtri.solo_menzioni),
        ("salta fissati", filtri.salta_fissati),
    ):
        if attivo:
            parti.append(nome)
    if filtri.contiene:
        verbo = {
            "inizia": "inizia con", "finisce": "finisce con", "uguale": "è uguale a", "regex": "regex",
        }.get(filtri.modo, "contiene")
        parti.append(f"{verbo} «{filtri.contiene}»")
    if filtri.tipo:
        parti.append(f"tipo {filtri.tipo}")
    if filtri.piu_vecchi_di_s:
        parti.append(f"più vecchi di {filtri.piu_vecchi_di_s} s")
    if filtri.piu_nuovi_di_s:
        parti.append(f"più nuovi di {filtri.piu_nuovi_di_s} s")
    if filtri.non_contiene:
        parti.append(f"non contiene «{filtri.non_contiene}»")
    if filtri.ruolo_id:
        parti.append(f"ruolo {filtri.ruolo_id}")
    return ", ".join(parti) or "nessun filtro"


@dataclass
class StatoClear:
    """Conta i messaggi vecchi cancellati e quelli saltati per il tetto."""

    vecchi_presi: int = 0
    vecchi_saltati: int = 0


def crea_controllo(filtri: FiltriClear, *, ora: datetime | None = None, tetto_vecchi: int = MAX_VECCHI):
    """
    Funzione per `purge(check=)`: applica i filtri e il tetto dei messaggi più vecchi di
    14 giorni (si cancellano uno per uno, quindi piano). Ritorna (controllo, stato).
    """
    stato = StatoClear()
    riferimento = ora or datetime.now(timezone.utc)

    def controllo(msg) -> bool:
        if not messaggio_passa(msg, filtri):
            return False
        creato = getattr(msg, "created_at", None)
        if isinstance(creato, datetime) and riferimento - creato >= ETA_BULK:
            if stato.vecchi_presi >= tetto_vecchi:
                stato.vecchi_saltati += 1
                return False
            stato.vecchi_presi += 1
        return True

    return controllo, stato


def leggi_riferimento_messaggio(testo: str, canale_id: int) -> int:
    """ID o link di un messaggio del canale `canale_id`. ValueError con il motivo, in italiano."""
    testo = testo.strip()
    if testo.isdigit() and len(testo) <= 21:
        return int(testo)
    trovato = _RIF_LINK.match(testo)
    if not trovato:
        raise ValueError("Scrivi l'ID del messaggio o il suo link.")
    if int(trovato.group(2)) != canale_id:
        raise ValueError("Il messaggio è di un altro canale: usa un messaggio del canale da pulire.")
    return int(trovato.group(3))

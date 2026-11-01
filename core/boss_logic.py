"""
core/boss_logic.py
==================
Regole del World Boss, senza Discord e senza database: vita secondo i membri
attivi, danno secondo il livello, magia a monete, difesa e cura, contrattacco,
premi con tetti, orario di comparsa, mostri pronti per ogni tema, lettura del
mostro scritto dall'AI.
Funzioni coperte: SPEC §25.49–§25.52, §25.59, §25.70 (AI-R-054..057, AI-R-064, AI-R-077)
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.ai_testi_logic import estrai_json

DURATA_MINUTI = 60
ATTESA_AZIONE_SECONDI = 8
COSTO_MAGIA = 20
FATTORE_MAGIA = 3
RITMO_CONTRATTACCO = 10  # ogni 10 azioni il boss colpisce
FERITA_SECONDI = 45
VITA_PER_MEMBRO = 150
VITA_MINIMA, VITA_MASSIMA = 600, 60_000
DANNO_BASE, DANNO_PER_LIVELLO, DANNO_MASSIMO = 10, 2, 120
PREMIO_MONETE_MAX, PREMIO_XP_MAX = 300, 200
MAX_FRASI = 5
FUSO_PREDEFINITO = "Europe/Rome"
GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
AZIONI = ("attacco", "magia", "difesa", "cura")


def vita_boss(membri_attivi_7_giorni: int, vita_extra: int = 0) -> int:
    """La vita cresce con i membri attivi negli ultimi 7 giorni (AI-R-057), entro un minimo e un massimo."""
    base = max(VITA_MINIMA, min(VITA_MASSIMA, max(0, membri_attivi_7_giorni) * VITA_PER_MEMBRO))
    return base + max(0, vita_extra)


def danno_attacco(livello: int, rng: random.Random | None = None) -> int:
    """Chi ha un livello più alto fa più danno; ±20 % di variazione, tetto 120."""
    rng = rng or random
    medio = min(DANNO_MASSIMO, DANNO_BASE + DANNO_PER_LIVELLO * max(0, livello))
    return max(1, round(medio * rng.uniform(0.8, 1.2)))


def danno_magia(livello: int, rng: random.Random | None = None) -> int:
    return danno_attacco(livello, rng) * FATTORE_MAGIA


def contrattacco_dovuto(azioni_totali: int) -> bool:
    return azioni_totali > 0 and azioni_totali % RITMO_CONTRATTACCO == 0


def barra_vita(vita: int, vita_max: int, larghezza: int = 20) -> str:
    pieni = 0 if vita_max <= 0 else round(larghezza * max(0, vita) / vita_max)
    pieni = min(larghezza, max(1 if vita > 0 else 0, pieni))
    return "█" * pieni + "░" * (larghezza - pieni)


@dataclass(frozen=True)
class Premio:
    monete: int
    xp: int


def premio(danno_persona: int, danno_totale: int, partecipanti: int) -> Premio:
    """
    Premio di chi ha colpito il boss sconfitto: una quota fissa più una parte secondo il danno
    dato. Tetti 300 monete e 200 XP a persona, così nessun evento sposta l'economia.
    """
    if danno_persona <= 0 or danno_totale <= 0 or partecipanti <= 0:
        return Premio(0, 0)
    quota = min(1.0, danno_persona / max(1, danno_totale / partecipanti) / 3)
    return Premio(min(PREMIO_MONETE_MAX, 40 + round(260 * quota)), min(PREMIO_XP_MAX, 20 + round(180 * quota)))


# ---------------------------------------------------------------- orario
def fuso_valido(nome: str) -> str | None:
    try:
        ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None
    return nome


def giorno_di_comparsa(
    giorni: tuple[int, ...] | list[int], ora: int, fuso: str, adesso: datetime | None = None,
    ultimo_giorno: date | None = None, ritardo_massimo_ore: int = 3,
) -> date | None:
    """
    La data locale del boss da far comparire adesso, o None. Compare nel giorno scelto dall'ora
    indicata (e fino a 3 ore dopo, se il bot era fermo), una volta sola per giorno (AI-R-055).
    """
    adesso = adesso or datetime.now(timezone.utc)
    try:
        locale = adesso.astimezone(ZoneInfo(fuso))
    except (ZoneInfoNotFoundError, ValueError, OSError):
        locale = adesso.astimezone(ZoneInfo(FUSO_PREDEFINITO))
    if locale.weekday() not in giorni or ultimo_giorno == locale.date():
        return None
    if not 0 <= locale.hour - ora <= ritardo_massimo_ore:
        return None
    return locale.date()


def descrivi_orario(giorni, ora: int, fuso: str) -> str:
    nomi = ", ".join(GIORNI[g] for g in sorted(set(giorni)) if 0 <= g < 7) or "nessun giorno"
    return f"{nomi} alle {ora:02d}:00 ({fuso})"


def leggi_giorni(testo: str) -> list[int] | None:
    """«lun,ven» o «venerdì» → [0, 4]. None se una parola non si capisce; «ogni giorno» vale tutti."""
    pulito = testo.strip().lower()
    if pulito in ("ogni giorno", "tutti", "ogni"):
        return list(range(7))
    trovati: set[int] = set()
    for parola in re.split(r"[,\s;]+", pulito):
        if not parola:
            continue
        indice = next((i for i, g in enumerate(GIORNI) if g.startswith(parola[:3]) and len(parola) >= 3), None)
        if indice is None:
            return None
        trovati.add(indice)
    return sorted(trovati) or None


# ---------------------------------------------------------------- mostri
@dataclass(frozen=True)
class Mostro:
    nome: str
    aspetto: str
    frasi: tuple[str, ...]


MOSTRI_PRONTI: dict[str, tuple[Mostro, ...]] = {
    "yokai": (
        Mostro("Gashadokuro", "Uno scheletro alto come una torre, fatto di ossa di dimenticati.", ("Le ossa scricchiolano.", "Un ruggito di vento gelido.")),
        Mostro("Nurarihyon", "Un vecchio sorridente che entra nelle case come se fossero sue.", ("Servite il tè.", "Nessuno lo ha invitato, eppure è qui.")),
    ),
    "fantasy": (
        Mostro("Drago Cenere", "Un drago dalle ali bruciate che sputa brace.", ("Un soffio di fuoco.", "Le scaglie brillano rosse.")),
        Mostro("Re Goblin", "Un goblin con la corona rubata a cento re.", ("Questo oro è mio!", "I goblin ridono nell'ombra.")),
    ),
    "cyberpunk": (
        Mostro("Mecha-Oni", "Un gigante di metallo con gli occhi al neon.", ("Sistema in sovraccarico.", "Scintille sulla pioggia acida.")),
        Mostro("Virus Zero", "Un'intelligenza ostile che vive nei server della città.", ("Accesso negato.", "Copia di me stesso in corso.")),
    ),
    "horror": (
        Mostro("La Presenza", "Qualcosa che non si vede mai, solo si sente.", ("Un sussurro alle spalle.", "La luce trema.")),
        Mostro("Uomo Magro", "Troppo alto, troppo silenzioso.", ("Non guardarlo.", "Si avvicina senza muoversi.")),
    ),
    "spazio": (
        Mostro("Leviatano Stellare", "Una creatura grande come una luna, nata tra le nebulose.", ("Un'eco nel vuoto.", "Le stelle si spengono.")),
        Mostro("Sciame Alieno", "Mille ombre che si muovono come una mente sola.", ("Segnale ostile.", "Gli scudi tremano.")),
    ),
    "pirati": (
        Mostro("Kraken", "Tentacoli grandi come alberi di nave.", ("Il mare ribolle.", "La nave cigola.")),
        Mostro("Capitan Spettro", "Un capitano senza ciurma, con una nave senza fondo.", ("Chi osa sfidarmi?", "Cannoni dal nulla.")),
    ),
}


def mostro_pronto(tema: str | None, rng: random.Random | None = None) -> Mostro:
    """Un mostro del tema (senza AI); per un tema sconosciuto, quello degli yokai."""
    rng = rng or random
    return rng.choice(MOSTRI_PRONTI.get(tema or "", MOSTRI_PRONTI["yokai"]))


ISTRUZIONI_MOSTRO = (
    "Inventa un mostro per un evento di gruppo, coerente con l'ambientazione. Rispondi SOLO con JSON: "
    '{"nome": "max 40 caratteri", "aspetto": "max 200 caratteri", "frasi": ["tre frasi brevi che dice o fa"]}. '
    "Non citare persone reali né utenti."
)


def _pulisci(testo, massimo: int) -> str:
    return re.sub(r"[`<>@]|https?://\S+", "", str(testo or "")).strip()[:massimo]


def leggi_mostro(testo: str) -> Mostro | None:
    dati = estrai_json(testo)
    if not dati:
        return None
    nome = _pulisci(dati.get("nome"), 40)
    if not nome:
        return None
    frasi = dati.get("frasi")
    frasi = [f for f in (_pulisci(x, 120) for x in (frasi if isinstance(frasi, list) else []) if isinstance(x, str)) if f][:MAX_FRASI]
    return Mostro(nome, _pulisci(dati.get("aspetto"), 200), tuple(frasi))

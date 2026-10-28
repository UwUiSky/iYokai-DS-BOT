"""
core/ai_testi_logic.py
======================
Testi e dati fissi delle funzioni AI: temi pronti della lore, lingue della
traduzione e bandiere, istruzioni per ogni funzione, elenco dei comandi
per l'helpdesk, lettura della proposta di struttura del server.
Funzioni coperte: SPEC §25.7, §25.27, §25.34, §25.35, §25.46, §25.74–§25.79 (AI-R-028, AI-R-036, AI-R-037, AI-R-050, AI-R-081..086)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# ---------------------------------------------------------------- lore
TEMI: dict[str, str] = {
    "yokai": "Mondo del folklore giapponese: spiriti yokai, santuari, lanterne, nebbia e leggende antiche.",
    "fantasy": "Regno fantasy medievale: draghi, maghi, gilde di avventurieri e rovine magiche.",
    "cyberpunk": "Città futura al neon: hacker, corporazioni, impianti cibernetici e pioggia acida.",
    "horror": "Atmosfera horror: case abbandonate, presenze, sussurri e paura che cresce piano.",
    "spazio": "Fantascienza spaziale: astronavi, stazioni orbitali, pianeti sconosciuti e alieni.",
    "pirati": "Avventura piratesca: navi, isole del tesoro, mappe, tempeste e ciurme rivali.",
}
MAX_LORE = 1000


def testo_lore(tema: str | None, testo: str | None) -> str:
    """Il tema pronto più le parole dell'admin, entro MAX_LORE caratteri."""
    parti = [TEMI.get(tema or "", ""), (testo or "").strip()]
    return " ".join(p for p in parti if p)[:MAX_LORE]


# ---------------------------------------------------------------- lingue
LINGUE: dict[str, str] = {
    "it": "italiano", "en": "inglese", "es": "spagnolo", "fr": "francese", "de": "tedesco",
    "pt": "portoghese", "nl": "olandese", "pl": "polacco", "ro": "rumeno", "ru": "russo",
    "uk": "ucraino", "tr": "turco", "ar": "arabo", "hi": "hindi", "ja": "giapponese",
    "ko": "coreano", "zh": "cinese", "sv": "svedese", "el": "greco", "cs": "ceco",
    "hu": "ungherese", "fi": "finlandese", "da": "danese", "no": "norvegese", "id": "indonesiano",
}

BANDIERE: dict[str, str] = {
    "🇮🇹": "it", "🇬🇧": "en", "🇺🇸": "en", "🇪🇸": "es", "🇲🇽": "es", "🇫🇷": "fr", "🇩🇪": "de",
    "🇵🇹": "pt", "🇧🇷": "pt", "🇳🇱": "nl", "🇵🇱": "pl", "🇷🇴": "ro", "🇷🇺": "ru", "🇺🇦": "uk",
    "🇹🇷": "tr", "🇸🇦": "ar", "🇮🇳": "hi", "🇯🇵": "ja", "🇰🇷": "ko", "🇨🇳": "zh", "🇸🇪": "sv",
    "🇬🇷": "el", "🇨🇿": "cs", "🇭🇺": "hu", "🇫🇮": "fi", "🇩🇰": "da", "🇳🇴": "no", "🇮🇩": "id",
}

_PAROLE_LINGUA: dict[str, frozenset[str]] = {
    "it": frozenset("il lo la gli che non per con una sono come cosa perché questo ciao grazie".split()),
    "en": frozenset("the and you that is are with for this what how not have hello thanks".split()),
    "es": frozenset("el los las que con para una por como esto hola gracias pero muy".split()),
    "fr": frozenset("le les des que avec pour une est pas comment bonjour merci mais très".split()),
    "de": frozenset("der die das und ist nicht mit für ein eine wie hallo danke aber sehr".split()),
    "pt": frozenset("os as que com para uma não como isso olá obrigado mas muito você".split()),
}


def riconosci_lingua(testo: str, predefinita: str = "it") -> str:
    """Lingua più probabile dalle parole comuni (AI-R-086). Senza indizi: `predefinita`."""
    parole = set(re.findall(r"[a-zàèéìòùäöüßñç]+", testo.lower()))
    punteggi = {lingua: len(parole & comuni) for lingua, comuni in _PAROLE_LINGUA.items()}
    migliore = max(punteggi, key=punteggi.get)
    return migliore if punteggi[migliore] > 0 else predefinita


def nome_lingua(codice: str) -> str:
    return LINGUE.get(codice, codice)


# ---------------------------------------------------------------- istruzioni per funzione
ISTRUZIONI: dict[str, str] = {
    "chiedi": "Aiuta l'utente a usare il bot. Usa SOLO i comandi dell'elenco. Proponi al massimo 3 comandi, "
    "ognuno su una riga che comincia con il percorso esatto tra barre, es. /mod timeout. Se la richiesta "
    "è un'azione (es. 'metti in timeout Mario 10 minuti'), indica il comando e i valori da inserire.",
    "riassumi": "Riassumi la conversazione in punti brevi (al massimo 10). Non citare dati personali.",
    "traduci": "Traduci il testo nella lingua richiesta. Rispondi solo con la traduzione.",
    "spiega": "Spiega il messaggio in parole semplici, in poche righe.",
    "menzione": "Rispondi come l'assistente del server, in modo amichevole e breve.",
    "personaggio": "Interpreta il personaggio descritto qui sotto. Resta nel personaggio, risposte brevi.",
    "stile": "Scrivi un messaggio nuovo sull'argomento dato, imitando lo stile dei messaggi di esempio "
    "(lessico, lunghezza, punteggiatura, emoji). Non copiare frasi intere.",
    "moderazione": "Valuta se il messaggio viola le regole comuni di Discord (insulti, odio, minacce, spam, "
    "contenuti sessuali). Rispondi SOLO con JSON: {\"violazione\": true|false, \"motivo\": \"...\", "
    "\"gravita\": 1-5}.",
    "ticket_bozza": "Scrivi una bozza di risposta dello staff al ticket, cortese e concreta. Usa la base di "
    "conoscenza se pertinente. Lo staff la rivedrà prima di inviarla.",
    "ticket_utente": "Rispondi alla domanda dell'utente nel ticket usando solo la base di conoscenza. Se non sai, "
    "dì che lo staff risponderà a breve.",
    "ticket_smista": "Classifica il ticket. Rispondi SOLO con JSON: {\"categoria\": \"...\", \"urgenza\": 1-5, "
    "\"ruolo\": \"moderatore\"|\"amministratore\"}.",
    "costruisci": "Proponi la struttura di un server Discord. Rispondi SOLO con JSON: {\"ruoli\": [\"nome\"], "
    "\"categorie\": [{\"nome\": \"...\", \"canali\": [{\"nome\": \"...\", \"tipo\": \"testo\"|\"voce\"}]}]}. "
    "Al massimo 10 ruoli, 6 categorie, 25 canali in tutto.",
    "immagina": "",
}


# ---------------------------------------------------------------- helpdesk
@dataclass(frozen=True)
class ComandoNoto:
    percorso: str  # es. "mod timeout"
    descrizione: str


def elenco_comandi_per_ai(comandi: list[ComandoNoto], massimo: int = 200) -> str:
    """Registro dei comandi letto dall'AI (AI-R-027): una riga per comando, senza ID."""
    return "\n".join(f"/{c.percorso} — {c.descrizione}" for c in comandi[:massimo])


_PERCORSO = re.compile(r"/([a-z0-9\-_]+(?: [a-z0-9\-_]+){0,2})")


def comandi_citati(risposta: str, comandi: list[ComandoNoto], massimo: int = 3) -> list[ComandoNoto]:
    """I comandi veri citati nella risposta, al massimo 3, nell'ordine in cui compaiono (AI-R-028)."""
    per_percorso = {c.percorso: c for c in comandi}
    trovati: list[ComandoNoto] = []
    for m in _PERCORSO.finditer(risposta.lower()):
        parole = m.group(1).split()
        for n in range(len(parole), 0, -1):
            c = per_percorso.get(" ".join(parole[:n]))
            if c is not None:
                if c not in trovati:
                    trovati.append(c)
                break
        if len(trovati) >= massimo:
            break
    return trovati


# Comandi di configurazione: il pannello web ha la pagina giusta (AI-R-028, §25.27).
GRUPPI_CONFIGURAZIONE = frozenset({"admin", "ai", "moduli", "ruoli"})
PAGINE_PANNELLO = (  # dal percorso più preciso al più generico
    ("ai", "ai"), ("admin premium aspetto", "aspetto"), ("admin premium marchio", "marchio"),
    ("admin premium", "premium"),
)


def link_configurazione(url_pannello: str, guild_id: int | None, citati: list[ComandoNoto]) -> str | None:
    """
    L'indirizzo della pagina del pannello dove si fa ciò che spiega il primo comando di configurazione
    citato (altrimenti la pagina del server). None senza pannello, senza server o senza comandi di
    configurazione tra quelli citati.
    """
    if not url_pannello or guild_id is None:
        return None
    for c in citati:
        if c.percorso.split(" ")[0] not in GRUPPI_CONFIGURAZIONE:
            continue
        pagina = next((p for prefisso, p in PAGINE_PANNELLO if c.percorso == prefisso or c.percorso.startswith(prefisso + " ")), "")
        return "/".join(p for p in (url_pannello.rstrip("/"), "server", str(guild_id), pagina) if p)[:512]
    return None


# ---------------------------------------------------------------- JSON dalle risposte
def estrai_json(testo: str) -> dict | None:
    """Il primo oggetto JSON nella risposta (i modelli a volte aggiungono testo o ```)."""
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio < 0 or fine <= inizio:
        return None
    try:
        dati = json.loads(testo[inizio : fine + 1])
    except ValueError:
        return None
    return dati if isinstance(dati, dict) else None


@dataclass(frozen=True)
class PropostaServer:
    ruoli: tuple[str, ...]
    categorie: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]  # (nome, ((canale, tipo), ...))

    @property
    def canali_totali(self) -> int:
        return sum(len(c) for _, c in self.categorie)


def _lista(valore) -> list:
    """Il valore come elenco: un testo solo diventa un elenco di uno, il resto (numeri, oggetti) niente."""
    if isinstance(valore, list):
        return valore
    return [valore] if isinstance(valore, str) else []


_NOME_CANALE = re.compile(r"[^a-z0-9\-_àèéìòù]+")


def leggi_proposta_server(testo: str) -> PropostaServer | None:
    """Proposta dell'AI resa sicura: tetti (10 ruoli, 6 categorie, 25 canali), nomi corti e puliti."""
    dati = estrai_json(testo)
    if not dati:
        return None
    ruoli = tuple(str(r).strip()[:100] for r in _lista(dati.get("ruoli")) if str(r).strip())[:10]
    categorie = []
    totale = 0
    for cat in _lista(dati.get("categorie"))[:6]:
        if not isinstance(cat, dict):
            continue
        nome_cat = str(cat.get("nome") or "").strip()[:100]
        canali = []
        for ch in _lista(cat.get("canali")):
            if totale >= 25 or not isinstance(ch, dict):
                break
            nome = _NOME_CANALE.sub("-", str(ch.get("nome") or "").lower()).strip("-")[:100]
            tipo = "voce" if str(ch.get("tipo")).lower() in ("voce", "voice", "vocale") else "testo"
            if nome:
                canali.append((nome, tipo))
                totale += 1
        if nome_cat:
            categorie.append((nome_cat, tuple(canali)))
    if not ruoli and not categorie:
        return None
    return PropostaServer(ruoli=ruoli, categorie=tuple(categorie))


@dataclass(frozen=True)
class Giudizio:
    violazione: bool
    motivo: str
    gravita: int


def leggi_giudizio(testo: str) -> Giudizio | None:
    dati = estrai_json(testo)
    if not dati or "violazione" not in dati:
        return None
    try:
        gravita = max(1, min(5, int(dati.get("gravita") or 1)))
    except (TypeError, ValueError):
        gravita = 1
    violazione = dati["violazione"]
    if isinstance(violazione, str):
        violazione = violazione.strip().lower() in ("true", "si", "sì", "yes", "1")
    return Giudizio(bool(violazione), str(dati.get("motivo") or "")[:300], gravita)

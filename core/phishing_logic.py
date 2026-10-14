"""
core/phishing_logic.py
======================
Riconosce i link di phishing: confronto dei domini con la lista e con alcuni
segni tipici dei siti truffa (nome di una marca con parole da regalo, nomi
scritti quasi come quelli veri). Senza Discord e senza rete.
Funzioni coperte: SPEC §23 (NF-31, SIC-042: accorciatori di link e inviti a
server per adulti, ognuno con un suo interruttore)

Un dominio ufficiale non e' mai segnalato. L'euristica puo' sbagliare: per
questo il server puo' mettere un dominio in whitelist (anti-link) e lo
sblocca anche dal controllo del phishing.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.automod_advanced_logic import extract_domains, normalize_domain

FILE_LISTA_LOCALE = Path(__file__).resolve().parent.parent / "data" / "phishing_domains.txt"
MAX_DOMINI_LISTA = 200_000  # tetto in memoria: una lista scaricata piu' grande si ignora

# Siti veri delle marche piu' imitate: mai segnalati, nemmeno dall'euristica.
DOMINI_UFFICIALI = frozenset({
    "discord.com", "discord.gg", "discord.gift", "discord.new", "discord.media", "discord.dev",
    "discordapp.com", "discordapp.net", "discordstatus.com", "discord.js.org", "discordbotlist.com",
    "top.gg", "steampowered.com", "steamcommunity.com", "steamstatic.com", "steamgames.com",
    "epicgames.com", "roblox.com", "twitch.tv", "youtube.com", "youtu.be",
})

# Marche imitate e parole che i siti truffa ci mettono accanto.
MARCHE = ("discord", "steam", "roblox", "epicgames")
PAROLE_SOSPETTE = (
    "nitro", "gift", "free", "promo", "airdrop", "giveaway", "claim", "drop", "bonus", "reward", "gratis", "regalo",
)
# Marche scritte quasi giuste: l'etichetta del dominio e' a una lettera di distanza.
MARCHE_SCRITTE_STORTE = ("discord", "steamcommunity", "steampowered")

PAROLE_VERE = frozenset({"discard"})  # parole comuni a una lettera da «discord»: non sono typosquatting

_TOKEN_DOMINIO = re.compile(r"(?<![\w@.-])((?:[a-z0-9-]{1,63}\.)+[a-z]{2,24})(?![\w-])", re.IGNORECASE)
_DUE_PARTI_SPECIALI = {"co", "com", "org", "net", "gov", "ac"}


def carica_domini(testo: str) -> frozenset[str]:
    """Da un testo con un dominio per riga (commenti con #) alla lista normalizzata."""
    domini = set()
    for riga in testo.splitlines():
        riga = riga.split("#", 1)[0].strip()
        if riga:
            dominio = normalize_domain(riga)
            if dominio and "." in dominio:
                domini.add(dominio)
        if len(domini) >= MAX_DOMINI_LISTA:
            break
    return frozenset(domini)


def carica_lista_locale(percorso: Path = FILE_LISTA_LOCALE) -> frozenset[str]:
    try:
        return carica_domini(percorso.read_text(encoding="utf-8"))
    except OSError:
        return frozenset()


def domini_nel_testo(testo: str) -> tuple[str, ...]:
    """Domini dei link con http/https, piu' i nomi scritti senza http (es. «discord-nitro.xyz/ritira»)."""
    trovati = list(extract_domains(testo))
    for corrispondenza in _TOKEN_DOMINIO.findall(testo):
        dominio = normalize_domain(corrispondenza)
        if dominio and dominio not in trovati:
            trovati.append(dominio)
    return tuple(trovati)


def _registrabile(dominio: str) -> str:
    """Il nome sotto l'estensione: «a.b.discord-nitro.xyz» -> «discord-nitro.xyz» (co.uk compreso)."""
    parti = dominio.split(".")
    if len(parti) >= 3 and parti[-2] in _DUE_PARTI_SPECIALI and len(parti[-1]) == 2:
        return ".".join(parti[-3:])
    return ".".join(parti[-2:])


def _ufficiale(dominio: str) -> bool:
    parti = dominio.split(".")
    return any(".".join(parti[i:]) in DOMINI_UFFICIALI for i in range(len(parti)))


def _distanza_al_massimo_uno(a: str, b: str) -> bool:
    """True se a e b differiscono per una lettera cambiata, tolta o aggiunta (non uguali)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    corta, lunga = sorted((a, b), key=len)
    return any(lunga[:i] + lunga[i + 1:] == corta for i in range(len(lunga)))


def sembra_phishing(dominio: str) -> bool:
    """Segni da sito truffa su un dominio non ufficiale: marca + parola da regalo, o marca scritta storta."""
    dominio = normalize_domain(dominio)
    if not dominio or _ufficiale(dominio):
        return False
    # Un dominio vero usato come prefisso di un altro («steampowered.com.evil.io»).
    parti = dominio.split(".")
    for i in range(len(parti) - 1):
        for j in range(i + 2, len(parti)):
            if ".".join(parti[i:j]) in DOMINI_UFFICIALI and j < len(parti) and i + 1 < j:
                return True
    nome = _registrabile(dominio).rsplit(".", 1)[0].replace(".", "-")
    parole = [parola for parola in PAROLE_SOSPETTE if parola in nome]
    if any(marca in nome for marca in MARCHE) and parole:
        return True
    if "nitro" in parole and len(parole) >= 2:  # «free-nitro», «nitro-gift»
        return True
    # La marca scritta storta: per ogni pezzo del nome («dlscord-app» -> «dlscord», «app»).
    for pezzo in re.split(r"[-_.]", nome):
        if pezzo not in PAROLE_VERE and any(_distanza_al_massimo_uno(pezzo, marca) for marca in MARCHE_SCRITTE_STORTE):
            return True
    return False


def e_phishing(domini, lista: frozenset[str], consentiti=()) -> bool:
    """
    True se ALMENO UN dominio e' nella lista (lui o un dominio che lo contiene)
    o sembra phishing. I domini in `consentiti` (whitelist del server) non contano.
    """
    consentiti_n = {normalize_domain(d) for d in consentiti} - {""}
    for dominio in domini:
        dominio = normalize_domain(dominio)
        if not dominio:
            continue
        parti = dominio.split(".")
        if any(".".join(parti[i:]) in consentiti_n for i in range(len(parti))):
            continue
        if any(".".join(parti[i:]) in lista for i in range(len(parti))):
            return True
        if sembra_phishing(dominio):
            return True
    return False


# SIC-042: accorciatori di link. Nascondono la meta vera del link: chi li accende li blocca tutti.
ACCORCIATORI = frozenset({
    "bit.ly", "bitly.com", "tinyurl.com", "goo.gl", "is.gd", "v.gd", "ow.ly", "buff.ly", "cutt.ly",
    "rebrand.ly", "shorturl.at", "tiny.cc", "rb.gy", "bit.do", "t.ly", "s.id", "adf.ly", "shorte.st",
    "t.co", "lnkd.in", "tiny.one", "shorturl.gg", "u.to", "clck.ru", "qr.ae", "soo.gd", "x.gd",
    "urlz.fr", "2no.co", "grabify.link", "iplogger.org", "iplogger.com", "blasze.com", "linktr.ee",
})


def e_accorciatore(domini, consentiti=()) -> bool:
    """True se almeno un dominio (o un suo dominio padre) e' un accorciatore non in whitelist."""
    consentiti_n = {normalize_domain(d) for d in consentiti} - {""}
    for dominio in domini:
        parti = normalize_domain(dominio).split(".")
        catena = {".".join(parti[i:]) for i in range(len(parti))}
        if catena & consentiti_n:
            continue
        if catena & ACCORCIATORI:
            return True
    return False


# SIC-042: inviti a server per adulti. Il codice si legge dal testo; il server lo dice Discord.
MAX_INVITI_PER_MESSAGGIO = 3  # ogni invito costa una chiamata a Discord
_INVITO = re.compile(r"(?:discord(?:app)?\.com/invite|discord\.gg)/([A-Za-z0-9-]{2,32})", re.IGNORECASE)
# Parole nel nome del server che lo dicono per adulti anche se il livello NSFW non e' impostato.
PAROLE_ADULTI = ("nsfw", "18+", "porn", "hentai", "onlyfans", "xxx", "nude", "nudes", "sexy", "e-girl", "egirl")
LIVELLI_NSFW_ADULTI = frozenset({"explicit", "age_restricted"})


def codici_invito(testo: str) -> tuple[str, ...]:
    """I codici d'invito Discord nel testo, senza doppioni, al massimo MAX_INVITI_PER_MESSAGGIO."""
    visti: list[str] = []
    for codice in _INVITO.findall(testo or ""):
        if codice not in visti:
            visti.append(codice)
        if len(visti) >= MAX_INVITI_PER_MESSAGGIO:
            break
    return tuple(visti)


def server_per_adulti(livello_nsfw: str, nome: str) -> bool:
    """True se Discord segna il server come esplicito/vietato ai minori o se il nome lo dichiara."""
    if (livello_nsfw or "").lower() in LIVELLI_NSFW_ADULTI:
        return True
    nome = (nome or "").lower()
    return any(parola in nome for parola in PAROLE_ADULTI)

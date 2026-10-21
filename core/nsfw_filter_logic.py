"""
core/nsfw_filter_logic.py
=========================
Filtri dell'istanza NSFW: lista vietata fissa nel codice, lista permessa
scelta dal server, fonti ammesse, controllo del canale vietato ai minori e
impronta (hash) di ogni immagine. Funzioni semplici, senza Discord né rete.
Funzioni coperte: SPEC §16.10 (NF-23)

Regole fisse (non si cambiano da un comando):
- contenuti che riguardano minori, violenza, assenza di consenso, animali,
  persone reali senza consenso: sempre bloccati;
- contenuti disegnati o generati: bloccati, perché nessuno può dichiarare
  età e consenso di un personaggio;
- solo fonti che dichiarano l'età e il consenso di chi compare, e solo
  elementi che la fonte segna come "verificati".
Il filtro sbaglia per eccesso: meglio un contenuto lecito scartato che uno
illecito pubblicato.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

import discord

MAX_TAG_PERMESSI = 25
LUNGHEZZA_TAG = (2, 32)
_TAG_VALIDO = re.compile(r"^[a-z0-9][a-z0-9 ]*[a-z0-9]$")


@dataclass(frozen=True)
class Fonte:
    nome: str
    dichiarazione: str
    domini: tuple[str, ...]


# Fonti ammesse: dichiarano che chi compare ha almeno 18 anni e ha dato il
# consenso (verifica dei creatori). Nessun sito "booru": non dichiarano nulla.
FONTI: dict[str, Fonte] = {
    "redgifs": Fonte(
        nome="RedGifs",
        dichiarazione="Creatori verificati: età (18+) e consenso controllati dalla piattaforma.",
        domini=("redgifs.com",),
    ),
}

# --- Lista vietata fissa -------------------------------------------------
# Parole che bloccano se una parola del testo COMINCIA così.
_PREFISSI: dict[str, tuple[str, ...]] = {
    "minori": (
        "loli", "shota", "teen", "tween", "preteen", "underag", "minor", "child", "kiddi", "infant",
        "toddler", "young", "youth", "jailbait", "pedo", "paedo", "school", "student", "pupil",
        "junior", "petite", "tiny", "little", "smol", "barely", "innocen", "virgin", "pigtail",
        "braces", "babysit", "cheerlead", "daughter", "niece", "nephew", "ageplay", "ddlg", "abdl",
        "diaper", "littlespace", "bambin", "ragazzin", "minorenn", "scolar", "liceal", "adolescen",
        "piccol", "giovan", "figlia", "nipot", "verginel", "studentess", "colegial", "jovencit",
        "menor", "kinder", "baby", "babies",
    ),
    "violenza o consenso": (
        "rape", "raping", "stupr", "noncon", "nonconsen", "forced", "forzat", "drugged", "drogat",
        "sleep", "asleep", "dormient", "unconscious", "incoscien", "passedout", "drunk", "ubriac",
        "abuse", "abus", "snuff", "gore", "blood", "sangue", "murder", "necro", "tortur", "kidnap",
        "rapim", "traffick", "incest", "stepdau", "stepsis", "stepbro", "stepson", "stepmom",
        "stepdad", "sister", "brother", "sorell", "fratell", "family", "famigli",
    ),
    "persone reali senza consenso": (
        "hidden", "spycam", "voyeur", "upskirt", "downblouse", "creep", "candid", "leak", "revenge",
        "stolen", "rubat", "celeb", "famous", "deepfake", "faceswap", "nudify", "undress", "spogli",
        "exgf", "ex-gf",
    ),
    "animali": ("bestial", "zoophil", "animal", "canine", "equine", "feral", "horse", "doggy-style-dog"),
    "disegnati o generati (età non dichiarabile)": (
        "hentai", "anime", "manga", "cartoon", "toon", "doujin", "ecchi", "futanari", "furry",
        "yiff", "cosplay", "render", "blender", "aigenerat", "generated", "generat", "stablediffus",
        "midjourney", "animated", "animazion",
    ),
}
# Parole che bloccano solo se sono la parola intera (troppo corte per un prefisso).
_ESATTE: dict[str, frozenset[str]] = {
    "minori": frozenset({"cp", "pthc", "ptsc", "kdv", "jb", "kid", "kids", "yo", "lil", "boy", "boys", "minore"}),
    "animali": frozenset({"zoo", "dog", "dogs", "cane"}),
    "disegnati o generati (età non dichiarabile)": frozenset({"ai", "3d", "cgi", "sfm", "futa", "toons"}),
    "violenza o consenso": frozenset({"mom", "dad", "mamma", "papa", "kill"}),
}
# Cercate anche a lettere unite, per chi scrive "l.o.l.i" o "s c h o o l g i r l".
_COMPATTE = (
    "loli", "shota", "preteen", "underage", "jailbait", "pedo", "pthc", "childporn", "kinderporn",
    "minorenn", "bambin", "schoolgirl", "schoolboy", "zoophil", "bestial",
)
# "16yo", "15 anni", "17 years": età sotto i 18 scritte in cifre.
_ETA_MINORE = re.compile(r"(?<!\d)(?:[1-9]|1[0-7])\s*(?:y\s*o|yrs?|years?|anni|anno|ans|age|eta)\b")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})


def _senza_accenti(testo: str) -> str:
    decomposto = unicodedata.normalize("NFKD", testo)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def normalizza(testo: str) -> str:
    """Minuscole, senza accenti, cifre "leet" in lettere, solo lettere e spazi."""
    base = _senza_accenti(testo).translate(_LEET)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", base).split())


def motivo_vietato(*testi: str) -> str | None:
    """Categoria vietata trovata nei testi (tag, titolo, autore), o None."""
    for testo in testi:
        if not testo:
            continue
        grezze = re.sub(r"[^a-z0-9]+", " ", _senza_accenti(testo)).split()
        if _ETA_MINORE.search(" ".join(grezze)):
            return "minori"
        parole = normalizza(testo).split()
        compatto = "".join(parole)
        for categoria, prefissi in _PREFISSI.items():
            if any(p.startswith(pref) for p in parole for pref in prefissi):
                return categoria
        for categoria, esatte in _ESATTE.items():
            if any(p in esatte for p in (*parole, *grezze)):
                return categoria
        if any(c in compatto for c in _COMPATTE):
            return "minori"
    return None


def valida_tag(testo: str) -> tuple[str | None, str | None]:
    """(tag pulito, None) se si può mettere nella lista permessa, altrimenti (None, errore)."""
    tag = normalizza(testo)
    minimo, massimo = LUNGHEZZA_TAG
    if not (minimo <= len(tag) <= massimo) or not _TAG_VALIDO.match(tag):
        return None, f"Il tag deve avere da {minimo} a {massimo} caratteri: lettere, cifre e spazi."
    motivo = motivo_vietato(tag)
    if motivo is not None:
        return None, f"Questo tag è nella lista vietata fissa ({motivo}) e non si può permettere."
    return tag, None


@dataclass(frozen=True)
class ElementoFonte:
    fonte: str
    id_fonte: str
    tag: tuple[str, ...]
    testo: str
    autore: str
    verificato: bool
    url_pagina: str
    url_anteprima: str


def dominio_della_fonte(url: str, fonte: Fonte) -> bool:
    parti = urlparse(url)
    host = (parti.hostname or "").lower()
    return parti.scheme == "https" and any(host == d or host.endswith("." + d) for d in fonte.domini)


def motivo_scarto(elemento: ElementoFonte, tag_permessi: frozenset[str] | set[str]) -> str | None:
    """Perché un elemento NON si può pubblicare; None se passa tutti i filtri."""
    fonte = FONTI.get(elemento.fonte)
    if fonte is None:
        return "fonte non ammessa"
    if not elemento.verificato:
        return "la fonte non dichiara età e consenso per questo contenuto"
    if not (dominio_della_fonte(elemento.url_pagina, fonte) and dominio_della_fonte(elemento.url_anteprima, fonte)):
        return "indirizzo fuori dalla fonte"
    motivo = motivo_vietato(*elemento.tag, elemento.testo, elemento.autore)
    if motivo is not None:
        return f"lista vietata: {motivo}"
    if not tag_permessi or not {normalizza(t) for t in elemento.tag} & {normalizza(t) for t in tag_permessi}:
        return "nessun tag della lista permessa del server"
    return None


def filtra(elementi: list[ElementoFonte], tag_permessi: frozenset[str] | set[str]) -> list[ElementoFonte]:
    """Solo gli elementi che passano entrambi i filtri (lista vietata e lista permessa)."""
    return [e for e in elementi if motivo_scarto(e, tag_permessi) is None]


def canale_ammesso(canale: object) -> bool:
    """Solo canali di testo o thread segnati vietati ai minori da Discord (nsfw)."""
    if not isinstance(canale, (discord.TextChannel, discord.Thread)):
        return False
    try:
        return bool(canale.is_nsfw())
    except AttributeError:
        return False


def impronta(dati: bytes) -> str:
    """Hash SHA-256 dei byte dell'immagine, per il registro e il blocco."""
    return hashlib.sha256(dati).hexdigest()


def leggi_redgifs(payload: object) -> list[ElementoFonte]:
    """Elementi dalla risposta di ricerca di RedGifs; campi mancanti = elemento scartato."""
    if not isinstance(payload, dict) or not isinstance(payload.get("gifs"), list):
        return []
    elementi: list[ElementoFonte] = []
    for voce in payload["gifs"]:
        if not isinstance(voce, dict) or voce.get("published") is False:
            continue
        id_fonte = str(voce.get("id") or "")
        urls = voce.get("urls") if isinstance(voce.get("urls"), dict) else {}
        anteprima = str(urls.get("poster") or urls.get("thumbnail") or "")
        if not re.fullmatch(r"[a-z0-9]{3,64}", id_fonte) or not anteprima:
            continue
        tag = tuple(str(t) for t in (voce.get("tags") or []) + (voce.get("niches") or []) if isinstance(t, str))
        elementi.append(
            ElementoFonte(
                fonte="redgifs",
                id_fonte=id_fonte,
                tag=tag[:50],
                testo=str(voce.get("description") or "")[:500],
                autore=str(voce.get("userName") or "")[:100],
                verificato=voce.get("verified") is True,
                url_pagina=f"https://www.redgifs.com/watch/{id_fonte}",
                url_anteprima=anteprima,
            )
        )
    return elementi

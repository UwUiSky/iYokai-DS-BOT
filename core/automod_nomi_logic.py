"""
core/automod_nomi_logic.py
==========================
Pulizia dei nomi (MOD-102), senza Discord: «dehoist» (via i simboli all'inizio che fanno salire un nome in cima
all'elenco) e «simboli» (lettere decorative, testo impilato, caratteri invisibili). Spenti di base (D66).
Funzioni coperte: SPEC §6 (MOD-102)
"""

from __future__ import annotations

import unicodedata

MAX_NICK = 32
SEGNI_IMPILATI_MAX = 2  # oltre questi, sopra una lettera, e' testo «zalgo»
# Invisibili e di direzione: non servono a un nome e ne nascondono il contenuto.
INVISIBILI = frozenset("­​‌‍⁠﻿᠎‎‏‪‫‬‭‮⁦⁧⁨⁩")
MAX_MEMBRI_GIRO = 1000
PAUSA_GIRO = 0.4  # secondi tra due modifiche (limite di frequenza di Discord)


def senza_hoist(nome: str) -> str:
    """Toglie da `nome` tutto cio' che sta prima della prima lettera o cifra."""
    i = 0
    while i < len(nome) and not nome[i].isalnum():
        i += 1
    return nome[i:]


def senza_simboli(nome: str) -> str:
    """Lettere decorative a lettere normali (NFKC), niente invisibili, al piu' 2 segni impilati su una lettera."""
    testo = unicodedata.normalize("NFKC", nome)
    uscita: list[str] = []
    segni = 0
    for c in testo:
        if c in INVISIBILI or unicodedata.category(c) in ("Cc", "Cs"):
            continue
        if unicodedata.category(c) in ("Mn", "Me"):
            segni += 1
            if segni > SEGNI_IMPILATI_MAX:
                continue
        else:
            segni = 0
        uscita.append(c)
    return " ".join("".join(uscita).split())


def pulisci_nome(nome: str, *, dehoist: bool, simboli: bool, sostitutivo: str) -> str | None:
    """
    Il nome ripulito, o None se non c'e' niente da cambiare. Se non resta niente da mostrare: `sostitutivo`.
    Ripulire un nome gia' pulito da' None (il cambio non rimette in moto se stesso).
    """
    nuovo = nome
    if simboli:
        nuovo = senza_simboli(nuovo)
    if dehoist:
        nuovo = senza_hoist(nuovo)
    nuovo = nuovo.strip()[:MAX_NICK].strip() or sostitutivo
    return None if nuovo == nome else nuovo

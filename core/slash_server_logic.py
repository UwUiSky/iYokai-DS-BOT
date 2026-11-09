"""
core/slash_server_logic.py
==========================
Comandi e menu del server che rispondono con un tag (B28): controllo dei nomi, impronta delle definizioni, regole della sync
(una ogni 5 minuti, 200 creazioni al giorno per server). Funzioni semplici, senza Discord e senza database.
Funzioni coperte: catalogo #128 UTL-045, UTL-046 (D69, D60, B28)
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta

MAX_COMANDI = 25          # nomi di primo livello per server (Discord: 100)
MAX_SOTTO = 25            # sotto-comandi per gruppo (Discord: 25)
MAX_MENU = 5              # per tipo, per server (Discord: 15)
MAX_NOME = 32
MAX_DESCRIZIONE = 100
INTERVALLO_SYNC = 300     # secondi tra due sync dello stesso server
MAX_CREAZIONI_GIORNO = 200  # LIMITI tab. 85
AZIONE_SYNC = "slash_server_sync"
TIPI_MENU = ("utente", "messaggio")
PREFISSI_RISERVATI = ("admin", "mod", "founder")  # D60

_NOME_COMANDO = re.compile(r"^[a-z0-9_-]{1,32}$")
_NOME_MENU = re.compile(r"^[^\W_][\w \-]{0,31}$", re.UNICODE)


def normalizza_nome(nome: str, *, sotto: bool = False) -> str | None:
    pulito = (nome or "").strip().lower()
    return pulito if _NOME_COMANDO.match(pulito) else None


def errore_nome_comando(nome: str, globali: set[str]) -> str | None:
    """Chiave del testo d'errore se `nome` (già normalizzato) non va per un comando del server, altrimenti None."""
    if not _NOME_COMANDO.match(nome):
        return "slash_nome_non_valido"
    if nome.startswith(PREFISSI_RISERVATI):
        return "slash_nome_riservato"
    if nome in globali:
        return "slash_nome_globale"
    return None


def errore_nome_menu(nome: str, globali: set[str]) -> str | None:
    """Per i menu del tasto destro: 1-32 caratteri, anche con spazi e maiuscole."""
    if not _NOME_MENU.match(nome or ""):
        return "slash_menu_nome_non_valido"
    if nome.casefold().startswith(PREFISSI_RISERVATI):
        return "slash_nome_riservato"
    if nome.casefold() in {g.casefold() for g in globali}:
        return "slash_nome_globale"
    return None


def impronta(comandi: list[tuple], menu: list[tuple]) -> str:
    """sha256 delle definizioni (nome, sotto, descrizione / nome, tipo), indipendente dall'ordine: cambia solo se cambia Discord."""
    testo = json.dumps([sorted(map(list, comandi)), sorted(map(list, menu))], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(testo.encode()).hexdigest()


def nomi_di_discord(comandi: list[tuple], menu: list[tuple]) -> list[str]:
    """I nomi che Discord vedrebbe (un gruppo conta uno): servono a contare le creazioni nuove."""
    return sorted({f"c:{c[0]}" for c in comandi} | {f"m:{m[1]}:{m[0]}" for m in menu})


def creazioni_nuove(vecchi: list[str], nuovi: list[str]) -> int:
    return len(set(nuovi) - set(vecchi))


def attesa_sync(ultimo: datetime | None, adesso: datetime) -> int:
    """Secondi ancora da aspettare prima di poter sincronizzare di nuovo (0 = si può)."""
    if ultimo is None:
        return 0
    return max(0, int(INTERVALLO_SYNC - (adesso - ultimo).total_seconds() + 0.999))


def creazioni_di_oggi(giorno: date | None, usate: int, oggi: date) -> int:
    return usate if giorno == oggi else 0


def quando_riprovare(ultimo: datetime | None, adesso: datetime) -> datetime:
    return adesso + timedelta(seconds=max(attesa_sync(ultimo, adesso), 1))

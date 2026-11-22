"""
core/backup_modelli_logic.py
============================
Modelli di server: pochi modelli pronti nel bot, lettura di un modello di Discord (nome, codice o link
discord.new) e conversione nella struttura che il caricamento già conosce. Un modello non porta mai
ban, membri, messaggi né permessi dei singoli utenti.
Funzioni coperte: BKP-020, BKP-021, BKP-022
"""

from __future__ import annotations

import re

import discord

from core import backup_struttura_logic as struttura

_CODICE_DISCORD = re.compile(r"^[A-Za-z0-9]{8,32}$")
_LINK_DISCORD = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:discord\.new|discord(?:app)?\.com/template)/([A-Za-z0-9]{8,32})/?$", re.IGNORECASE
)


def _perm(*nomi: str) -> int:
    return discord.Permissions(**{n: True for n in nomi}).value


_BASE = _perm("view_channel", "send_messages", "read_message_history", "add_reactions", "embed_links",
              "attach_files", "connect", "speak", "use_voice_activation")

# Pochi modelli pronti: solo ruoli, categorie e canali; nessun permesso pericoloso.
MODELLI_PRONTI: dict[str, dict] = {
    "comunita": {
        "titolo": "Comunità",
        "descrizione": "Un server generale: benvenuto, chiacchiere, aiuto e due stanze vocali.",
        "dati": {
            "versione": 1, "nome": "Comunità", "everyone": _BASE,
            "ruoli": [
                {"nome": "Staff", "colore": 0xC24A3A, "hoist": True, "mentionable": False,
                 "permessi": _perm("manage_messages"), "posizione": 2},
                {"nome": "Membro", "colore": 0, "hoist": False, "mentionable": False, "permessi": _BASE, "posizione": 1},
            ],
            "categorie": [{"nome": "Info", "posizione": 0, "overwrite": []}, {"nome": "Chiacchiere", "posizione": 1, "overwrite": []},
                          {"nome": "Vocali", "posizione": 2, "overwrite": []}],
            "canali": [
                {"nome": "benvenuto", "tipo": "testo", "categoria": "Info", "posizione": 0},
                {"nome": "regole", "tipo": "testo", "categoria": "Info", "posizione": 1},
                {"nome": "annunci", "tipo": "annunci", "categoria": "Info", "posizione": 2},
                {"nome": "generale", "tipo": "testo", "categoria": "Chiacchiere", "posizione": 3},
                {"nome": "aiuto", "tipo": "testo", "categoria": "Chiacchiere", "posizione": 4},
                {"nome": "Sala 1", "tipo": "vocale", "categoria": "Vocali", "posizione": 5},
                {"nome": "Sala 2", "tipo": "vocale", "categoria": "Vocali", "posizione": 6},
            ],
        },
    },
    "gioco": {
        "titolo": "Gioco",
        "descrizione": "Per un gruppo che gioca insieme: squadre, ricerca compagni e vocali.",
        "dati": {
            "versione": 1, "nome": "Gioco", "everyone": _BASE,
            "ruoli": [
                {"nome": "Capitano", "colore": 0x9B4D7A, "hoist": True, "mentionable": True, "permessi": _BASE, "posizione": 2},
                {"nome": "Giocatore", "colore": 0, "hoist": False, "mentionable": True, "permessi": _BASE, "posizione": 1},
            ],
            "categorie": [{"nome": "Squadra", "posizione": 0, "overwrite": []}, {"nome": "Vocali", "posizione": 1, "overwrite": []}],
            "canali": [
                {"nome": "annunci", "tipo": "annunci", "categoria": "Squadra", "posizione": 0},
                {"nome": "cerco-compagni", "tipo": "testo", "categoria": "Squadra", "posizione": 1},
                {"nome": "strategie", "tipo": "testo", "categoria": "Squadra", "posizione": 2},
                {"nome": "Squadra A", "tipo": "vocale", "categoria": "Vocali", "posizione": 3},
                {"nome": "Squadra B", "tipo": "vocale", "categoria": "Vocali", "posizione": 4},
            ],
        },
    },
    "studio": {
        "titolo": "Studio",
        "descrizione": "Per studiare insieme: materie, domande, risorse e stanze di silenzio.",
        "dati": {
            "versione": 1, "nome": "Studio", "everyone": _BASE,
            "ruoli": [
                {"nome": "Tutor", "colore": 0xC24A3A, "hoist": True, "mentionable": True,
                 "permessi": _perm("manage_messages"), "posizione": 2},
                {"nome": "Studente", "colore": 0, "hoist": False, "mentionable": False, "permessi": _BASE, "posizione": 1},
            ],
            "categorie": [{"nome": "Studio", "posizione": 0, "overwrite": []}, {"nome": "Stanze", "posizione": 1, "overwrite": []}],
            "canali": [
                {"nome": "regole", "tipo": "testo", "categoria": "Studio", "posizione": 0},
                {"nome": "domande", "tipo": "forum", "categoria": "Studio", "posizione": 1},
                {"nome": "risorse", "tipo": "testo", "categoria": "Studio", "posizione": 2},
                {"nome": "Silenzio", "tipo": "vocale", "categoria": "Stanze", "posizione": 3},
                {"nome": "Gruppo", "tipo": "vocale", "categoria": "Stanze", "posizione": 4},
            ],
        },
    },
}


def trova_pronto(testo: str) -> tuple[str, dict] | None:
    """Un modello pronto, per chiave o per titolo (senza badare alle maiuscole)."""
    voluto = (testo or "").strip().casefold()
    for chiave, m in MODELLI_PRONTI.items():
        if voluto in (chiave, m["titolo"].casefold()):
            return chiave, m
    return None


def codice_discord(testo: str) -> str | None:
    """Il codice di un modello di Discord, da un link discord.new o discord.com/template, o dal codice nudo."""
    pulito = (testo or "").strip()
    trovato = _LINK_DISCORD.match(pulito)
    if trovato:
        return trovato.group(1)
    return pulito if _CODICE_DISCORD.match(pulito) else None


def _senza_everyone_come_ruolo(righe: list[dict]) -> list[dict]:
    """Nei modelli di Discord @everyone ha un id suo: i permessi su di lui diventano quelli di @everyone."""
    return [{"everyone": True, "allow": o["allow"], "deny": o["deny"]} if o.get("ruolo") == "@everyone" else o for o in righe]


def da_modello_discord(modello: discord.Template) -> tuple[str, dict] | None:
    """(nome, struttura) letti da un modello di Discord, o None se non è leggibile o non è valido."""
    try:
        g = modello.source_guild
        predefinito = next((r for r in g.roles if r.id in (0, g.id) or r.name == "@everyone"), None)
        canali = [leggi for leggi in g.channels if leggi.type in struttura._TIPI]
        dati = {
            "versione": struttura.VERSIONE,
            "nome": (modello.name or "modello")[:100],
            "impostazioni": {
                "verification_level": g.verification_level.value,
                "default_notifications": g.default_notifications.value,
                "explicit_content_filter": g.explicit_content_filter.value,
            },
            "everyone": predefinito.permissions.value if predefinito is not None else 0,
            "ruoli": [struttura.leggi_ruolo(r) for r in g.roles if r is not predefinito and not r.managed],
            "categorie": [
                {"nome": c.name, "posizione": c.position, "overwrite": struttura._overwrite(c)} for c in g.categories
            ],
            "canali": [struttura.leggi_canale(c) for c in canali],
            "emoji": [], "sticker": [],
        }
        for c in (*dati["categorie"], *dati["canali"]):
            c["overwrite"] = _senza_everyone_come_ruolo(c["overwrite"])
        dati = struttura.senza_dati_personali(dati)
    except Exception:
        return None
    if struttura.valida_struttura(dati):
        return None
    return dati["nome"], dati

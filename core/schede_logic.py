"""
core/schede_logic.py
====================
Schede informative di utente, server, canale e ruolo, elenco dei ruoli,
classifiche di anzianità e permessi in un canale: i testi già pronti per
un embed (campi entro 1024, al massimo 25). Funzioni pure.
Funzioni coperte: SPEC §14 (catalogo #128: UTL-195, 197-200, 202; #123: RUO-110-112)
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import discord

MAX_CAMPO = 1024
# Le classifiche di anzianità mostrano al massimo 100 righe (a pagine).
MAX_CLASSIFICA = 100

ANZIANITA = {
    "account-vecchi": ("Account più vecchi", "created_at", False),
    "account-nuovi": ("Account più nuovi", "created_at", True),
    "primi-entrati": ("Entrati per primi", "joined_at", False),
    "ultimi-entrati": ("Entrati per ultimi", "joined_at", True),
}

# Permessi che contano di più quando si cerca perché qualcosa non va.
PERMESSI_CHIAVE = (
    "administrator", "manage_guild", "manage_roles", "manage_channels", "manage_messages",
    "manage_webhooks", "kick_members", "ban_members", "moderate_members", "mention_everyone",
    "view_channel", "send_messages", "embed_links", "attach_files", "add_reactions",
    "read_message_history", "connect", "speak", "use_application_commands",
)


def data_discord(quando: datetime | None, stile: str = "D") -> str:
    """Data nel formato di Discord (ognuno la vede nel suo fuso); '—' se manca."""
    if quando is None:
        return "—"
    return f"<t:{int(quando.timestamp())}:{stile}>"


def taglia(testo: str, limite: int = MAX_CAMPO) -> str:
    return testo if len(testo) <= limite else testo[: limite - 1] + "…"


def elenco_menzioni(voci: list[str], limite: int = MAX_CAMPO) -> str:
    """Menzioni separate da spazi, senza superare il limite: in coda '+N'."""
    usate: list[str] = []
    totale = 0
    for indice, voce in enumerate(voci):
        resto = f" +{len(voci) - indice}"
        if totale + len(voce) + 1 + len(resto) > limite:
            return " ".join(usate) + resto
        usate.append(voce)
        totale += len(voce) + 1
    return " ".join(usate) or "—"


def campi_utente(membro) -> list[tuple[str, str]]:
    ruoli = [r for r in reversed(membro.roles) if not r.is_default()]
    campi = [
        ("ID", f"`{membro.id}`"),
        ("Account creato", f"{data_discord(membro.created_at)} ({data_discord(membro.created_at, 'R')})"),
        ("Entrato nel server", f"{data_discord(membro.joined_at)} ({data_discord(membro.joined_at, 'R')})"),
        (f"Ruoli ({len(ruoli)})", elenco_menzioni([r.mention for r in ruoli])),
    ]
    if getattr(membro, "premium_since", None):
        campi.append(("Booster dal", data_discord(membro.premium_since)))
    if membro.bot:
        campi.append(("Tipo", "Bot"))
    return campi


def campi_server(guild) -> list[tuple[str, str]]:
    umani = sum(1 for m in guild.members if not m.bot)
    bot = len(guild.members) - umani
    conteggio = f"{guild.member_count or len(guild.members)}"
    if guild.members:
        conteggio += f" ({umani} umani, {bot} bot)"
    return [
        ("ID", f"`{guild.id}`"),
        ("Proprietario", f"<@{guild.owner_id}>"),
        ("Creato", f"{data_discord(guild.created_at)} ({data_discord(guild.created_at, 'R')})"),
        ("Membri", conteggio),
        ("Canali", f"{len(guild.text_channels)} testo, {len(guild.voice_channels)} vocali, {len(guild.categories)} categorie"),
        ("Ruoli", str(len(guild.roles))),
        ("Emoji e sticker", f"{len(guild.emojis)} emoji, {len(guild.stickers)} sticker"),
        ("Boost", f"livello {guild.premium_tier}, {guild.premium_subscription_count or 0} boost"),
        ("Verifica", str(guild.verification_level)),
    ]


def campi_canale(canale) -> list[tuple[str, str]]:
    campi = [
        ("ID", f"`{canale.id}`"),
        ("Tipo", str(canale.type)),
        ("Creato", data_discord(canale.created_at)),
        ("Categoria", canale.category.name if getattr(canale, "category", None) else "—"),
    ]
    argomento = getattr(canale, "topic", None)
    if argomento:
        campi.append(("Argomento", taglia(argomento)))
    lento = getattr(canale, "slowmode_delay", 0)
    if lento:
        campi.append(("Modalità lenta", f"{lento} s"))
    if getattr(canale, "nsfw", False):
        campi.append(("NSFW", "sì"))
    if isinstance(canale, discord.VoiceChannel):
        campi.append(("Vocale", f"{len(canale.members)} dentro, limite {canale.user_limit or '—'}, {canale.bitrate // 1000} kbps"))
    return campi


def campi_ruolo(ruolo) -> list[tuple[str, str]]:
    attivi = [nome for nome in PERMESSI_CHIAVE if getattr(ruolo.permissions, nome, False)]
    return [
        ("ID", f"`{ruolo.id}`"),
        ("Colore", str(ruolo.colour)),
        ("Membri", str(len(ruolo.members))),
        ("Creato", data_discord(ruolo.created_at)),
        ("Posizione", str(ruolo.position)),
        ("Menzionabile", "sì" if ruolo.mentionable else "no"),
        ("Separato", "sì" if ruolo.hoist else "no"),
        ("Gestito da un'integrazione", "sì" if ruolo.managed else "no"),
        ("Permessi principali", taglia(", ".join(attivi) or "nessuno")),
    ]


def righe_ruoli(ruoli: Iterable) -> list[str]:
    """Una riga per ruolo, dal più alto: ID, menzione, membri, colore; avviso su @everyone."""
    righe = []
    for ruolo in sorted(ruoli, key=lambda r: r.position, reverse=True):
        if ruolo.is_default():
            continue
        riga = f"`{ruolo.id}` {ruolo.mention} — {len(ruolo.members)} membri — {ruolo.colour}"
        if ruolo.permissions.mention_everyone:
            riga += " — può menzionare @everyone"
        righe.append(riga)
    return righe


def classifica_anzianita(membri: Iterable, tipo: str) -> list[str]:
    """Le prime MAX_CLASSIFICA righe della classifica scelta."""
    _, attributo, al_contrario = ANZIANITA[tipo]
    con_data = [m for m in membri if getattr(m, attributo, None) is not None]
    ordinati = sorted(con_data, key=lambda m: getattr(m, attributo), reverse=al_contrario)
    return [
        f"{posto}. {m.mention} — {data_discord(getattr(m, attributo))}"
        for posto, m in enumerate(ordinati[:MAX_CLASSIFICA], start=1)
    ]


def righe_permessi(permessi: discord.Permissions) -> tuple[str, str]:
    """(permessi chiave concessi, permessi chiave mancanti)."""
    si = [nome for nome in PERMESSI_CHIAVE if getattr(permessi, nome)]
    no = [nome for nome in PERMESSI_CHIAVE if not getattr(permessi, nome)]
    return taglia(", ".join(si) or "nessuno"), taglia(", ".join(no) or "nessuno")

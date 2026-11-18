"""
core/schede_logic.py
====================
Schede informative di utente, server, canale e ruolo, elenco dei ruoli,
classifiche di anzianità e permessi in un canale: i testi già pronti per
un embed (campi entro 1024, al massimo 25). Funzioni pure.
Funzioni coperte: SPEC §14 (catalogo #128: UTL-195, 197-200, 202; #123: RUO-110-112); STA-058 (membri in file), STA-059 (invito, emoji)
"""

from __future__ import annotations

import re
import unicodedata
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


MAX_RIGHE_MEMBRI_FILE = 100_000  # STA-058: tetto alle righe del file

_RE_EMOJI = re.compile(r"<(a?):([A-Za-z0-9_]{2,32}):(\d{15,21})>")


def leggi_emoji(testo: str) -> tuple[str, str | None, int | None, bool]:
    """STA-059: (tipo, nome, id, animata). Tipo «custom» per `<:nome:id>` o un ID numerico, «unicode» per un carattere, «niente» altrimenti."""
    testo = testo.strip()
    trovata = _RE_EMOJI.fullmatch(testo)
    if trovata:
        return "custom", trovata.group(2), int(trovata.group(3)), trovata.group(1) == "a"
    if testo.isdigit() and 15 <= len(testo) <= 21:
        return "custom", None, int(testo), False
    if 0 < len(testo) <= 16 and not testo.isascii():
        return "unicode", testo, None, False
    return "niente", None, None, False


def campi_emoji(testo: str, trovata=None, server_corrente_id: int | None = None) -> list[tuple[str, str]]:
    """STA-059: la scheda di un'emoji. `trovata` è l'emoji che il bot conosce (server dove sta il bot).

    Il nome di un altro server non si mostra: l'emoji può stare in un server dove chi chiede non è.
    """
    tipo, nome, emoji_id, animata = leggi_emoji(testo)
    if tipo == "unicode":
        punti = " ".join(f"U+{ord(c):04X}" for c in nome)
        nomi = ", ".join(unicodedata.name(c, "?").title() for c in nome[:4])
        return [("Tipo", "Emoji standard"), ("Carattere", nome), ("Punti Unicode", punti), ("Nome", nomi)]
    if tipo == "niente":
        return []
    campi = [("Tipo", "Emoji personalizzata"), ("ID", f"`{emoji_id}`"),
             ("Creata", data_discord(discord.utils.snowflake_time(emoji_id)))]
    nome = getattr(trovata, "name", None) or nome
    if nome:
        campi.append(("Nome", f"`{nome}`"))
    animata = bool(getattr(trovata, "animated", animata))
    campi.append(("Animata", "sì" if animata else "no"))
    if trovata is not None and getattr(trovata, "guild_id", None) == server_corrente_id and server_corrente_id is not None:
        campi.append(("Server", "questo"))
    campi.append(("Immagine", f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animata else 'png'}"))
    return campi


def campi_invito(invito) -> list[tuple[str, str]]:
    """STA-059: la scheda di un invito (le informazioni che Discord dà a chiunque abbia il codice)."""
    server = getattr(invito, "guild", None)
    campi = [("Codice", f"`{invito.code}`")]
    if server is not None:
        campi.append(("Server", taglia(str(server.name), 200)))
    canale = getattr(invito, "channel", None)
    if canale is not None and getattr(canale, "name", None):
        campi.append(("Canale", taglia(f"#{canale.name}", 200)))
    chi = getattr(invito, "inviter", None)
    if chi is not None:
        campi.append(("Creato da", f"{taglia(chi.name, 100)} (`{chi.id}`)"))
    if getattr(invito, "approximate_member_count", None) is not None:
        campi.append(("Membri", str(invito.approximate_member_count)))
    if getattr(invito, "approximate_presence_count", None) is not None:
        campi.append(("Online", str(invito.approximate_presence_count)))
    scade = getattr(invito, "expires_at", None)
    campi.append(("Scade", data_discord(scade) if scade else "mai"))
    usi = getattr(invito, "uses", None)
    if usi is not None:
        massimo = getattr(invito, "max_uses", 0)
        campi.append(("Usi", f"{usi}/{massimo}" if massimo else str(usi)))
    return campi


def righe_membri_csv(membri: Iterable) -> list[list]:
    """STA-058: id, nome da mostrare, bot, entrato il, account creato il. Solo dati che un amministratore già vede."""
    righe = []
    for m in membri:
        if len(righe) >= MAX_RIGHE_MEMBRI_FILE:
            break
        righe.append([
            m.id, m.display_name[:80], "sì" if m.bot else "no",
            m.joined_at.isoformat() if m.joined_at else "", m.created_at.isoformat() if m.created_at else "",
        ])
    return righe

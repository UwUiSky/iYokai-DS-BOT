"""
core/lockdown_logic.py
======================
Cosa bloccare e come ripristinare, senza Discord: quali permessi di @everyone
si tolgono per tipo di canale, come si salva lo stato di prima e come si
rimette, chi puo' usare i comandi durante il panico.
Funzioni coperte: SPEC §23 (NF-29), catalogo SIC-011..015

Regola di fondo: si tocca solo cio' che il blocco ha cambiato. Un permesso che
era gia' negato resta com'e', e allo sblocco si rimette solo cio' che il
blocco aveva negato (se nel frattempo qualcuno ha concesso quel permesso a
mano, la sua scelta vince).
"""

from __future__ import annotations

from dataclasses import dataclass

import discord

from core.security_logic import AntiNukeConfig, TRUST_KIND_USER, voci_fiducia

NOME_CANALE_NASCOSTO = "___hidden___"  # LIM-38

# Limiti scelti per rispettare i tetti di Discord e dell'interfaccia.
MAX_RUOLI_AVVISO = 10  # SIC-013: un messaggio con piu' ping e' spam
MAX_CATEGORIE_ESCLUSE = 25  # SIC-014
MAX_SBLOCCO_MINUTI = 1440  # SIC-015: un giorno
MAX_MOTIVO = 512
GRANDEZZA_GRUPPO = 8  # canali modificati insieme
PAUSA_TRA_GRUPPI = 0.4  # secondi

PERMESSI_TESTO = (
    "send_messages",
    "send_messages_in_threads",
    "create_public_threads",
    "create_private_threads",
    "add_reactions",
)
PERMESSI_VOCE = ("connect", "speak")

TIPO_BLOCCO = "blocco"
TIPO_PANICO = "panico"

STATO_IN_CORSO = "in_corso"
STATO_ATTIVO = "attivo"
STATO_IN_RIAPERTURA = "in_riapertura"

Prima = dict[str, bool | None]


def permessi_da_bloccare(canale) -> tuple[str, ...]:
    """I permessi di @everyone da negare in questo canale (vuoto: il canale non si tocca)."""
    if isinstance(canale, (discord.VoiceChannel, discord.StageChannel)):
        return PERMESSI_VOCE
    if isinstance(canale, (discord.TextChannel, discord.ForumChannel)):
        return PERMESSI_TESTO
    return ()  # categorie, thread: i canali si bloccano uno per uno


def canale_escluso(canale, categorie_escluse) -> bool:
    """Il canale e' in una categoria esclusa, o e' proprio la categoria."""
    escluse = set(categorie_escluse)
    return canale.id in escluse or getattr(canale, "category_id", None) in escluse


def canali_da_bloccare(canali, categorie_escluse) -> list[tuple[object, tuple[str, ...]]]:
    """(canale, permessi) per ogni canale che il blocco deve toccare, nell'ordine dato."""
    piano = []
    for canale in canali:
        if getattr(canale, "name", "") == NOME_CANALE_NASCOSTO:
            continue
        permessi = permessi_da_bloccare(canale)
        if permessi and not canale_escluso(canale, categorie_escluse):
            piano.append((canale, permessi))
    return piano


def stato_prima(overwrite: discord.PermissionOverwrite, permessi: tuple[str, ...]) -> Prima:
    """Per ogni permesso: True (concesso), False (negato) o None (non impostato)."""
    return {nome: getattr(overwrite, nome) for nome in permessi}


def gia_bloccato(prima: Prima) -> bool:
    return bool(prima) and all(valore is False for valore in prima.values())


def blocca(overwrite: discord.PermissionOverwrite, permessi: tuple[str, ...]) -> discord.PermissionOverwrite:
    for nome in permessi:
        setattr(overwrite, nome, False)
    return overwrite


def ripristina(overwrite: discord.PermissionOverwrite, prima: Prima) -> discord.PermissionOverwrite | None:
    """
    Rimette i permessi di prima, ma solo dove oggi c'e' ancora il nostro
    divieto. Restituisce None se l'overwrite resta vuoto (si toglie del tutto).
    """
    for nome, valore in prima.items():
        if getattr(overwrite, nome) is False and valore is not False:
            setattr(overwrite, nome, valore)
    return None if overwrite.is_empty() else overwrite


def puo_agire_in_panico(user_id: int, owner_id: int, config: AntiNukeConfig) -> bool:
    """SIC-012: durante il panico i comandi di moderazione li usano solo il proprietario e i fidati (utenti)."""
    if user_id == owner_id:
        return True
    return any(v.kind == TRUST_KIND_USER and v.target_id == user_id for v in voci_fiducia(config))


@dataclass(frozen=True)
class Esito:
    ok: bool
    messaggio: str
    bloccati: int = 0
    saltati: int = 0
    falliti: int = 0


def testo_riepilogo(
    *, tipo: str, bloccati: int, saltati: int, falliti: int, verifica: bool, inviti: bool, finisce_il=None
) -> str:
    nome = "Panico" if tipo == TIPO_PANICO else "Blocco totale"
    righe = [f"**{nome} attivo.** Canali bloccati: {bloccati}."]
    if saltati:
        righe.append(f"Lasciati com'erano (esclusi, gia' bloccati o nascosti): {saltati}.")
    if falliti:
        righe.append(f"**{falliti} canali non sono riuscito a bloccarli** (permessi mancanti): controlla a mano.")
    righe.append(f"Ingressi: {'livello di verifica al massimo' if verifica else 'livello di verifica invariato'}"
                 f"{', inviti chiusi' if inviti else ''}.")
    if finisce_il is not None:
        righe.append(f"Si riapre da solo <t:{int(finisce_il.timestamp())}:R>.")
    righe.append("Per riaprire: stesso comando con «togli».")
    return "\n".join(righe)[:1900]

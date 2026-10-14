"""
core/command_policy.py
======================
Politica dei comandi di un server (CFG-008, CFG-009, CFG-010 del catalogo #122; diagnosi CFG-018).

Cosa può decidere l'admin, con `/utility politica ...`:
- spegnere UN comando (non un modulo intero);
- limitare i comandi ad alcuni canali (elenco dei permessi) o vietarli in altri;
- far ignorare al bot certi ruoli e certi utenti.

Regole di sicurezza (così nessuno si chiude fuori):
- i comandi di `/admin`, `/owner` e `/utility politica` non si spengono mai;
- l'owner del bot, il proprietario del server e chi ha «Gestisci server» non sono mai bloccati da canali o da
  ruoli/utenti ignorati (un comando spento invece vale per tutti, tranne i gruppi qui sopra);
- un canale vale anche se è il thread o la categoria sotto cui sta.
Le impostazioni stanno in `guild_config.settings` (chiavi `policy_*`, nello schema di import/export) e passano da
queste funzioni, sia per il comando sia per il futuro pannello (D16). Il controllo gira in
`BlacklistAwareCommandTree.interaction_check`, prima di ogni comando.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

CHIAVE_COMANDI_OFF = "policy_comandi_off"
CHIAVE_CANALI_OK = "policy_canali_ok"
CHIAVE_CANALI_NO = "policy_canali_no"
CHIAVE_RUOLI_IGNORATI = "policy_ignora_ruoli"
CHIAVE_UTENTI_IGNORATI = "policy_ignora_utenti"
CHIAVI_ID = (CHIAVE_CANALI_OK, CHIAVE_CANALI_NO, CHIAVE_RUOLI_IGNORATI, CHIAVE_UTENTI_IGNORATI)
TUTTE_LE_CHIAVI = (CHIAVE_COMANDI_OFF, *CHIAVI_ID)

MAX_VOCI = 250
MAX_LUNGHEZZA_PERCORSO = 100
# Mai spenti: servono a rimettere a posto la politica.
PREFISSI_SEMPRE_APERTI = ("admin", "owner", "utility politica")

MOTIVO_COMANDO_OFF = "pol_comando_spento"
MOTIVO_UTENTE_IGNORATO = "pol_ignorato"
MOTIVO_CANALE_VIETATO = "pol_canale_vietato"
MOTIVO_CANALE_NON_PERMESSO = "pol_canale_non_permesso"


@dataclass(frozen=True)
class Politica:
    comandi_off: frozenset[str] = frozenset()
    canali_ok: frozenset[int] = frozenset()
    canali_no: frozenset[int] = frozenset()
    ruoli_ignorati: frozenset[int] = frozenset()
    utenti_ignorati: frozenset[int] = frozenset()

    @property
    def vuota(self) -> bool:
        return not (self.comandi_off or self.canali_ok or self.canali_no or self.ruoli_ignorati or self.utenti_ignorati)


def sempre_aperto(percorso: str) -> bool:
    return any(percorso == p or percorso.startswith(p + " ") for p in PREFISSI_SEMPRE_APERTI)


def valuta(
    politica: Politica,
    *,
    percorso: str,
    canali: Iterable[int],
    ruoli: Iterable[int],
    user_id: int,
    esente: bool,
) -> str | None:
    """None se il comando può girare, altrimenti la chiave del motivo (testo nel catalogo delle lingue)."""
    if sempre_aperto(percorso):
        return None
    if percorso in politica.comandi_off:
        return MOTIVO_COMANDO_OFF
    if esente:
        return None
    if user_id in politica.utenti_ignorati or any(r in politica.ruoli_ignorati for r in ruoli):
        return MOTIVO_UTENTE_IGNORATO
    dove = set(canali)
    if dove & politica.canali_no:
        return MOTIVO_CANALE_VIETATO
    if politica.canali_ok and not (dove & politica.canali_ok):
        return MOTIVO_CANALE_NON_PERMESSO
    return None


async def leggi_politica(guild_id: int) -> Politica:
    from core.database import db

    async def lista(chiave: str, tipo):
        valore = await db.get_guild_setting(guild_id, chiave, [])
        return frozenset(v for v in valore if isinstance(v, tipo) and not isinstance(v, bool)) if isinstance(valore, list) else frozenset()

    return Politica(
        comandi_off=await lista(CHIAVE_COMANDI_OFF, str),
        canali_ok=await lista(CHIAVE_CANALI_OK, int),
        canali_no=await lista(CHIAVE_CANALI_NO, int),
        ruoli_ignorati=await lista(CHIAVE_RUOLI_IGNORATI, int),
        utenti_ignorati=await lista(CHIAVE_UTENTI_IGNORATI, int),
    )


class ElencoPieno(ValueError):
    """L'elenco ha già `MAX_VOCI` voci."""


class VoceNonValida(ValueError):
    """Il comando è troppo lungo, o non si può spegnere."""


async def modifica_elenco(guild_id: int, chiave: str, valore, *, aggiungi: bool, changed_by: int | None) -> bool:
    """
    Aggiunge o toglie `valore` da un elenco della politica. True se l'elenco è cambiato.
    Un solo punto per comando e pannello; l'elenco vuoto toglie la chiave.
    """
    from core.database import db

    if chiave not in TUTTE_LE_CHIAVI:
        raise KeyError(chiave)
    if chiave == CHIAVE_COMANDI_OFF:
        if not isinstance(valore, str) or not valore or len(valore) > MAX_LUNGHEZZA_PERCORSO or sempre_aperto(valore):
            raise VoceNonValida(str(valore)[:MAX_LUNGHEZZA_PERCORSO])
    elif not isinstance(valore, int) or isinstance(valore, bool) or valore <= 0:
        raise VoceNonValida(str(valore))
    attuale = await db.get_guild_setting(guild_id, chiave, [])
    attuale = list(attuale) if isinstance(attuale, list) else []
    if aggiungi:
        if valore in attuale:
            return False
        if len(attuale) >= MAX_VOCI:
            raise ElencoPieno(chiave)
        attuale.append(valore)
    else:
        if valore not in attuale:
            return False
        attuale.remove(valore)
    if attuale:
        await db.set_guild_setting(guild_id, chiave, attuale, changed_by=changed_by)
    else:
        await db.remove_guild_setting(guild_id, chiave, changed_by=changed_by)
    return True


async def azzera_elenco(guild_id: int, chiave: str, *, changed_by: int | None) -> bool:
    from core.database import db

    if chiave not in TUTTE_LE_CHIAVI:
        raise KeyError(chiave)
    if not await db.get_guild_setting(guild_id, chiave, []):
        return False
    await db.remove_guild_setting(guild_id, chiave, changed_by=changed_by)
    return True


def percorsi_dei_comandi(comandi: Iterable) -> list[str]:
    """I percorsi di tutti i comandi foglia dell'albero (gruppi annidati compresi)."""
    from discord import app_commands

    trovati: list[str] = []
    for nodo in comandi:
        if isinstance(nodo, app_commands.Group):
            trovati.extend(percorsi_dei_comandi(nodo.commands))
        else:
            trovati.append(nodo.qualified_name)
    return trovati


def _canali_dell_interazione(interaction) -> list[int]:
    """Canale, canale padre (thread) e categoria: una regola su uno qualsiasi vale per il comando."""
    canale = getattr(interaction, "channel", None)
    ids = [getattr(interaction, "channel_id", None)]
    for attributo in ("parent_id", "category_id"):
        ids.append(getattr(canale, attributo, None))
    padre = getattr(canale, "parent", None)  # thread di un canale dentro una categoria
    ids.append(getattr(padre, "category_id", None))
    return [i for i in ids if isinstance(i, int)]


def _e_esente(interaction) -> bool:
    from core.config import config

    utente = interaction.user
    guild = interaction.guild
    if utente.id == config.OWNER_ID or (guild is not None and guild.owner_id == utente.id):
        return True
    permessi = getattr(utente, "guild_permissions", None)
    return bool(permessi is not None and permessi.manage_guild)


async def valuta_interazione(interaction) -> str | None:
    """
    Il motivo per cui questo comando non può girare qui (chiave del catalogo), o None.
    Mai eccezioni: se qualcosa va storto il comando passa (una politica rotta non deve bloccare il bot).
    """
    import discord

    try:
        if interaction.guild is None or interaction.type is not discord.InteractionType.application_command:
            return None
        comando = interaction.command
        if comando is None:
            return None
        politica = await leggi_politica(interaction.guild.id)
        if politica.vuota:
            return None
        return valuta(
            politica,
            percorso=comando.qualified_name,
            canali=_canali_dell_interazione(interaction),
            ruoli=[r.id for r in getattr(interaction.user, "roles", ())],
            user_id=interaction.user.id,
            esente=_e_esente(interaction),
        )
    except Exception:
        return None

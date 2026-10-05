"""
core/command_access.py
======================
Chi può usare i gruppi di comandi (D24). UNA sola strada, usata dai
comandi e dal futuro pannello web (D16): decisione pura
(`decidi_accesso`), controllo per le interazioni (`controlla`,
`puo_usare`), `richiedi` per i comandi, `GruppoYokai` per i gruppi, e le
funzioni che leggono e scrivono i ruoli scelti dall'admin del server.
Funzioni coperte: NF-05 (issue #76)
Dipende da: core/config.py (OWNER_ID), core/database.py (impostazioni)

REGOLA PER GLI AUTOCOMPLETE: discord.py NON esegue i controlli dei
comandi né dei gruppi sugli autocomplete. Ogni autocomplete di un comando
sotto un gruppo protetto (o con `richiedi`) va decorato con
`@autocomplete_protetto(Livello.X)`, con lo stesso livello del gruppo:
chi non può usare il comando riceve un elenco vuoto. Sotto un gruppo
protetto un sotto-gruppo deve essere un `GruppoYokai` (un `Group`
semplice viene rifiutato con TypeError).

Il rifiuto non risponde da solo: solleva `AccessoNegato`, che il gestore
globale degli errori (core/premium.py) trasforma in UNA risposta effimera.
"""

from __future__ import annotations

import enum
import functools
from collections.abc import Iterable

import discord
from discord import app_commands

from core.config import config
from core.database import db

SETTING_ADMIN_ROLE = "admin_role_id"
SETTING_MOD_ROLE = "mod_role_id"
SETTING_MODBAN_ROLE = "modban_role_id"


class Livello(enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MOD = "mod"
    MODBAN = "modban"
    SECURITY = "security"
    LOG = "log"


class TipoRuolo(enum.Enum):
    """Ruoli del bot che l'admin sceglie nel passo di /setup."""

    ADMIN = SETTING_ADMIN_ROLE
    MOD = SETTING_MOD_ROLE
    MODBAN = SETTING_MODBAN_ROLE


CHIAVI_RUOLI = (SETTING_ADMIN_ROLE, SETTING_MOD_ROLE, SETTING_MODBAN_ROLE)


def ruolo_valido_per_server(guild: discord.Guild, ruolo_id) -> bool:
    """True se `ruolo_id` è un ruolo vero di questo server (non @everyone, che ha l'id del server)."""
    return (
        isinstance(ruolo_id, int)
        and not isinstance(ruolo_id, bool)
        and ruolo_id != guild.id
        and guild.get_role(ruolo_id) is not None
    )


# Per ogni livello del server: permesso di Discord che basta da solo e
# il tipo di ruolo del bot che vale al suo posto.
_REGOLE: dict[Livello, tuple[str, TipoRuolo]] = {
    Livello.ADMIN: ("manage_guild", TipoRuolo.ADMIN),
    Livello.SECURITY: ("administrator", TipoRuolo.ADMIN),
    Livello.LOG: ("manage_guild", TipoRuolo.ADMIN),
    Livello.MOD: ("moderate_members", TipoRuolo.MOD),
    Livello.MODBAN: ("ban_members", TipoRuolo.MODBAN),
}

_MESSAGGI: dict[Livello, str] = {
    Livello.OWNER: "Questo comando è riservato al proprietario del bot.",
    Livello.ADMIN: "Non puoi usare questo comando: serve il permesso «Gestisci server» o il ruolo admin del bot.",
    Livello.SECURITY: "Non puoi usare questo comando: serve il permesso «Amministratore» o il ruolo admin del bot.",
    Livello.LOG: "Non puoi usare questo comando: serve il permesso «Gestisci server» o il ruolo admin del bot.",
    Livello.MOD: "Non puoi usare questo comando: serve il permesso «Metti in timeout i membri» o il ruolo mod del bot.",
    Livello.MODBAN: "Non puoi usare questo comando: serve il permesso «Banna i membri» o il ruolo ban del bot.",
}
MESSAGGIO_SOLO_SERVER = "Questo comando si usa solo dentro un server."


class AccessoNegato(app_commands.CheckFailure):
    """Sollevata dal controllo. `messaggio` è il testo effimero per l'utente."""

    def __init__(self, livello: Livello | None = None, messaggio: str | None = None) -> None:
        self.livello = livello
        self.messaggio = messaggio or _MESSAGGI.get(livello, "Non puoi usare questo comando.")
        super().__init__(self.messaggio)


def decidi_accesso(
    livello: Livello,
    *,
    user_id: int,
    owner_bot_id: int,
    guild_owner_id: int | None,
    permessi: discord.Permissions,
    ruoli_utente_ids: Iterable[int],
    ruolo_configurato_id: int | None,
    ruolo_esiste: bool = True,
) -> bool:
    """
    Decisione pura, senza Discord. OWNER: solo l'ID dell'owner del bot.
    Gli altri livelli: permesso di Discord, OPPURE il ruolo configurato
    (se esiste ancora nel server), OPPURE proprietario del server.
    """
    if livello is Livello.OWNER:
        return user_id == owner_bot_id
    permesso, _ = _REGOLE[livello]
    if guild_owner_id is not None and user_id == guild_owner_id:
        return True
    if getattr(permessi, permesso):
        return True
    return bool(
        ruolo_configurato_id is not None
        and ruolo_esiste
        and ruolo_configurato_id in set(ruoli_utente_ids)
    )


# ----------------------------------------------------------------------
# Ruoli configurati (D16: un solo punto, usato da comandi e pannello)
# ----------------------------------------------------------------------
async def leggi_ruolo(guild_id: int, tipo: TipoRuolo) -> int | None:
    """
    ID del ruolo configurato, o None se non c'è. Un valore corrotto
    (non numerico, <= 0) o uguale all'id del server (@everyone) vale
    "non configurato": restano i permessi di Discord.
    """
    valore = await db.get_guild_setting(guild_id, tipo.value)
    if not isinstance(valore, int) or isinstance(valore, bool) or valore <= 0 or valore == guild_id:
        return None
    return valore


async def imposta_ruolo(
    guild: discord.Guild,
    tipo: TipoRuolo,
    ruolo: discord.Role | None,
    changed_by: int | None = None,
) -> None:
    """Salva il ruolo (None lo toglie). Rifiuta @everyone e ruoli di altri server."""
    if ruolo is not None:
        if ruolo.id == guild.id:
            raise ValueError("Non puoi usare @everyone come ruolo del bot.")
        if not ruolo_valido_per_server(guild, ruolo.id):
            raise ValueError("Questo ruolo non esiste in questo server.")
    await db.set_guild_setting(
        guild.id, tipo.value, ruolo.id if ruolo is not None else None, changed_by
    )


# ----------------------------------------------------------------------
# Controllo sulle interazioni
# ----------------------------------------------------------------------
async def controlla(interaction: discord.Interaction, livello: Livello) -> bool:
    """True se può usare il comando, altrimenti solleva AccessoNegato."""
    if livello is Livello.OWNER:
        if interaction.user.id == config.OWNER_ID:
            return True
        raise AccessoNegato(livello)

    guild = interaction.guild
    utente = interaction.user
    if guild is None or not isinstance(utente, discord.Member):
        raise AccessoNegato(livello, MESSAGGIO_SOLO_SERVER)

    _, tipo = _REGOLE[livello]
    configurato = await leggi_ruolo(guild.id, tipo)
    ok = decidi_accesso(
        livello,
        user_id=utente.id,
        owner_bot_id=config.OWNER_ID,
        guild_owner_id=guild.owner_id,
        permessi=utente.guild_permissions,
        ruoli_utente_ids=[r.id for r in utente.roles],
        ruolo_configurato_id=configurato,
        ruolo_esiste=configurato is not None and guild.get_role(configurato) is not None,
    )
    if not ok:
        raise AccessoNegato(livello)
    return True


async def puo_usare(interaction: discord.Interaction, livello: Livello) -> bool:
    """Come `controlla`, ma restituisce False invece di sollevare."""
    try:
        return await controlla(interaction, livello)
    except AccessoNegato:
        return False


def richiedi(livello: Livello):
    """Decorator per un comando: `@richiedi(Livello.MOD)`."""

    async def predicate(interaction: discord.Interaction) -> bool:
        return await controlla(interaction, livello)

    return app_commands.check(predicate)


def autocomplete_protetto(livello: Livello):
    """
    Decorator per un autocomplete (funzione o metodo di un cog):
    `(interaction, current)` o `(self, interaction, current)`. Chi non
    ha il livello riceve `[]`, mai un errore.
    """

    def decorator(funzione):
        @functools.wraps(funzione)
        async def avvolta(*args, **kwargs):
            interaction = next((a for a in args if isinstance(a, discord.Interaction)), None)
            if interaction is None or not await puo_usare(interaction, livello):
                return []
            return await funzione(*args, **kwargs)

        return avvolta

    return decorator


class GruppoYokai(app_commands.Group):
    """
    Gruppo con controllo di accesso. Un sotto-gruppo (senza `livello`)
    passa il controllo al padre: discord.py guarda solo il genitore
    diretto, quindi senza questa catena un sotto-gruppo resterebbe aperto.
    """

    def __init__(self, *, livello: Livello | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.livello = livello

    def _livello_effettivo(self) -> Livello | None:
        gruppo = self
        while gruppo is not None:
            livello = getattr(gruppo, "livello", None)
            if livello is not None:
                return livello
            gruppo = gruppo.parent
        return None

    def add_command(self, command, /, *, override: bool = False) -> None:
        """
        Sotto un gruppo protetto un sotto-gruppo deve essere un
        GruppoYokai: un `Group` semplice non controlla niente e i suoi
        comandi passerebbero a chiunque.
        """
        if (
            isinstance(command, app_commands.Group)
            and not isinstance(command, GruppoYokai)
            and self._livello_effettivo() is not None
        ):
            raise TypeError(
                f"'{command.name}' è un Group semplice sotto un gruppo protetto "
                f"('{self.name}'): usa GruppoYokai, altrimenti il controllo di "
                f"accesso non si applica ai suoi comandi."
            )
        super().add_command(command, override=override)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if self.parent is not None and not await self.parent.interaction_check(interaction):
            return False
        if self.livello is not None:
            return await controlla(interaction, self.livello)
        return True

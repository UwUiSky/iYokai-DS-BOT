"""
core/premium.py
=================
Sistema Premium — PREDISPOSTO ma inizialmente disattivato per tutti.

Come funziona in breve
------------------------
1. Ogni modulo (ogni cog) si REGISTRA qui con un nome univoco tramite
   `PremiumModule`, dichiarando se è "premium_capable" (cioè: può
   diventare a pagamento in futuro) — quasi tutti lo sono.

2. Ogni modulo parte con `is_premium_active = False`. Questo significa
   che OGGI, con la configurazione di default, tutti i comandi
   funzionano gratis per chiunque, ESATTAMENTE come richiesto.

3. Il giorno in cui vorrai monetizzare, tu (solo tu, OWNER_ID) userai
   il comando /owner premium per accendere la flag di un modulo
   specifico. Da quel momento, quel modulo richiede una delle
   condizioni di sblocco (vedi guild_has_premium_access più sotto)
   per TUTTI i server tranne quelli in whitelist.

4. Ogni comando che appartiene a un modulo premium-capable si marca
   con il decorator @requires_module("nome_modulo"). Il decorator fa
   tutto il lavoro di controllo, il comando in sé non deve sapere
   nulla di premium/free — così non c'è logica sparsa e duplicata.

Nessuna parte di questo file, da sola, fa pagare qualcuno. Serve solo
a predisporre l'interruttore, che oggi resta spento ovunque.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.bot_stats import error_counter

logger = logging.getLogger("iyokai.premium")


class UnlockMethod(str, Enum):
    """
    I modi in cui un server può sbloccare un modulo premium quando
    la flag globale di quel modulo è accesa.
    Vedi la conversazione di progetto per i dettagli di ciascuno:
    tutti restano INATTIVI finché non li implementiamo per davvero
    (oggi c'è solo lo scheletro, non la logica di pagamento).
    """
    YEARLY_PAYMENT = "yearly_payment"      # 1€/anno per modulo
    COIN_PAYMENT = "coin_payment"           # 1.000.000 coin server
    NITRO_BOOST = "nitro_boost"             # boost sul server principale
    WHITELIST = "whitelist"                 # server ID inserito a mano da te


@dataclass
class PremiumModule:
    """
    Rappresenta un modulo registrabile come premium.
    Un cog che vuole poter diventare premium in futuro crea UNA
    istanza di questa classe e la passa a `registry.register(...)`
    nel proprio `setup()`. Vedi cogs/moderation/__init__.py come
    esempio concreto.
    """
    name: str                    # identificatore univoco, es. "spam_trap"
    display_name: str            # nome leggibile, es. "Spam Trap"
    description: str             # una riga, mostrata nel pannello owner
    premium_capable: bool = True # False solo per i moduli SEMPRE gratis
                                  # (core, setup, dashboard — vedi schema)
    is_premium_active: bool = False  # <-- LO STATO ATTUALE. Parte spento.


class PremiumRegistry:
    """
    Tiene traccia di tutti i moduli registrati e del loro stato.
    Un'unica istanza condivisa da tutto il bot (vedi `registry` in
    fondo al file).
    """

    def __init__(self) -> None:
        self._modules: dict[str, PremiumModule] = {}

    def register(self, module: PremiumModule) -> None:
        """
        Chiamato dai cog al momento del caricamento per dichiararsi.

        Se un nome è già registrato con una dichiarazione DIVERSA
        (display_name, description o premium_capable diversi), è un
        errore di programmazione vero (due cog diversi con lo stesso
        identificatore) e va risolto subito — solleva un'eccezione.

        Se invece è già registrato con la STESSA dichiarazione, non
        solleva: è il caso di /owner cog-reload, che richiama
        setup() (e quindi register()) sullo stesso cog una seconda
        volta — trovato con un test reale, non ipotizzato: prima di
        questa correzione, ricaricare QUALUNQUE cog con un modulo
        premium falliva sempre con ValueError, perché register() non
        distingueva "stesso modulo ridichiarato" da "due moduli
        diversi in conflitto". Non sovrascrivere l'entry esistente è
        la parte importante: preserva is_premium_active così com'è,
        un reload non deve resettare lo stato premium a False.
        """
        esistente = self._modules.get(module.name)
        if esistente is None:
            self._modules[module.name] = module
            return

        stessa_dichiarazione = (
            esistente.display_name == module.display_name
            and esistente.description == module.description
            and esistente.premium_capable == module.premium_capable
        )
        if not stessa_dichiarazione:
            raise ValueError(
                f"Modulo premium '{module.name}' già registrato con una "
                f"dichiarazione diversa. I nomi devono essere univoci."
            )
        # Stesso nome, stessa dichiarazione: reload legittimo, non
        # tocchiamo l'entry esistente (preserva is_premium_active).

    def get(self, name: str) -> PremiumModule | None:
        return self._modules.get(name)

    def all_modules(self) -> list[PremiumModule]:
        """Usato dal pannello owner per mostrare la lista completa."""
        return sorted(self._modules.values(), key=lambda m: m.name)

    def is_module_premium(self, name: str) -> bool:
        """
        True se quel modulo, GLOBALMENTE, richiede sblocco premium
        in questo momento. Oggi restituisce sempre False per tutti,
        perché ogni PremiumModule nasce con is_premium_active=False
        e nessun comando owner l'ha ancora acceso.
        """
        module = self._modules.get(name)
        if module is None:
            # Un modulo non registrato non è mai premium: fallisce
            # in modo permissivo, non bloccante. Meglio un bug
            # "tutto gratis per errore" che "tutto bloccato per errore".
            return False
        return module.is_premium_active

    def set_module_premium(self, name: str, active: bool) -> None:
        """
        Accende/spegne la flag premium di un modulo. Chiamato SOLO
        dal comando owner (/owner premium), mai da un cog normale.
        La persistenza su database (così lo stato sopravvive a un
        riavvio) è responsabilità di chi chiama questo metodo: vedi
        il TODO nel cog owner.
        """
        module = self._modules.get(name)
        if module is None:
            raise ValueError(f"Modulo '{name}' non registrato.")
        if not module.premium_capable:
            raise ValueError(
                f"Il modulo '{name}' è marcato come sempre-gratuito "
                f"e non può diventare premium."
            )
        module.is_premium_active = active


# Istanza unica, condivisa da tutto il progetto.
registry = PremiumRegistry()


async def guild_has_premium_access(guild_id: int, module_name: str) -> bool:
    """
    Verifica se UN SERVER SPECIFICO ha diritto ad usare un modulo
    che è (globalmente) premium.

    Due meccanismi di sblocco attivi oggi:
    - whitelist manuale (owner del bot, permanente)
    - premium acquistato dal server stesso via cassa (SPEC.md
      §15.15, core.premium_purchase_service/guild_premium_repo) —
      sblocca TUTTI i moduli premium per la durata acquistata
      (`premium_until`), non un modulo specifico: comprare "un mese
      di bot premium" è tutto o niente, non un acquisto per modulo

    TODO quando si implementeranno gli altri metodi di sblocco:
    - NITRO_BOOST: controllo su member.premium_since nel server
      principale, per l'owner/admin del server richiedente
    - YEARLY_PAYMENT: query alla tabella subscriptions
    """
    from core.database import db  # import locale per evitare cicli
    from core.repositories.guild_premium_repo import guild_premium_repo

    if await db.is_guild_whitelisted(guild_id):
        return True

    from datetime import datetime, timezone

    stato = await guild_premium_repo.get_status(guild_id)
    return stato.is_active(datetime.now(timezone.utc))


class PremiumCheckFailure(app_commands.CheckFailure):
    """Classe base per gli errori sollevati da requires_module()."""


class ModuleNotUnlockedError(PremiumCheckFailure):
    """
    Sollevata quando un modulo è premium globalmente e questo server
    non ha diritto ad usarlo. Porta con sé i dati per costruire il
    messaggio di risposta (vedi handle_app_command_error più sotto).
    """

    def __init__(self, module_name: str, display_name: str) -> None:
        self.module_name = module_name
        self.display_name = display_name
        super().__init__(
            f"Modulo premium '{module_name}' non sbloccato per questo server."
        )


class PremiumCheckOutsideGuildError(PremiumCheckFailure):
    """Sollevata quando un comando gated da requires_module viene
    usato fuori da un server (es. in DM)."""


def requires_module(module_name: str):
    """
    Decorator da mettere su OGNI comando che appartiene a un modulo
    potenzialmente premium. Esempio d'uso:

        @app_commands.command(name="spamtrap-setup")
        @requires_module("spam_trap")
        async def spamtrap_setup(self, interaction: discord.Interaction):
            ...

    IMPORTANTE — perché è implementato con app_commands.check() e non
    con un wrapper che sostituisce la funzione
    -------------------------------------------------------------------
    Una prima versione di questo decorator avvolgeva `func` in un
    `wrapper` definito con `functools.wraps`. Sembra innocuo, ma ha
    un difetto che si manifesta solo in certi casi e in modo
    silenzioso fino al momento del caricamento del cog: `wraps` copia
    nome, docstring, annotazioni — ma NON PUÒ copiare `__globals__`,
    che è una proprietà del modulo in cui la funzione è stata
    *definita*, non qualcosa che un decorator possa sovrascrivere.
    Se un comando usa `app_commands.Range[int, 1, UNA_COSTANTE_LOCALE]`
    definita nel file del cog, discord.py deve risolvere quel nome
    leggendo `callback.__globals__` — e con il vecchio wrapper, quei
    globals erano quelli di QUESTO file (core/premium.py), non quelli
    del cog: `UNA_COSTANTE_LOCALE` non veniva trovata e il caricamento
    del cog falliva con un NameError. È successo per davvero con
    MAX_CLEAR_AMOUNT in cogs/moderation/clear.py durante lo sviluppo
    (vedi il commit che ha introdotto questa versione del file).

    `app_commands.check()` risolve il problema alla radice: aggiunge
    un predicato alla lista dei controlli del comando SENZA MAI
    creare una nuova funzione al posto di quella originale. Il
    callback che discord.py ispeziona resta sempre quello vero, con
    i suoi __globals__ originali.

    Cosa fa il predicato, in ordine:
    1. Se il modulo non è (oggi) marcato come premium globalmente,
       lascia passare chiunque — è il caso normale, di default.
    2. Se il modulo È premium, controlla se QUESTO server ha
       diritto ad usarlo (whitelist, o in futuro gli altri metodi).
    3. Se non ce l'ha, solleva ModuleNotUnlockedError — non risponde
       direttamente: la risposta all'utente la costruisce
       handle_app_command_error() più sotto, registrato una volta
       sola come error handler globale dell'albero comandi (vedi
       main.py). Così ogni comando gated da requires_module ottiene
       lo stesso messaggio coerente, senza duplicare la logica di
       risposta in ogni predicato.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if not registry.is_module_premium(module_name):
            return True

        if interaction.guild is None:
            raise PremiumCheckOutsideGuildError()

        has_access = await guild_has_premium_access(
            interaction.guild.id, module_name
        )
        if not has_access:
            module = registry.get(module_name)
            display = module.display_name if module else module_name
            raise ModuleNotUnlockedError(module_name, display)

        return True

    return app_commands.check(predicate)


async def handle_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """
    Error handler globale dell'albero comandi, registrato in
    main.py con `bot.tree.error(handle_app_command_error)`. Gestisce
    esplicitamente gli errori sollevati da requires_module(); tutto
    il resto viene loggato e risposto con un messaggio generico,
    invece di lasciare che l'eccezione sparisca in silenzio o stampi
    solo su stderr (comportamento di default di discord.py se non si
    registra un error handler).
    """
    error_counter.record()  # SPEC.md §17.8, usato da /owner stats

    if isinstance(error, ModuleNotUnlockedError):
        message = (
            f"**{error.display_name}** è una funzione Premium non ancora "
            f"sbloccata su questo server.\n"
            f"Contatta lo staff del server o consulta il pannello di "
            f"gestione per maggiori informazioni."
        )
    elif isinstance(error, PremiumCheckOutsideGuildError):
        message = "Questo comando è disponibile solo dentro un server."
    else:
        logger.error(
            "Errore non gestito in un comando slash: %s", error, exc_info=error
        )
        message = "Si è verificato un errore imprevisto eseguendo il comando."

    # L'interazione potrebbe essere già stata "risposta" (es. un
    # comando che ha fatto defer() prima di sollevare l'errore):
    # in quel caso va usato followup, non response, altrimenti
    # Discord rifiuta una seconda risposta diretta.
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        # L'interazione può essere scaduta nel frattempo (>3s senza
        # risposta): non c'è più nulla da fare, ma non deve
        # sollevare un'altra eccezione non gestita per questo.
        logger.warning(
            "Impossibile rispondere all'interazione dopo un errore "
            "(probabilmente scaduta)."
        )

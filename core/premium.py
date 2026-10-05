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

# DA FARE (issue #69, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §13 (Owner).
# DA FARE (issue #93, fase F10): NF-22, Pagamento vero del premium. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

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


# BUG-2: categorie ammesse per i moduli, usate da /setup per mostrare un
# menu per categoria (un solo menu con tutti i moduli supera il limite
# di 25 opzioni di Discord). register() rifiuta qualunque altro valore.
CATEGORIE_MODULI = (
    "moderation",
    "security",
    "automod",
    "logging",
    "utility",
    "tickets",
    "voice",
    "music",
    "leveling",
    "fun",
)


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
    category: str = ""           # uno di CATEGORIE_MODULI, obbligatorio
                                  # (register() rifiuta il vuoto)


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
        if module.category not in CATEGORIE_MODULI:
            raise ValueError(
                f"Modulo premium '{module.name}': categoria "
                f"{module.category!r} non valida. Ammesse: "
                f"{', '.join(CATEGORIE_MODULI)}."
            )

        esistente = self._modules.get(module.name)
        if esistente is None:
            self._modules[module.name] = module
            return

        stessa_dichiarazione = (
            esistente.display_name == module.display_name
            and esistente.description == module.description
            and esistente.premium_capable == module.premium_capable
            and esistente.category == module.category
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

    def modules_in_category(self, category: str) -> list[PremiumModule]:
        """Moduli di una categoria, ordinati per nome (usato da /setup)."""
        return [m for m in self.all_modules() if m.category == category]

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


async def reload_premium_flags_from_database() -> None:
    """
    SPEC.md §3.3 — ricarica lo stato premium di ogni modulo dalla
    tabella `premium_module_flags` all'avvio del bot.

    Perché serve: ogni `PremiumModule` nasce con
    `is_premium_active=False` in `register()` (vedi sopra), quindi
    senza questa ricarica lo stato premium impostato con
    `/owner premium-toggle` andrebbe perso ad ogni riavvio, anche se
    la riga corrispondente resta persistita in
    `premium_module_flags` (scritta da `_apply_premium_toggle` in
    `cogs/utility/owner_premium.py`).

    Va chiamato DOPO che tutti i cog hanno avuto modo di registrarsi
    (`load_all_cogs`), non durante `Database.run_migrations()`:
    `set_module_premium` solleva `ValueError` se il modulo non è
    ancora registrato — vedi `main.py.setup_hook`, subito dopo
    `load_all_cogs(self)`.
    """
    from core.database import db

    righe = await db.pool.fetch(
        "SELECT module_name, is_active FROM premium_module_flags"
    )
    for riga in righe:
        modulo = registry.get(riga["module_name"])
        if modulo is None or not modulo.premium_capable:
            # Riga storica di un modulo non (più) registrato in
            # questo avvio, o marcato sempre-gratuito nel frattempo:
            # ignorata in silenzio, mai un crash all'avvio per questo.
            continue
        registry.set_module_premium(riga["module_name"], riga["is_active"])


async def _guild_owner_boosts_main_guild(guild_id: int, bot) -> bool:
    """
    NITRO_BOOST (SPEC.md §3.1): "sul server principale" — l'owner del
    server richiedente deve avere un boost attivo (`Member.
    premium_since`) sul server principale del bot (`config.
    MAIN_GUILD_ID`, lo stesso già usato per il doppio cancello
    temporale del premium via cassa). Sblocca TUTTI i moduli premium
    per quel server (come whitelist), non uno specifico — a
    differenza degli abbonamenti mensili/annuali per modulo (vedi
    module_subscription_repo). Richiede `bot` per leggere i due
    server e il membro: senza un bot connesso (es. un worker che non
    lo passa) questo metodo semplicemente non si applica, non
    solleva — le altre condizioni di sblocco restano valide comunque.
    """
    if bot is None:
        return False

    guild = bot.get_guild(guild_id)
    if guild is None or guild.owner_id is None:
        return False

    main_guild = bot.get_guild(config.MAIN_GUILD_ID)
    if main_guild is None:
        return False

    member = main_guild.get_member(guild.owner_id)
    if member is None:
        return False

    return member.premium_since is not None


async def guild_has_premium_access(
    guild_id: int, module_name: str, bot=None
) -> bool:
    """
    Verifica se UN SERVER SPECIFICO ha diritto ad usare un modulo
    che è (globalmente) premium.

    Meccanismi di sblocco attivi oggi (SPEC.md §3.1):
    - override ALPHA (`config.PREMIUM_ALPHA_UNLOCK_ALL`, temporaneo,
      vedi il commento sul campo in core/config.py): se attivo,
      sblocca SEMPRE tutto per tutti, controllato PRIMA di ogni
      altra condizione
    - whitelist manuale (owner del bot, permanente) — sblocca tutto
    - premium acquistato dal server stesso via cassa (SPEC.md
      §15.15, core.premium_purchase_service/guild_premium_repo) —
      sblocca TUTTI i moduli premium per la durata acquistata
      (`premium_until`), non un modulo specifico
    - NITRO_BOOST: l'owner del server richiedente ha un boost attivo
      sul server principale del bot — sblocca tutto (vedi
      `_guild_owner_boosts_main_guild`), richiede `bot`
    - pagamento mensile/annuale PER MODULO (`module_subscription_
      repo`) — sblocca SOLO il modulo `module_name` richiesto, non
      gli altri: nessun gateway di pagamento reale, l'owner concede
      l'abbonamento a mano con `/owner premium-grant` dopo averlo
      incassato fuori dal bot (vedi il file del repository)
    """
    if config.PREMIUM_ALPHA_UNLOCK_ALL:
        return True

    from core.database import db  # import locale per evitare cicli
    from core.repositories.guild_premium_repo import guild_premium_repo
    from core.repositories.module_subscription_repo import module_subscription_repo

    if await db.is_guild_whitelisted(guild_id):
        return True

    from datetime import datetime, timezone

    stato = await guild_premium_repo.get_status(guild_id)
    if stato.is_active(datetime.now(timezone.utc)):
        return True

    if await _guild_owner_boosts_main_guild(guild_id, bot):
        return True

    return await module_subscription_repo.is_active(guild_id, module_name)


async def get_guild_premium_breakdown(guild_id: int, bot=None) -> dict:
    """
    SPEC.md §3.2 "Visualizza stato premium di tutti i server": a
    differenza di guild_has_premium_access (un True/False per un
    singolo modulo), qui servono TUTTI i meccanismi insieme, per
    capire perché un server ha (o non ha) accesso — usato da
    /owner premium-status-all insieme a core/premium_status_logic.py
    per la formattazione.
    """
    from datetime import datetime, timezone

    from core.database import db  # import locale per evitare cicli
    from core.repositories.guild_premium_repo import guild_premium_repo
    from core.repositories.module_subscription_repo import module_subscription_repo

    whitelisted = await db.is_guild_whitelisted(guild_id)
    boosts_main_guild = await _guild_owner_boosts_main_guild(guild_id, bot)
    cassa_status = await guild_premium_repo.get_status(guild_id)
    cassa_active = cassa_status.is_active(datetime.now(timezone.utc))
    abbonamenti = await module_subscription_repo.list_for_guild(guild_id)

    return {
        "whitelisted": whitelisted,
        "boosts_main_guild": boosts_main_guild,
        "cassa_active": cassa_active,
        "subscription_count": len(abbonamenti),
    }


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
            interaction.guild.id, module_name, bot=interaction.client
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

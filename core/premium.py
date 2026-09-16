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

from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Callable

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config


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
        Se un nome è già registrato, è un errore di programmazione
        (due cog con lo stesso identificatore) e va risolto subito,
        non ignorato in silenzio — per questo solleva un'eccezione.
        """
        if module.name in self._modules:
            raise ValueError(
                f"Modulo premium '{module.name}' già registrato. "
                f"I nomi devono essere univoci."
            )
        self._modules[module.name] = module

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

    Questa funzione oggi controlla SOLO la whitelist manuale, perché
    è l'unico meccanismo di sblocco che ha senso implementare da
    subito (i altri — pagamento, coin, boost — richiedono
    integrazioni che arriveranno più avanti, vedi UnlockMethod).

    TODO quando si implementeranno gli altri metodi di sblocco:
    - COIN_PAYMENT: query alla tabella economy per il saldo del server
    - NITRO_BOOST: controllo su member.premium_since nel server
      principale, per l'owner/admin del server richiedente
    - YEARLY_PAYMENT: query alla tabella subscriptions
    """
    from core.database import db  # import locale per evitare cicli

    is_whitelisted = await db.is_guild_whitelisted(guild_id)
    return is_whitelisted


def requires_module(module_name: str):
    """
    Decorator da mettere su OGNI comando che appartiene a un modulo
    potenzialmente premium. Esempio d'uso:

        @app_commands.command(name="spamtrap-setup")
        @requires_module("spam_trap")
        async def spamtrap_setup(self, interaction: discord.Interaction):
            ...

    Cosa fa, in ordine:
    1. Se il modulo non è (oggi) marcato come premium globalmente,
       lascia passare chiunque — è il caso normale, di default.
    2. Se il modulo È premium, controlla se QUESTO server ha
       diritto ad usarlo (whitelist, o in futuro gli altri metodi).
    3. Se non ce l'ha, risponde con un messaggio chiaro invece di
       eseguire il comando, e lo fa in modo "ephemeral" (visibile
       solo a chi ha lanciato il comando).

    Il comando stesso non contiene NESSUNA di queste logiche: le
    ignora completamente. Così il giorno in cui accendi la flag
    premium di un modulo, ogni comando di quel modulo la rispetta
    automaticamente, senza toccare il codice del comando.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            if not registry.is_module_premium(module_name):
                # Modulo attualmente gratuito per tutti: via libera.
                return await func(self, interaction, *args, **kwargs)

            if interaction.guild is None:
                # Comando premium usato fuori da un server (DM):
                # non ha senso, blocchiamo.
                await interaction.response.send_message(
                    "Questo comando è disponibile solo dentro un server.",
                    ephemeral=True,
                )
                return

            has_access = await guild_has_premium_access(
                interaction.guild.id, module_name
            )
            if not has_access:
                module = registry.get(module_name)
                display = module.display_name if module else module_name
                await interaction.response.send_message(
                    f"**{display}** è una funzione Premium non ancora "
                    f"sbloccata su questo server.\n"
                    f"Contatta lo staff del server o consulta il "
                    f"pannello di gestione per maggiori informazioni.",
                    ephemeral=True,
                )
                return

            return await func(self, interaction, *args, **kwargs)

        return wrapper
    return decorator

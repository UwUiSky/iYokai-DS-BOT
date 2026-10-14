"""
cogs/ai/_comune.py
==================
Pezzi comuni ai cog dell'AI: sotto-gruppo `/utility ai`, modulo premium
"ai", richiesta allo snodo con la risposta locale già pronta, testi divisi
per i limiti di Discord.
Funzioni coperte: SPEC §25 (NF-24)
"""

from __future__ import annotations

import discord
from discord import app_commands

from core.ai_servizio import AINonDisponibile, RichiestaAI, RispostaAI, servizio_ai
from core.ai_testi_logic import LINGUE
from core.premium import PremiumModule, registry

MODULO_AI = "ai"
SOTTO_AI = ("ai", "Funzioni con l'intelligenza artificiale")
NESSUNA_MENZIONE = discord.AllowedMentions.none()


def registra_modulo_ai() -> None:
    """Il modulo AI, che l'owner può rendere premium (D13): stessa dichiarazione da ogni cog."""
    registry.register(
        PremiumModule(
            name=MODULO_AI,
            display_name="Intelligenza artificiale",
            category="utility",
            description="Assistente, riassunti, traduzioni, immagini, personaggi e aiuto allo staff con l'AI.",
            premium_capable=True,
        )
    )


def richiesta_da(interaction: discord.Interaction, funzione: str, tipo: str, testo: str, **kw) -> RichiestaAI:
    return RichiestaAI(
        user_id=interaction.user.id, funzione=funzione, tipo=tipo, testo=testo,
        guild_id=interaction.guild_id, channel_id=interaction.channel_id, **kw,
    )


async def chiedi(richiesta: RichiestaAI) -> tuple[RispostaAI | None, str | None]:
    """(risposta, None) oppure (None, testo locale da mostrare): nessuna funzione resta muta."""
    try:
        return await servizio_ai().richiedi(richiesta), None
    except AINonDisponibile as exc:
        return None, exc.testo


def taglia(testo: str, limite: int = 4000) -> str:
    return testo if len(testo) <= limite else testo[: limite - 1] + "…"


def embed_risposta(titolo: str, testo: str, *, colore: discord.Color | None = None, da_cache: bool = False) -> discord.Embed:
    embed = discord.Embed(title=taglia(titolo, 256), description=taglia(testo), color=colore or discord.Color.blurple())
    embed.set_footer(text="Risposta salvata" if da_cache else "Scritto dall'AI: controlla prima di usarlo")
    return embed


async def testo_canale(canale, limite: int, *, autore_id: int | None = None, max_caratteri: int = 12000) -> str:
    """Gli ultimi messaggi di un canale come testo (dal più vecchio), senza bot; solo di `autore_id` se dato."""
    righe: list[str] = []
    totale = 0
    async for m in canale.history(limit=limite):
        if m.author.bot or not m.content:
            continue
        if autore_id is not None and m.author.id != autore_id:
            continue
        riga = m.content if autore_id is not None else f"{m.author.display_name}: {m.content}"
        totale += len(riga)
        if totale > max_caratteri:
            break
        righe.append(riga)
    return "\n".join(reversed(righe))


def completa_lingue(current: str) -> list[app_commands.Choice[str]]:
    cerca = current.lower()
    return [
        app_commands.Choice(name=f"{nome} ({codice})", value=codice)
        for codice, nome in LINGUE.items() if cerca in nome or cerca in codice
    ][:25]

"""
core/admin_mentions_logic.py
================================
Ping nei testi scritti dall'admin (decisione D12): benvenuti, messaggi
fissi, messaggi programmati. I ruoli nominati nel testo vengono
avvisati solo se chi ha configurato il messaggio ha il permesso
"Menziona @everyone, @here e tutti i ruoli". `@everyone` e `@here`
non pingano mai. Funzioni semplici, provabili senza Discord.
"""

from __future__ import annotations

from typing import Iterable

import discord


def puo_pingare_ruoli(permessi: discord.Permissions | None) -> bool:
    """True se chi configura ha "Menziona tutti" (l'amministratore lo ha sempre)."""
    if permessi is None:
        return False
    return bool(permessi.mention_everyone or permessi.administrator)


def menzioni_ammesse(
    ping_ruoli: bool, utenti: Iterable[discord.abc.Snowflake] = ()
) -> discord.AllowedMentions:
    """
    Menzioni esplicite: `everyone` sempre spento; i ruoli solo se
    `ping_ruoli`; gli utenti solo quelli passati (es. chi entra).
    """
    return discord.AllowedMentions(
        everyone=False,
        roles=bool(ping_ruoli),
        users=list(utenti),
        replied_user=False,
    )


def taglia_messaggio(testo: str, limite: int = 2000) -> str:
    """Taglia un testo al limite di un messaggio Discord (ultimo carattere "…")."""
    if len(testo) <= limite:
        return testo
    return testo[: limite - 1] + "…"

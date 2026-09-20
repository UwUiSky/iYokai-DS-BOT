"""
core/eval_shell_logic.py
===========================
Logica pura di Eval/Exec/Shell (SPEC.md §17.3). Solo il troncamento
dell'output — l'esecuzione vera (exec/subprocess) vive nel cog,
perché non è testabile come funzione pura senza eseguire codice
davvero.
"""

from __future__ import annotations

DISCORD_MESSAGE_LIMIT = 2000
CODE_BLOCK_OVERHEAD = 8  # "```\n" + "\n```"


def truncate_output(text: str, max_length: int = DISCORD_MESSAGE_LIMIT - CODE_BLOCK_OVERHEAD) -> str:
    """
    Accorcia l'output se supera il limite, aggiungendo un avviso
    esplicito — un output silenziosamente tagliato a metà sembra un
    risultato completo quando non lo è, un problema soprattutto per
    l'esecuzione di codice/comandi dove capire cosa è successo per
    davvero conta.
    """
    if len(text) <= max_length:
        return text

    avviso = "\n... (output troncato)"
    spazio_utile = max_length - len(avviso)
    return text[:spazio_utile] + avviso

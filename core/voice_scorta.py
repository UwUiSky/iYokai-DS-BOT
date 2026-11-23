"""
core/voice_scorta.py
====================
La stanza vocale di scorta (VOC-014, D121): con l'opzione accesa il bot tiene sempre una stanza vuota pronta nella
categoria dei vocali temporanei, senza che nessuno entri nel generatore. La stanza di scorta ha come proprietario il
bot; chi ci entra la prende (nome, permessi, pannello) e il bot ne prepara un'altra. Rispetta il tetto della categoria
(`/admin-vocali cap`): se la categoria è piena non ne crea. Spenta di base.
Funzioni coperte: VOC-014
"""

from __future__ import annotations

SETTING_SCORTA = "voicetemp_scorta"
NOME_NEL_MODELLO = "libero"  # al posto del nome del proprietario finché nessuno la prende


async def attiva(database, guild_id: int) -> bool:
    return bool(await database.get_guild_setting(guild_id, SETTING_SCORTA, False))


async def imposta(database, guild_id: int, valore: bool, changed_by: int) -> None:
    await database.set_guild_setting(guild_id, SETTING_SCORTA, bool(valore), changed_by=changed_by)


def serve_nuova(scorte_vuote: int) -> bool:
    """Vero se non c'è nessuna stanza di scorta vuota (e quindi se ne prepara una)."""
    return scorte_vuote < 1

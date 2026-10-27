"""
core/bot_inviti.py
==================
Gli altri bot di iYokai in un server: chi c'è, chi manca, il link per invitarlo e cosa resta ridotto senza di lui
(D15, #113). Lo mostra `/admin setup attiva` (senza categoria). Nessuna chiamata a Discord: legge i client già avviati.
Funzioni coperte: SPEC §E (iYokai Mod, Music), #113
Dipende da: core/bot_roles.py, core/bot_info.py, core/music_fleet.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core import bot_info, bot_roles

MAX_LINK_MUSICA = 5  # i worker sono 5: non serve tagliare


@dataclass(frozen=True)
class StatoAltroBot:
    """`chiave`: "mod" o "musica". `mancanti`: coppie (etichetta, link d'invito)."""

    chiave: str
    presenti: int
    totale: int
    mancanti: list[tuple[str, str]] = field(default_factory=list)


async def altri_bot(principale, guild_id: int) -> list[StatoAltroBot]:
    """Mod (se configurato) e i bot musicali (se la flotta c'è), con i link per chi manca."""
    risultato: list[StatoAltroBot] = []
    mod = bot_roles.client_mod()
    if mod is not None and mod.application_id is not None:
        presente = bot_roles.server_mod(guild_id) is not None
        mancanti = [] if presente else [("iYokai Mod", bot_info.url_invito_mod(mod.application_id, guild_id))]
        risultato.append(StatoAltroBot("mod", int(presente), 1, mancanti))
    flotta = getattr(principale, "music_fleet", None)
    if flotta is not None:
        pronti = [i for i in range(1, len(flotta.worker_bots) + 1) if flotta.get_worker_bot(i).is_ready()]
        assenti = await flotta.get_missing_worker_indices(guild_id)
        mancanti = [(f"#{i}", flotta.build_invite_url(i, guild_id)) for i in sorted(assenti)]
        risultato.append(StatoAltroBot("musica", len(pronti) - len(assenti), len(pronti), mancanti))
    return risultato

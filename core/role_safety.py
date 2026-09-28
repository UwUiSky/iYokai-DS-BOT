"""
core/role_safety.py
======================
Controllo condiviso da chiamare ogni volta che il bot sta per lasciare
che un ruolo venga assegnato a qualcuno — sia in fase di
configurazione (un admin sceglie il ruolo per shop/level-roles/role
menu/verify/vocali temporanei) sia in fase di assegnazione vera e
propria (il ruolo può aver cambiato permessi nel frattempo).
Funzioni coperte: REVIEW.md SEC-4/SEC-17 (issue #10, #14, #29, #32).
"""

from __future__ import annotations

import discord

# Permessi che rendono un ruolo pericoloso da lasciar prendere a un
# utente DA SOLO (self_service=True): shop, level-roles, role menu,
# verify, ruolo piattaforma dei vocali temporanei. Un admin può
# comunque assegnare a mano un ruolo con questi permessi (self_service
# resta False in quel percorso, es. /moderation), ma non renderlo
# auto-assegnabile da chiunque.
_PERMESSI_PERICOLOSI_SELF_SERVICE = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "ban_members",
    "kick_members",
    "moderate_members",
    "manage_webhooks",
    "mention_everyone",
)


def check_role_assignable(
    guild: discord.Guild,
    role: discord.Role,
    actor: discord.Member,
    *,
    self_service: bool,
) -> str | None:
    """
    Restituisce None se il ruolo può essere assegnato, altrimenti il
    motivo del rifiuto in italiano (pronto da mostrare all'utente).

    self_service=True per un ruolo che un utente ottiene da solo senza
    passare da un moderatore (acquisto shop, level-roles automatico,
    click su un role menu, verify, ruolo piattaforma dei vocali
    temporanei). self_service=False per un'assegnazione manuale fatta
    da chi ha già i permessi di moderazione (es. /moderation
    assegna-ruolo), dove il controllo di gerarchia resta ma quello sui
    permessi pericolosi no: un moderatore autorizzato può assegnare a
    mano un ruolo "forte" a un altro membro fidato.
    """
    if role.is_default():
        return "Non puoi usare @everyone come ruolo."

    if role.managed:
        return "Questo ruolo è gestito da un'integrazione (bot, boost, ecc.) e non può essere assegnato manualmente."

    if role >= guild.me.top_role:
        return "Questo ruolo è pari o sopra il ruolo più alto del bot: il bot non può assegnarlo."

    if actor.id != guild.owner_id and role >= actor.top_role:
        return "Questo ruolo è pari o sopra il tuo ruolo più alto: non puoi usarlo qui."

    if self_service:
        permessi = role.permissions
        for nome_permesso in _PERMESSI_PERICOLOSI_SELF_SERVICE:
            if getattr(permessi, nome_permesso):
                return (
                    f"Il ruolo '{role.name}' ha il permesso '{nome_permesso}': "
                    "non può essere auto-assegnabile. Un admin può assegnarlo "
                    "a mano dagli strumenti di moderazione."
                )

    return None

"""
core/permissions.py
=====================
Logica di gerarchia dei permessi di moderazione, come funzioni PURE:
prendono in ingresso solo numeri e booleani semplici, non oggetti
discord.Member o discord.Role.

Perché è scritta così invece di prendere direttamente un discord.Member
--------------------------------------------------------------------------
Una funzione che prende `discord.Member` come parametro è testabile
solo dentro un vero bot connesso a Discord (o con mock complessi che
replicano tutta l'API interna della libreria). Una funzione che prende
`int` e `bool` si testa con `pytest` in due righe, senza nessuna
dipendenza da discord.py — infatti tests/test_permissions.py lo fa
davvero, contro valori concreti, non contro presunzioni.

Ogni cog di moderazione chiama queste funzioni passando i valori
estratti dagli oggetti Discord veri (member.top_role.position, ecc.):
la conversione "oggetto Discord -> numeri semplici" resta nel cog,
la LOGICA di decisione sta qui ed è quella verificata dai test.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModerationActor:
    """
    Rappresenta, con soli dati semplici, chi sta per eseguire
    un'azione di moderazione (il moderatore) o chi la subisce
    (il bersaglio). Stessa struttura per entrambi i ruoli.
    """
    user_id: int
    top_role_position: int   # discord.Member.top_role.position
    is_guild_owner: bool
    is_bot_itself: bool = False  # True solo per l'account del bot stesso


def can_moderate(
    actor: ModerationActor,
    target: ModerationActor,
    bot_top_role_position: int,
) -> tuple[bool, str]:
    """
    Decide se `actor` può eseguire un'azione di moderazione su
    `target`. Restituisce (True, "") se consentito, oppure
    (False, "motivo leggibile") se negato — così il cog può
    rispondere all'utente con un messaggio chiaro invece di un
    generico "non puoi farlo".

    Regole, in ordine di controllo:
    1. Nessuno può moderare se stesso.
    2. Nessuno può moderare il bot.
    3. Il proprietario del server non può MAI essere moderato da
       nessuno tranne se stesso (che comunque è già escluso al
       punto 1) — Discord stesso lo impedisce a livello di ruoli,
       ma lo controlliamo esplicitamente per un messaggio d'errore
       chiaro invece di un fallimento silenzioso dell'API.
    4. Il proprietario del server può sempre moderare chiunque
       altro (il suo top_role_position potrebbe essere @everyone,
       cioè il più basso possibile, eppure ha comunque autorità
       assoluta).
    5. Altrimenti: il ruolo più alto di `actor` deve essere
       STRETTAMENTE superiore al ruolo più alto di `target`.
       Ruoli di pari livello non possono moderarsi a vicenda
       (evita ambiguità quando due admin hanno lo stesso ruolo).
    6. Il bot deve avere un ruolo più alto del bersaglio, altrimenti
       l'azione fallirebbe comunque lato Discord: meglio dirlo
       subito con un messaggio chiaro che lasciar fallire la
       chiamata API con un errore criptico.
    """
    if actor.user_id == target.user_id:
        return False, "Non puoi eseguire questa azione su te stesso."

    if target.is_bot_itself:
        return False, "Non puoi eseguire questa azione sul bot."

    if target.is_guild_owner:
        return False, "Non puoi moderare il proprietario del server."

    if actor.is_guild_owner:
        # Il proprietario del server può sempre agire, a prescindere
        # dal suo top_role_position (che potrebbe essere basso se non
        # si è assegnato ruoli).
        pass
    elif actor.top_role_position <= target.top_role_position:
        return (
            False,
            "Non puoi moderare un utente con un ruolo pari o superiore "
            "al tuo.",
        )

    if bot_top_role_position <= target.top_role_position:
        return (
            False,
            "Il mio ruolo è troppo basso per moderare questo utente: "
            "sposta il ruolo del bot più in alto nelle impostazioni "
            "del server.",
        )

    return True, ""


def can_use_moderation_commands(
    actor_has_permission: bool,
    actor_is_guild_owner: bool,
) -> bool:
    """
    Controllo di base "può usare comandi di moderazione?", separato
    da can_moderate() perché risponde a una domanda diversa: qui non
    c'è ancora un bersaglio, è solo "questa persona ha in generale il
    permesso Discord richiesto (es. ban_members) per questa categoria
    di comando?". actor_has_permission arriva già calcolato dal cog
    leggendo interaction.user.guild_permissions.
    """
    return actor_has_permission or actor_is_guild_owner

"""
core/greetings_logic.py
==========================
Logica pura di Welcome / Goodbye / Boost messages (SPEC.md
§14.4-14.6). Sostituzione dei segnaposto in un template testuale —
nessuna dipendenza da discord.py, il chiamante (cogs/utility/
greetings.py) passa già stringhe/numeri semplici estratti dagli
oggetti Discord reali.

Segnaposto supportati: {user} (mention), {username} (nome semplice,
senza @), {server} (nome del server), {membercount} (numero attuale
di membri).

Nota sul perché {user} e {username} non entrano in conflitto tra
loro nella sostituzione: la stringa esatta "{user}" non è una
sottostringa di "{username}" (dopo "user" in "{username}" segue
"name}", non "}") — l'ordine delle sostituzioni non ha bisogno di
essere garantito in un modo particolare, verificato esplicitamente
con un test dedicato invece di assumerlo.
"""

from __future__ import annotations

DEFAULT_WELCOME_TEMPLATE = (
    "Welcome {user} to **{server}**! We're now {membercount} members strong. 🎉"
)
DEFAULT_GOODBYE_TEMPLATE = "**{username}** has left {server}. We're now {membercount} members."
DEFAULT_BOOST_TEMPLATE = (
    "🚀 {user} just boosted **{server}**! Thank you for the support!"
)


def render_template(
    template: str,
    user_mention: str,
    username: str,
    server_name: str,
    member_count: int,
) -> str:
    return (
        template.replace("{user}", user_mention)
        .replace("{username}", username)
        .replace("{server}", server_name)
        .replace("{membercount}", str(member_count))
    )


# LIM-10 (M 10.2): il messaggio finale è un messaggio normale (2000). La
# lunghezza si misura DOPO i segnaposto, con i valori peggiori di chi non
# si conosce al momento della configurazione: una menzione utente (<@ + 20
# cifre + >) e un nome utente di 32 caratteri.
MAX_MESSAGE_LENGTH = 2000
_LUNGHEZZA_MENZIONE_UTENTE = 23
_LUNGHEZZA_NOME_UTENTE = 32


def lunghezza_dopo_segnaposto(template: str, server_name: str, member_count: int) -> int:
    """Lunghezza peggiore del testo dopo la sostituzione dei segnaposto."""
    return len(
        render_template(
            template,
            user_mention="m" * _LUNGHEZZA_MENZIONE_UTENTE,
            username="u" * _LUNGHEZZA_NOME_UTENTE,
            server_name=server_name,
            member_count=member_count,
        )
    )

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

import random

from core.role_menu_logic import valida_emoji

DEFAULT_WELCOME_TEMPLATE = (
    "Welcome {user} to **{server}**! We're now {membercount} members strong. 🎉"
)
DEFAULT_GOODBYE_TEMPLATE = "**{username}** has left {server}. We're now {membercount} members."
DEFAULT_BOOST_TEMPLATE = (
    "🚀 {user} just boosted **{server}**! Thank you for the support!"
)


def _ordinale(numero: int) -> str:
    """1234 -> "1.234º" (il numero del membro, RUO-018)."""
    return f"{numero:,}".replace(",", ".") + "º"


def render_template(
    template: str,
    user_mention: str,
    username: str,
    server_name: str,
    member_count: int,
    *,
    user_id: int | None = None,
    display_name: str | None = None,
    server_id: int | None = None,
) -> str:
    """
    Sostituisce i segnaposto. `{userid}`, `{displayname}` e `{serverid}` (RUO-019..021)
    restano scritti se chi chiama non dà il dato; `{ordinal}` (RUO-018) usa il numero dei membri.
    """
    testo = (
        template.replace("{user}", user_mention)
        .replace("{username}", username)
        .replace("{server}", server_name)
        .replace("{membercount}", str(member_count))
    )
    if "{ordinal}" in testo:
        testo = testo.replace("{ordinal}", _ordinale(member_count))
    if user_id is not None:
        testo = testo.replace("{userid}", str(user_id))
    if display_name is not None:
        testo = testo.replace("{displayname}", display_name)
    if server_id is not None:
        testo = testo.replace("{serverid}", str(server_id))
    return testo


# LIM-10 (M 10.2): il messaggio finale è un messaggio normale (2000). La
# lunghezza si misura DOPO i segnaposto, con i valori peggiori di chi non
# si conosce al momento della configurazione: una menzione utente (<@ + 20
# cifre + >) e un nome utente di 32 caratteri.
MAX_MESSAGE_LENGTH = 2000
_LUNGHEZZA_MENZIONE_UTENTE = 23
_LUNGHEZZA_NOME_UTENTE = 32
_LUNGHEZZA_ID = 20


def lunghezza_dopo_segnaposto(template: str, server_name: str, member_count: int) -> int:
    """Lunghezza peggiore del testo dopo la sostituzione dei segnaposto."""
    return len(
        render_template(
            template,
            user_mention="m" * _LUNGHEZZA_MENZIONE_UTENTE,
            username="u" * _LUNGHEZZA_NOME_UTENTE,
            server_name=server_name,
            member_count=member_count,
            user_id=10**_LUNGHEZZA_ID - 1,
            display_name="d" * _LUNGHEZZA_NOME_UTENTE,
            server_id=10**_LUNGHEZZA_ID - 1,
        )
    )


# RUO-013, 017, 023, 025: DM con testo suo, varianti a caso, reazioni sul benvenuto.
MAX_VARIANTI = 10
MAX_REAZIONI = 5


def analizza_varianti(testo: str) -> tuple[list[str], str | None]:
    """Una variante per riga, senza righe vuote. Ritorna (varianti, errore)."""
    varianti = [riga.strip() for riga in testo.splitlines() if riga.strip()]
    if len(varianti) > MAX_VARIANTI:
        return [], f"Al massimo {MAX_VARIANTI} varianti: ne hai scritte {len(varianti)}."
    for riga in varianti:
        if len(riga) > MAX_MESSAGE_LENGTH:
            return [], f"Una variante supera {MAX_MESSAGE_LENGTH} caratteri."
    return varianti, None


def analizza_reazioni(testo: str) -> tuple[list[str], str | None]:
    """Emoji separate da spazi, senza doppioni. Ritorna (reazioni, errore)."""
    reazioni: list[str] = []
    for parola in testo.split():
        if not valida_emoji(parola):
            return [], f"«{parola[:30]}» non è un'emoji."
        if parola not in reazioni:
            reazioni.append(parola)
    if len(reazioni) > MAX_REAZIONI:
        return [], f"Al massimo {MAX_REAZIONI} reazioni."
    return reazioni, None


def scegli_testo(principale: str, varianti: list[str], rng: random.Random | None = None) -> str:
    """Il testo principale o una delle varianti, a caso con la stessa probabilità."""
    if not varianti:
        return principale
    return (rng or random).choice([principale, *varianti])

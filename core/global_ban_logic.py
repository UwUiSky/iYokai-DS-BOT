"""
core/global_ban_logic.py
============================
Logica pura del ban globale (SPEC.md §7.3) — nessuna dipendenza da
discord.py o dal database, solo la regola: propaga un ban da un
server all'altro SOLO SE entrambi hanno esplicitamente aderito alla
rete (opt-in reciproco), mai a un server che non ha scelto di
partecipare.

Nota di design (perché questo non è "il" ban globale via fingerprint
di SPEC.md §4.3): il fingerprint/alt-detection lì descritto risolve
un problema diverso — riconoscere che DUE ACCOUNT DIVERSI sono la
stessa persona (un alt), cosa che richiede una raccolta IP/OAuth2
"identify" fatta AL MOMENTO DEL VERIFY, prima che l'account si
comporti male (§4.2, non costruito: un account appena bannato dalla
Spam Trap non collaborerebbe certo a un flusso OAuth2 dopo il fatto,
quindi quella raccolta non potrebbe mai avvenire a ban avvenuto).
Qui invece il problema è più semplice e concretamente risolvibile
oggi: lo STESSO account Discord (stesso user id, nessuna euristica di
somiglianza) viene bannato anche negli altri server che condividono
il bot e hanno aderito alla rete — un ban dello stesso utente, non
un'inferenza su un utente diverso.
"""

from __future__ import annotations


def should_propagate_ban(
    *, source_guild_id: int, target_guild_id: int, source_opted_in: bool, target_opted_in: bool
) -> bool:
    """
    True solo se: il server sorgente (dove è scattato il ban) e il
    server target sono aderenti entrambi alla rete di ban globali, e
    non sono lo stesso server (propagare un ban su se stessi non ha
    senso — l'utente è già bannato lì).
    """
    if source_guild_id == target_guild_id:
        return False
    return source_opted_in and target_opted_in

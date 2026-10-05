"""
core/snipe_logic.py
=======================
Logica pura per Reactionsnipe (SPEC.md §14.11) e Ghost ping detection
(§14.12) — solo stringhe/int/bool qui dentro, niente discord.py.

Nota architetturale importante (stessa disciplina già applicata a
SPEC.md §8.13/§8.8 — vedi PROGRESS.md Fase 70b — e a §13.10/§13.11):
QUESTE due funzionalità sono state verificate una per una contro il
Message Content Intent, non liquidate in blocco come "famiglia
snipe = bloccata". Risultato della verifica:

- Snipe (§14.9) ed Editsnipe (§14.10) mostrano il CONTENUTO del
  messaggio cancellato/modificato — quel contenuto è vuoto sia in
  on_message sia in on_message_delete/on_message_edit senza il
  Message Content Intent (privilegio gateway, non richiesto da
  questo bot — vedi SPEC.md §8.16 per la stessa decisione già presa
  sul logging). Restano rimandati, stesso motivo di §8.16 — non
  costruibili senza quell'intent, punto verificato sulla libreria
  installata (discord.Intents.message_content.__doc__), non assunto.
- Reactionsnipe (§14.11) NON ha bisogno del contenuto del messaggio:
  on_raw_reaction_remove restituisce emoji, autore e ID messaggio,
  nient'altro serve per "chi ha rimosso quale reazione da dove".
- Ghost ping detection (§14.12) NON ha bisogno del contenuto: la
  lista dei membri menzionati (Message.mentions) arriva dal campo
  "mentions" del payload gateway, POPOLATO SEMPRE da Discord
  indipendentemente dall'intent (verificato leggendo
  Message._handle_mentions nella libreria installata: legge da un
  campo a parte, non da un parsing del contenuto). Basta quindi
  tracciare "questo messaggio menzionava qualcuno" (id autore + id
  menzionati + timestamp, ZERO contenuto) in una cache leggera, e
  controllare alla cancellazione se l'ID era tracciato.
"""

# DA FARE (issue #74, fase F6): NF-03, Snipe ed editsnipe. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations


def is_ghost_ping_candidate(
    mentioned_user_ids: list[int], mentions_everyone: bool, author_is_bot: bool
) -> bool:
    """
    Un messaggio va tracciato per il ghost ping se menziona almeno
    un utente (o @everyone/@here) e non è stato scritto da un bot
    (i messaggi automatici del bot stesso, o di altri bot, non
    contano come "ghost ping" di un membro).
    """
    if author_is_bot:
        return False
    return bool(mentioned_user_ids) or mentions_everyone

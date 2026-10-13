"""
core/role_menu_logic.py
==========================
Logica pura dei Role Menu (SPEC.md §14.1-14.3: Reaction Roles,
Button Roles, Select Menu Roles). Le tre modalità condividono lo
stesso modello dati (un "menu" con delle "opzioni", ciascuna legata
a un ruolo) e buona parte della logica — cambia solo COME l'utente
interagisce (reazione emoji, click bottone, scelta da tendina).

Nessuna dipendenza da discord.py qui: solo insiemi di ID e stringhe.
"""

# DA FARE (issue #85, fase F9): NF-14, Modalità dei reaction roles. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

# Limiti pratici per modalità — non tutti sono limiti hard dell'API
# Discord (i bottoni sì: 25 per messaggio, 5 per riga; il select
# menu sì: 25 opzioni), la reazione è un limite di usabilità nostro
# (oltre una ventina di reazioni su un messaggio diventa scomodo da
# leggere per un utente, anche se Discord tecnicamente non lo vieta).
MODE_MAX_OPTIONS: dict[str, int] = {
    "reaction": 20,
    "button": 25,
    "select": 25,
}


def can_add_option(current_option_count: int, mode: str) -> bool:
    limite = MODE_MAX_OPTIONS.get(mode, 25)
    return current_option_count < limite


def compute_toggle_action(member_has_role: bool) -> Literal["add", "remove"]:
    """
    Per le modalità bottone e reazione (con toggle attivo): se il
    membro ha già il ruolo, l'interazione lo rimuove; altrimenti lo
    assegna. Logica identica per entrambe le modalità, isolata qui
    una volta sola.
    """
    return "remove" if member_has_role else "add"


def compute_select_sync(
    current_member_role_ids: set[int],
    menu_role_ids: set[int],
    selected_role_ids: set[int],
) -> tuple[set[int], set[int]]:
    """
    Per la modalità select: l'utente sceglie da una tendina quali
    ruoli (tra quelli del menu) vuole avere ORA — non è un toggle
    incrementale come bottone/reazione, è uno stato finale dichiarato
    in un colpo solo. Calcola quali ruoli aggiungere e quali togliere
    per portare il membro esattamente a quello stato, SENZA toccare
    ruoli che il membro ha ma che non appartengono a questo menu
    (un select di "colori preferiti" non deve mai rimuovere un ruolo
    di moderazione solo perché non è tra le opzioni scelte).

    Restituisce (da_aggiungere, da_rimuovere).
    """
    da_aggiungere = selected_role_ids - current_member_role_ids
    da_rimuovere = (menu_role_ids & current_member_role_ids) - selected_role_ids
    return da_aggiungere, da_rimuovere


# LIM-17 (M 10.7): l'emoji di un'opzione si controlla quando l'admin la scrive,
# non quando Discord la rifiuta. Personalizzata: <:nome:id> o <a:nome:id>.
_EMOJI_PERSONALIZZATA = re.compile(r"^<a?:[A-Za-z0-9_]{2,32}:(\d{15,22})>$")
_EMOJI_TASTO = re.compile("^[0-9#*]\ufe0f?\u20e3$")
MAX_LUNGHEZZA_EMOJI_UNICODE = 20


def id_emoji_personalizzata(testo: str) -> int | None:
    """L'ID di un'emoji personalizzata scritta come <:nome:id>, altrimenti None."""
    trovata = _EMOJI_PERSONALIZZATA.match(testo)
    return int(trovata.group(1)) if trovata else None


def valida_emoji(testo: str) -> bool:
    """
    True se `testo` è UNA emoji: personalizzata ben formata, un tasto
    (1️⃣) o una sequenza unicode di simboli (bandiere, tonalità, ZWJ).
    Lettere, cifre, spazi e testo libero sono rifiutati. Se l'emoji
    personalizzata esiste davvero lo dice poi Discord / la cache del bot.
    """
    if not testo or len(testo) > MAX_LUNGHEZZA_EMOJI_UNICODE and not testo.startswith("<"):
        return False
    if testo.startswith("<"):
        return _EMOJI_PERSONALIZZATA.match(testo) is not None
    if _EMOJI_TASTO.match(testo):
        return True
    for carattere in testo:
        categoria = unicodedata.category(carattere)
        if ord(carattere) < 128 or not (categoria[0] in ("S", "M") or categoria == "Cf"):
            return False
    return unicodedata.category(testo[0])[0] == "S"


# ----------------------------------------------------------------------
# NF-14 (M 10.8): comportamento di un menu (modello: Carl-bot)
# ----------------------------------------------------------------------
COMPORTAMENTI: dict[str, str] = {
    "normal": "normale: si prende e (con toggle) si toglie",
    "unique": "unique: un solo ruolo alla volta del menu",
    "verify": "verify: si dà e non si toglie",
    "drop": "drop: si toglie soltanto",
    "reversed": "reversed: la reazione toglie il ruolo, toglierla lo dà",
    "binding": "binding: una scelta per sempre",
    "temp": "temp: il ruolo dura un tempo, poi si toglie da solo",
    "lock": "lock: menu chiuso, nessuno cambia ruoli",
}
COMPORTAMENTO_DI_BASE = "normal"
# Quali comportamenti hanno senso in quale modalità (reversed e drop sono cose da
# reazione/bottone: una tendina descrive lo stato finale che si vuole avere).
_NON_AMMESSI: dict[str, set[str]] = {
    "reaction": set(),
    "button": {"reversed"},
    "select": {"reversed", "drop"},
}
MAX_TEMP_SECONDI = 30 * 24 * 3600
MAX_RUOLI_ACCESSO = 20  # per elenco (ammessi o esclusi)


def comportamento_ammesso(mode: str, comportamento: str) -> bool:
    return comportamento in COMPORTAMENTI and comportamento not in _NON_AMMESSI.get(mode, set())


@dataclass(frozen=True)
class Decisione:
    aggiungi: tuple[int, ...] = ()
    togli: tuple[int, ...] = ()
    temporaneo_secondi: int | None = None  # per i ruoli appena aggiunti
    rifiuto: str | None = None  # testo per l'utente; se c'è, non si tocca nulla


def membro_ammesso(ruoli_ammessi: list[int], ruoli_esclusi: list[int], ruoli_membro: set[int]) -> str | None:
    """None se il membro può usare il menu, altrimenti il motivo. L'esclusione vince sempre."""
    if ruoli_esclusi and ruoli_membro & set(ruoli_esclusi):
        return "Hai un ruolo che non può usare questo menu."
    if ruoli_ammessi and not ruoli_membro & set(ruoli_ammessi):
        return "Questo menu è riservato a chi ha certi ruoli."
    return None


def decidi_azione(
    comportamento: str,
    *,
    attiva: bool,
    via_reazione: bool,
    ruolo_id: int,
    ruoli_menu: set[int],
    ruoli_membro: set[int],
    toggle: bool = True,
    temp_secondi: int | None = None,
) -> Decisione:
    """
    Cosa fare quando un membro usa l'opzione `ruolo_id` di un menu.
    `attiva`: clic su bottone o reazione messa; False = reazione tolta.
    `via_reazione`: la reazione rimessa su un ruolo già posseduto non toglie nulla,
    il bottone cliccato di nuovo sì (se `toggle`).
    """
    ha = ruolo_id in ruoli_membro
    if comportamento == "lock":
        return Decisione(rifiuto="Questo menu è chiuso: ora i ruoli non si possono cambiare.")

    def rimuovi_se_ammesso() -> Decisione:
        if ha and toggle:
            return Decisione(togli=(ruolo_id,))
        if ha:
            return Decisione(rifiuto="Hai già questo ruolo: da questo menu non si può togliere.")
        return Decisione()

    if comportamento == "reversed":
        # solo reazioni: messa = togli, tolta = dai
        if attiva:
            return Decisione(togli=(ruolo_id,)) if ha else Decisione()
        return Decisione() if ha else Decisione(aggiungi=(ruolo_id,))

    if not attiva:  # reazione tolta
        if comportamento in ("verify", "drop", "binding"):
            return Decisione()
        return Decisione(togli=(ruolo_id,)) if ha and toggle else Decisione()

    if comportamento == "drop":
        if ha:
            return Decisione(togli=(ruolo_id,))
        return Decisione(rifiuto="Non hai questo ruolo.")
    if comportamento == "verify":
        if ha:
            return Decisione() if via_reazione else Decisione(rifiuto="Hai già questo ruolo: da questo menu non si toglie.")
        return Decisione(aggiungi=(ruolo_id,))
    if comportamento == "binding":
        if ha or ruoli_membro & ruoli_menu:
            return Decisione(rifiuto="La tua scelta in questo menu è definitiva: non si può cambiare.")
        return Decisione(aggiungi=(ruolo_id,))
    if comportamento == "unique":
        if ha:
            return Decisione() if via_reazione else rimuovi_se_ammesso()
        altri = tuple(sorted((ruoli_menu & ruoli_membro) - {ruolo_id}))
        return Decisione(aggiungi=(ruolo_id,), togli=altri)
    if comportamento == "temp":
        if ha:
            return Decisione() if via_reazione else rimuovi_se_ammesso()
        return Decisione(aggiungi=(ruolo_id,), temporaneo_secondi=temp_secondi)
    # normal
    if ha:
        return Decisione() if via_reazione else rimuovi_se_ammesso()
    return Decisione(aggiungi=(ruolo_id,))


def decidi_selezione(
    comportamento: str,
    *,
    ruoli_menu: set[int],
    ruoli_membro: set[int],
    scelti: set[int],
    temp_secondi: int | None = None,
) -> Decisione:
    """Come `decidi_azione` ma per la tendina: l'utente dichiara lo stato che vuole avere."""
    if comportamento == "lock":
        return Decisione(rifiuto="Questo menu è chiuso: ora i ruoli non si possono cambiare.")
    da_aggiungere, da_togliere = compute_select_sync(ruoli_membro, ruoli_menu, scelti)
    if comportamento == "binding":
        if ruoli_membro & ruoli_menu:
            return Decisione(rifiuto="La tua scelta in questo menu è definitiva: non si può cambiare.")
        return Decisione(aggiungi=tuple(sorted(da_aggiungere)))
    if comportamento == "verify":
        return Decisione(aggiungi=tuple(sorted(da_aggiungere)))
    if comportamento == "unique":
        # un solo ruolo: l'ultimo scelto vince, gli altri del menu si tolgono
        if len(scelti) > 1:
            return Decisione(rifiuto="Da questo menu puoi avere un ruolo solo.")
        return Decisione(aggiungi=tuple(sorted(da_aggiungere)), togli=tuple(sorted(da_togliere)))
    if comportamento == "temp":
        return Decisione(
            aggiungi=tuple(sorted(da_aggiungere)), togli=tuple(sorted(da_togliere)), temporaneo_secondi=temp_secondi
        )
    return Decisione(aggiungi=tuple(sorted(da_aggiungere)), togli=tuple(sorted(da_togliere)))

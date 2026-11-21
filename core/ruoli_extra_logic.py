"""
core/ruoli_extra_logic.py
=========================
Logica pura delle funzioni in più dei ruoli: ruolo personale (nome pulito, colore, pausa, tetti),
più ruoli da una opzione, gruppo di menu collegati, scelta a caso delle immagini del benvenuto.
Nessuna dipendenza da discord.py.
Funzioni coperte: SPEC RUO-012, RUO-045, RUO-046, RUO-069, RUO-083
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import replace
from datetime import datetime, timedelta

from core.role_menu_logic import Decisione

TETTO_RUOLI_PERSONALI = 250  # per server (anche il tetto di ruoli di Discord)
MAX_NOME_RUOLO = 100
PAUSA_MODIFICHE_SECONDI = 300  # una modifica ogni 5 minuti per persona
MAX_RUOLI_PER_OPZIONE = 5  # il ruolo dell'opzione più i ruoli in più
MAX_MENU_PER_GRUPPO = 10
MAX_NOME_GRUPPO = 40
MAX_IMMAGINI_BENVENUTO = 10

_MENZIONE = re.compile(r"<[@#!&:][^>]*>")
_COLORE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def pulisci_nome_ruolo(testo: str) -> str | None:
    """Nome sicuro per un ruolo: niente menzioni, @everyone, @here, invisibili o caratteri di controllo. None se resta vuoto."""
    testo = unicodedata.normalize("NFKC", testo or "")
    testo = _MENZIONE.sub(" ", testo)
    testo = "".join(
        c if not unicodedata.category(c).startswith(("C", "Z")) or c == " " else " " for c in testo
    )
    testo = testo.replace("@", "").replace("`", "")
    testo = re.sub(r"\s+", " ", testo).strip()[:MAX_NOME_RUOLO].strip()
    return testo or None


def valida_colore(testo: str) -> int | None:
    """«#C24A3A», «C24A3A» o «#c43» -> numero del colore; None se non è un colore."""
    trovato = _COLORE.match((testo or "").strip())
    if not trovato:
        return None
    esa = trovato.group(1)
    if len(esa) == 3:
        esa = "".join(c * 2 for c in esa)
    return int(esa, 16)


def secondi_di_pausa(ultima_modifica: datetime | None, ora: datetime, pausa: int = PAUSA_MODIFICHE_SECONDI) -> int:
    """Quanti secondi mancano alla prossima modifica consentita (0 = si può)."""
    if ultima_modifica is None:
        return 0
    return max(int((ultima_modifica + timedelta(seconds=pausa) - ora).total_seconds()), 0)


def puo_creare_ruolo_personale(ruoli_personali_nel_server: int, ruoli_del_server: int) -> str | None:
    """Motivo del rifiuto, o None. Tetto 250 ruoli personali e mai oltre il tetto dei ruoli di Discord."""
    if ruoli_personali_nel_server >= TETTO_RUOLI_PERSONALI:
        return "Il server ha già il massimo di ruoli personali."
    if ruoli_del_server >= TETTO_RUOLI_PERSONALI:
        return "Il server ha raggiunto il massimo di ruoli di Discord."
    return None


def posizione_sotto_il_bot(posizione_ruolo_bot: int) -> int:
    """Subito sotto il ruolo più alto del bot (mai sotto il posto 1)."""
    return max(posizione_ruolo_bot - 1, 1)


# ---------------------------------------------------------------- più ruoli da una opzione (RUO-083)

def puo_aggiungere_extra(ruoli_in_extra: int, e_gia_presente: bool) -> str | None:
    if not e_gia_presente and 1 + ruoli_in_extra >= MAX_RUOLI_PER_OPZIONE:
        return f"Una opzione dà al massimo {MAX_RUOLI_PER_OPZIONE} ruoli, compreso il suo."
    return None


def _espandi(ruoli: tuple[int, ...], extra: dict[int, tuple[int, ...]]) -> tuple[int, ...]:
    fuori: list[int] = []
    for rid in ruoli:
        for r in (rid, *extra.get(rid, ())):
            if r not in fuori:
                fuori.append(r)
    return tuple(fuori)


def applica_extra_e_gruppo(
    decisione: Decisione,
    *,
    extra: dict[int, tuple[int, ...]],
    ruoli_gruppo: frozenset[int] = frozenset(),
    ruoli_membro: set[int],
) -> Decisione:
    """
    RUO-083: ogni ruolo dato o tolto porta con sé i suoi ruoli in più.
    RUO-069: se il menu è in un gruppo, chi prende un ruolo perde quelli che ha degli altri menu del gruppo
    (`ruoli_gruppo` = tutti i ruoli dei menu del gruppo, compresi i loro ruoli in più).
    Un rifiuto già presente resta com'è.
    """
    if decisione.rifiuto is not None:
        return decisione
    if ruoli_gruppo and len(decisione.aggiungi) > 1:
        return replace(decisione, rifiuto="I menu di questo gruppo danno un solo ruolo alla volta.")
    aggiungi = _espandi(decisione.aggiungi, extra)
    togli = list(_espandi(decisione.togli, extra))
    if aggiungi and ruoli_gruppo:
        for rid in sorted(ruoli_gruppo & ruoli_membro):
            if rid not in aggiungi and rid not in togli:
                togli.append(rid)
    togli = [r for r in togli if r not in aggiungi]
    return replace(decisione, aggiungi=aggiungi, togli=tuple(togli))


def pulisci_nome_gruppo(testo: str) -> str | None:
    pulito = pulisci_nome_ruolo(testo)
    return pulito[:MAX_NOME_GRUPPO].strip().lower() if pulito else None


# ---------------------------------------------------------------- immagini del benvenuto (RUO-012)

def scegli_immagine(ids: list[int], caso: random.Random | None = None) -> int | None:
    """Una immagine a caso tra quelle salvate; None se non ce ne sono."""
    if not ids:
        return None
    return (caso or random).choice(ids)

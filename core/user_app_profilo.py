"""
core/user_app_profilo.py
========================
Profilo globale di iYokai App (SPEC §B.6): livello (dalla somma degli XP di tutti i server), clan, medaglie
(i badge del catalogo) e la rank card. Gli altri lo vedono solo se la persona lo ha acceso
(`/impostazioni profilo`); per sé lo vede sempre.
Funzioni coperte: SPEC §B.6 (NF-36, #107)
Dipende da: core/repositories/user_app_repo.py, core/profile_logic.py, core/rank_card_image.py
"""

from __future__ import annotations

from dataclasses import dataclass

from core.leveling_logic import level_for_xp
from core.profile_logic import CATALOGO, TIPO_BADGE, oggetto
from core.rank_card_image import TEMA_DI_BASE, DatiProfilo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.user_app_repo import user_app_repo

MAX_CLAN_MOSTRATI = 5
COLORE_DI_BASE = "#5865F2"


@dataclass(frozen=True)
class ProfiloGlobale:
    livello: int
    xp_totale: int
    server: int
    monete: int
    clan: tuple[str, ...]  # «[TAG] Nome»
    medaglie: tuple[str, ...]  # id degli oggetti posseduti
    colore: str = COLORE_DI_BASE
    tema: str = TEMA_DI_BASE


async def profilo_globale(user_id: int) -> ProfiloGlobale:
    somme = await user_app_repo.somme_globali(user_id)
    clan = await user_app_repo.clan_dell_utente(user_id, MAX_CLAN_MOSTRATI)
    medaglie = await user_app_repo.medaglie(user_id)
    colore, tema = await leveling_repo.get_rank_card_prefs(user_id)
    return ProfiloGlobale(
        livello=level_for_xp(somme.xp_totale), xp_totale=somme.xp_totale, server=somme.server, monete=somme.monete,
        clan=tuple(f"[{c['tag']}] {c['name']}" for c in clan), medaglie=tuple(medaglie),
        colore=colore or COLORE_DI_BASE, tema=tema or TEMA_DI_BASE,
    )


def testo_medaglie(ids: tuple[str, ...]) -> str:
    """Le emoji dei badge posseduti (gli sfondi si contano a parte)."""
    return " ".join(o.emoji for i in ids if (o := oggetto(i)) and o.tipo == TIPO_BADGE and o.emoji)


def dati_rank_card(nome: str, p: ProfiloGlobale) -> DatiProfilo:
    return DatiProfilo(
        nome=nome, presentazione=None, livello=p.livello, xp_totale=p.xp_totale, posizione=None, coin=p.monete,
        collezione=len(p.medaglie), collezione_totale=len(CATALOGO), colore=p.colore, tema=p.tema,
    )

"""
core/smash_logic.py
===================
«Smash or pass» (#131, D70, B11, FUN-021): un personaggio a caso dai più amati di AniList, sempre e solo
maggiorenne (ogni numero scritto nell'età dev'essere almeno 18; se manca l'età il personaggio non esce), mostrato come
link alla pagina di AniList (nessuna immagine ospitata da noi). Voti settimanali: uno a testa per personaggio.
Funzioni coperte: SPEC §16 (FUN-021)
Dipende da: core/safe_http.py, core/repositories/cache_esterna_repo.py, core/repositories/smash_repo.py
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import datetime

ANILIST = "https://graphql.anilist.co"
PAGINE = 20  # i primi 1000 personaggi per preferiti
PER_PAGINA = 50
SECONDI_CACHE = 24 * 3600
_QUERY = (
    "query($p:Int){Page(page:$p,perPage:" + str(PER_PAGINA) + "){characters(sort:FAVOURITES_DESC)"
    "{id age name{full} media(perPage:1){nodes{title{romaji english}}}}}}"
)


@dataclass(frozen=True)
class Personaggio:
    id: int
    nome: str
    opera: str

    @property
    def pagina(self) -> str:
        return f"https://anilist.co/character/{self.id}"


def eta_adulta(eta: object) -> bool:
    """Vero solo se nell'età ci sono numeri e sono tutti almeno 18 («17-23» e «14» non passano)."""
    numeri = [int(n) for n in re.findall(r"\d+", eta if isinstance(eta, str) else "")]
    return bool(numeri) and min(numeri) >= 18


def interpreta_pagina(testo: str | None) -> list[Personaggio]:
    try:
        righe = json.loads(testo or "")["data"]["Page"]["characters"]
    except (ValueError, KeyError, TypeError):
        return []
    trovati = []
    for r in righe if isinstance(righe, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("id"), int) or not eta_adulta(r.get("age")):
            continue
        nome = ((r.get("name") or {}).get("full") or "").strip() if isinstance(r.get("name"), dict) else ""
        nodi = (r.get("media") or {}).get("nodes") if isinstance(r.get("media"), dict) else None
        titoli = nodi[0].get("title") if isinstance(nodi, list) and nodi and isinstance(nodi[0], dict) else None
        opera = ((titoli or {}).get("english") or (titoli or {}).get("romaji") or "").strip() if isinstance(titoli, dict) else ""
        if nome:
            trovati.append(Personaggio(r["id"], nome[:100], opera[:100]))
    return trovati


def settimana(adesso: datetime) -> str:
    anno, numero, _ = adesso.isocalendar()
    return f"{anno}-W{numero:02d}"


async def _scarica(pagina: int) -> str | None:
    from core.safe_http import safe_richiesta

    return await safe_richiesta(
        ANILIST, metodo="POST", headers={"Content-Type": "application/json", "Accept": "application/json"},
        json_corpo={"query": _QUERY, "variables": {"p": pagina}}, max_bytes=300_000,
    )


async def personaggio_a_caso(cache, rng: random.Random | None = None, scarica=_scarica) -> Personaggio | None:
    """Un personaggio adulto da una pagina scelta a caso (la pagina sta in cache 24 ore). None se la fonte non risponde."""
    rng = rng or random.Random()
    pagina = rng.randint(1, PAGINE)
    chiave = f"smash:pagina:{pagina}"
    salvato = await cache.leggi(chiave)
    if salvato is not None:
        elenco = [Personaggio(**p) for p in salvato.get("personaggi", [])]
    else:
        elenco = interpreta_pagina(await scarica(pagina))
        if elenco:
            await cache.salva(chiave, {"personaggi": [{"id": p.id, "nome": p.nome, "opera": p.opera} for p in elenco]}, SECONDI_CACHE)
    return rng.choice(elenco) if elenco else None

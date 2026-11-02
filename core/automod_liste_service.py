"""
core/automod_liste_service.py
=============================
Liste con nome dell'AutoMod (parole e domini): punto unico per leggerle e scriverle, con i tetti (20 liste per
server, 1000 voci, ogni voce fino a 60 caratteri). Le liste di sistema (`@parolacce-it`, `@parolacce-en`,
`@vetrine-inviti`) vengono dai file in data/automod/, sono in sola lettura e valgono in ogni server.
Funzioni coperte: SPEC §6 (AMD-015, AMD-016, AMD-028), D63
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.automod_regole_logic import MAX_LISTE, MAX_LUNG_VOCE, MAX_NOME, MAX_VOCI_LISTA, RegolaNonValida
from core.bounded_cache import BoundedCache

CARTELLA = Path(__file__).resolve().parent.parent / "data" / "automod"
LISTE_DI_SISTEMA = {
    "@parolacce-it": ("parole", "parolacce_it.txt"),
    "@parolacce-en": ("parole", "parolacce_en.txt"),
    "@vetrine-inviti": ("domini", "vetrine_inviti.txt"),
}
TIPI = ("parole", "domini")
_cache: BoundedCache[int, dict[str, tuple[str, tuple[str, ...]]]] = BoundedCache(2000)


@lru_cache(maxsize=None)
def lista_di_sistema(nome: str) -> tuple[str, tuple[str, ...]]:
    tipo, file = LISTE_DI_SISTEMA[nome]
    righe = (CARTELLA / file).read_text(encoding="utf-8").splitlines()
    return tipo, tuple(r.strip() for r in righe if r.strip() and not r.startswith("#"))


def leggi_voci(testo: str) -> tuple[str, ...]:
    """Una voce per riga (o separate da virgola): senza doppioni, vuote tolte, ognuna al massimo 60 caratteri."""
    grezze = [v.strip() for riga in (testo or "").splitlines() for v in riga.split(",")]
    viste: dict[str, str] = {}
    for v in grezze:
        if not v:
            continue
        if len(v) > MAX_LUNG_VOCE:
            raise RegolaNonValida(f"ogni voce al massimo {MAX_LUNG_VOCE} caratteri")
        viste.setdefault(v.casefold(), v)
    if len(viste) > MAX_VOCI_LISTA:
        raise RegolaNonValida(f"al massimo {MAX_VOCI_LISTA} voci")
    return tuple(viste.values())


def controlla_nome(nome: str) -> str:
    nome = (nome or "").strip()
    if not nome or len(nome) > MAX_NOME or nome.startswith("@"):
        raise RegolaNonValida(f"il nome è lungo al massimo {MAX_NOME} caratteri e non comincia con @")
    return nome


async def liste_del_server(guild_id: int) -> dict[str, tuple[str, tuple[str, ...]]]:
    """{nome: (tipo, voci)} delle liste del server, in cache. Se non si leggono: nessuna lista, il filtro continua."""
    trovate = _cache.get(guild_id)
    if trovate is None:
        from core.repositories.automod_liste_repo import automod_liste_repo

        try:
            trovate = {n: (t, v) for n, t, v in await automod_liste_repo.elenca(guild_id)}
        except Exception:
            return {}
        _cache.set(guild_id, trovate)
    return trovate


async def voci_per_regole(guild_id: int) -> dict[str, tuple[str, ...]]:
    """Le voci di ogni lista (del server e di sistema) per nome, pronte per `innesco_scatta`."""
    fuori = {nome: lista_di_sistema(nome)[1] for nome in LISTE_DI_SISTEMA}
    fuori.update({n: v for n, (_, v) in (await liste_del_server(guild_id)).items()})
    return fuori


async def salva_lista(guild_id: int, nome: str, tipo: str, voci: tuple[str, ...]) -> None:
    from core.repositories.automod_liste_repo import automod_liste_repo

    nome = controlla_nome(nome)
    if tipo not in TIPI:
        raise RegolaNonValida("il tipo è parole o domini")
    if len(voci) > MAX_VOCI_LISTA:
        raise RegolaNonValida(f"al massimo {MAX_VOCI_LISTA} voci")
    esistenti = await liste_del_server(guild_id)
    if nome not in esistenti and len(esistenti) >= MAX_LISTE:
        raise RegolaNonValida(f"al massimo {MAX_LISTE} liste per server")
    await automod_liste_repo.salva(guild_id, nome, tipo, voci)
    _cache.delete(guild_id)


async def aggiungi_voci(guild_id: int, nome: str, nuove: tuple[str, ...]) -> tuple[str, ...]:
    tipo, voci = (await liste_del_server(guild_id))[nome]
    unite = leggi_voci("\n".join((*voci, *nuove)))
    await salva_lista(guild_id, nome, tipo, unite)
    return unite


async def togli_voci(guild_id: int, nome: str, via: tuple[str, ...]) -> tuple[str, ...]:
    tipo, voci = (await liste_del_server(guild_id))[nome]
    togliere = {v.casefold() for v in via}
    restano = tuple(v for v in voci if v.casefold() not in togliere)
    await salva_lista(guild_id, nome, tipo, restano)
    return restano


async def elimina_lista(guild_id: int, nome: str) -> bool:
    from core.repositories.automod_liste_repo import automod_liste_repo

    fatto = await automod_liste_repo.elimina(guild_id, nome)
    _cache.delete(guild_id)
    return fatto


def svuota_cache(guild_id: int | None = None) -> None:
    _cache.clear() if guild_id is None else _cache.delete(guild_id)

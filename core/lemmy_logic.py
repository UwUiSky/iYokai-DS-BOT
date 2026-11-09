"""
core/lemmy_logic.py
===================
Immagini dalle comunità Lemmy per `/immagini post` (#131, D70, B10): elenco chiuso in `data/lemmy_comunita.json`,
lettura di `api/v3/post/list` senza chiave con `safe_get`, solo post con immagine https, mai quelli segnati
nsfw (del post o della comunità), rimossi o cancellati. Cache comune di 15 minuti; i post segnalati da 3 persone
non si mostrano più. Il contenuto è di terzi: autore, comunità e link alla fonte sono sempre mostrati.
Funzioni coperte: SPEC §16 (FUN-053, FUN-055)
Dipende da: core/safe_http.py, core/repositories/cache_esterna_repo.py, core/repositories/immagini_segnalazioni_repo.py
"""

from __future__ import annotations

import json
import random
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlparse

PERCORSO = Path(__file__).resolve().parent.parent / "data" / "lemmy_comunita.json"
MAX_BYTE = 600_000
POST_PER_RICHIESTA = 20
SECONDI_CACHE = 15 * 60
ESTENSIONI_IMMAGINE = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MAX_TITOLO = 200


@dataclass(frozen=True)
class Comunita:
    id: str
    istanza: str
    nome: str
    etichetta: str

    @property
    def host(self) -> str:
        return urlparse(self.istanza).hostname or ""


@dataclass(frozen=True)
class Post:
    chiave: str
    titolo: str
    immagine: str
    pagina: str
    autore: str
    comunita: str


@lru_cache(maxsize=1)
def comunita() -> tuple[Comunita, ...]:
    grezzo = json.loads(PERCORSO.read_text(encoding="utf-8"))["comunita"]
    return tuple(Comunita(c["id"], c["istanza"].rstrip("/"), c["nome"], c["etichetta"]) for c in grezzo)


def trova(id_comunita: str) -> Comunita | None:
    return next((c for c in comunita() if c.id == (id_comunita or "").strip().casefold()), None)


def suggerimenti(digitato: str) -> list[tuple[str, str]]:
    """(etichetta, id) delle comunità che contengono il testo. Solo dati locali."""
    d = (digitato or "").strip().casefold()
    return [(c.etichetta[:100], c.id) for c in comunita() if not d or d in c.id or d in c.etichetta.casefold()][:25]


def _https(valore: object) -> str | None:
    return valore if isinstance(valore, str) and valore.startswith("https://") and len(valore) <= 500 and (urlparse(valore).hostname or "") else None


def _e_immagine(post: dict, url: str) -> bool:
    tipo = post.get("url_content_type")
    if isinstance(tipo, str) and tipo:
        return tipo.lower().startswith("image/") and "svg" not in tipo.lower()
    return urlparse(url).path.lower().endswith(ESTENSIONI_IMMAGINE)


def interpreta(testo: str | None, com: Comunita) -> list[Post]:
    """I post con immagine di una risposta. Scarta nsfw, rimossi, cancellati e tutto ciò che non è https."""
    try:
        dati = json.loads(testo or "")
    except ValueError:
        return []
    righe = dati.get("posts") if isinstance(dati, dict) else None
    if not isinstance(righe, list):
        return []
    trovati: list[Post] = []
    for riga in righe:
        if not isinstance(riga, dict) or not isinstance(riga.get("post"), dict):
            continue
        post = riga["post"]
        comm = riga.get("community") if isinstance(riga.get("community"), dict) else {}
        if post.get("nsfw") or comm.get("nsfw") or post.get("removed") or post.get("deleted"):
            continue
        immagine = _https(post.get("url"))
        numero = post.get("id")
        if immagine is None or not isinstance(numero, int) or not _e_immagine(post, immagine):
            continue
        creatore = riga.get("creator") if isinstance(riga.get("creator"), dict) else {}
        titolo = post.get("name")
        pagina = _https(post.get("ap_id")) or f"{com.istanza}/post/{numero}"
        trovati.append(Post(
            f"{com.host}:{numero}", (titolo if isinstance(titolo, str) else "")[:MAX_TITOLO], immagine, pagina,
            str(creatore.get("name") or "")[:80], com.nome,
        ))
    return trovati


async def _scarica_vero(url: str) -> str | None:
    from core.safe_http import safe_get

    return await safe_get(url, max_bytes=MAX_BYTE)


class ServizioLemmy:
    """Un post a caso da una comunità, con cache comune; chi chiama passa la chiave dei post da non mostrare."""

    def __init__(self, scarica: Callable[[str], Awaitable[str | None]] | None = None, cache=None, rng: random.Random | None = None) -> None:
        self._scarica = scarica or _scarica_vero
        self._cache = cache
        self._rng = rng or random.Random()

    def _repo_cache(self):
        if self._cache is None:
            from core.repositories.cache_esterna_repo import cache_esterna_repo

            self._cache = cache_esterna_repo
        return self._cache

    async def elenco(self, com: Comunita) -> list[Post]:
        chiave = f"lemmy:{com.id}"
        salvato = await self._repo_cache().leggi(chiave)
        if salvato is not None:
            return [Post(**p) for p in salvato.get("posts", [])]
        url = f"{com.istanza}/api/v3/post/list?community_name={quote(com.nome)}&sort=Hot&limit={POST_PER_RICHIESTA}"
        posts = interpreta(await self._scarica(url), com)
        if posts:
            await self._repo_cache().salva(chiave, {"posts": [asdict(p) for p in posts]}, SECONDI_CACHE)
        return posts

    async def post(self, com: Comunita, bloccati: set[str]) -> Post | None:
        liberi = [p for p in await self.elenco(com) if p.chiave not in bloccati]
        return self._rng.choice(liberi) if liberi else None


servizio_lemmy = ServizioLemmy()

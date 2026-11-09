"""
core/schede_giochi_logic.py
===========================
Schede di giochi, anime e carte per `/web scheda` (#131, D70, B9): Pokémon (PokéAPI), anime e manga (AniList),
Magic (Scryfall), Hearthstone (HearthstoneJSON), osu! (API v2) e Fortnite (fortnite-api.com).
Ogni risposta passa da `core/safe_http.safe_richiesta` (timeout, tetto di byte, nessun redirect), entra nella
cache comune `cache_esterna` e diventa una «scheda» neutra rispetto alla lingua (i nomi dei campi sono chiavi
del catalogo). Le chiavi si leggono da `config/giochi_servizi.env` o dall'ambiente e non finiscono mai nei log.
Funzioni coperte: SPEC §16 (B9 di #131: FUN-066..070, 073)
Dipende da: core/safe_http.py, core/repositories/cache_esterna_repo.py, docs/servizi_giochi.md
"""

from __future__ import annotations

import asyncio
import difflib
import html
import json
import logging
import os
import re
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, urlparse

from core import safe_http

logger = logging.getLogger("iyokai.schede")

SERVIZI = ("pokemon", "anime", "manga", "magic", "hearthstone", "osu", "fortnite")
MAX_NOME = 100
FILE_SERVIZI = Path(__file__).resolve().parent.parent / "config" / "giochi_servizi.env"
_SIGLA = {"pokemon": "POKEAPI", "anime": "ANILIST", "manga": "ANILIST", "magic": "SCRYFALL",
          "hearthstone": "HEARTHSTONE", "osu": "OSU", "fortnite": "FORTNITE"}
_CON_CHIAVE = ("osu", "fortnite")
CACHE_SECONDI = {"pokemon": 7 * 86400, "anime": 86400, "manga": 86400, "magic": 86400, "hearthstone": 86400, "osu": 600, "fortnite": 600}
MAX_CAMPO = 1000

POKEAPI = "https://pokeapi.co/api/v2"


def _pk(*parti: str) -> str:
    return "/".join((POKEAPI, *parti))
ANILIST = "https://graphql.anilist.co"
SCRYFALL = "https://api.scryfall.com/cards/named?fuzzy="
HEARTHSTONE = "https://api.hearthstonejson.com/v1/latest/{loc}/cards.collectible.json"
HEARTHSTONE_IMG = "https://art.hearthstonejson.com/v1/render/latest/{loc}/512x/{id}.png"
OSU_TOKEN = "https://osu.ppy.sh/oauth/token"
OSU_UTENTE = "https://osu.ppy.sh/api/v2/users/{nome}/osu?key=username"
FORTNITE = "https://fortnite-api.com/v2/stats/br/v2?name="


# ---------------- configurazione ----------------
def env_con_file(env: Mapping[str, str] | None = None, percorso: Path | None = None) -> dict[str, str]:
    """L'ambiente più le variabili `GIOCHI_*` del file (l'ambiente vince; un valore vuoto non copre il file)."""
    env = dict(os.environ if env is None else env)
    percorso = FILE_SERVIZI if percorso is None else percorso
    if not percorso.is_file():
        return env
    from dotenv import dotenv_values

    for chiave, valore in dotenv_values(percorso).items():
        if chiave.startswith("GIOCHI_") and valore and not env.get(chiave):
            env[chiave] = valore
    return env


def chiave_servizio(servizio: str, env: Mapping[str, str] | None = None) -> str:
    return (env_con_file(env).get(f"GIOCHI_{_SIGLA[servizio]}_KEY") or "").strip()


def servizio_acceso(servizio: str, env: Mapping[str, str] | None = None) -> bool:
    """Acceso se l'interruttore non è «no» e, per osu! e Fortnite, la chiave c'è."""
    e = env_con_file(env)
    if (e.get(f"GIOCHI_{_SIGLA[servizio]}_ATTIVO") or "si").strip().lower() in ("no", "0", "false", "off"):
        return False
    return servizio not in _CON_CHIAVE or bool(chiave_servizio(servizio, e))


# ---------------- piccoli attrezzi ----------------
async def _http(url: str, **kw) -> str | None:
    return await safe_http.safe_richiesta(url, **kw)


_ultimo: dict[str, float] = {}
_serrature: dict[str, asyncio.Lock] = {}


async def _ritmo(nome: str, secondi: float) -> None:
    """Aspetta che passino `secondi` dall'ultima richiesta allo stesso servizio (Scryfall 100 ms, osu! 1 s)."""
    serratura = _serrature.setdefault(nome, asyncio.Lock())
    async with serratura:
        attesa = _ultimo.get(nome, 0.0) + secondi - time.monotonic()
        if attesa > 0:
            await asyncio.sleep(attesa)
        _ultimo[nome] = time.monotonic()


def _taglia(testo: object, massimo: int = MAX_CAMPO) -> str:
    t = " ".join(str(testo or "").split())
    return t if len(t) <= massimo else t[: massimo - 1] + "…"


def _https_di(url: object, domini: tuple[str, ...]) -> str | None:
    """L'indirizzo solo se è https e il dominio è uno di quelli attesi (o un suo sottodominio)."""
    if not isinstance(url, str):
        return None
    p = urlparse(url)
    ok = p.scheme == "https" and p.hostname and any(p.hostname == d or p.hostname.endswith("." + d) for d in domini)
    return url if ok else None


def _scheda(titolo: object, descrizione: object = "", url: str | None = None, miniatura: str | None = None,
            immagine: str | None = None, campi: list[tuple[str, object]] | None = None, adulti: bool = False, **extra) -> dict:
    return {
        "titolo": _taglia(titolo, 256), "descrizione": _taglia(descrizione, 1000), "url": url, "miniatura": miniatura,
        "immagine": immagine, "adulti": adulti,
        "campi": [[c, _taglia(v, 1000)] for c, v in (campi or []) if str(v or "").strip()][:10], **extra,
    }


# ---------------- Pokémon ----------------
_TIPI = ("normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground", "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy")
TIPI_IT = {"normal": "normale", "fire": "fuoco", "water": "acqua", "electric": "elettro", "grass": "erba", "ice": "ghiaccio",
           "fighting": "lotta", "poison": "veleno", "ground": "terra", "flying": "volante", "psychic": "psico", "bug": "coleottero",
           "rock": "roccia", "ghost": "spettro", "dragon": "drago", "dark": "buio", "steel": "acciaio", "fairy": "folletto"}
# attaccante -> (superefficace contro, poco efficace contro, nessun effetto su)
_TABELLA = {
    "normal": ((), ("rock", "steel"), ("ghost",)),
    "fire": (("grass", "ice", "bug", "steel"), ("fire", "water", "rock", "dragon"), ()),
    "water": (("fire", "ground", "rock"), ("water", "grass", "dragon"), ()),
    "electric": (("water", "flying"), ("electric", "grass", "dragon"), ("ground",)),
    "grass": (("water", "ground", "rock"), ("fire", "grass", "poison", "flying", "bug", "dragon", "steel"), ()),
    "ice": (("grass", "ground", "flying", "dragon"), ("fire", "water", "ice", "steel"), ()),
    "fighting": (("normal", "ice", "rock", "dark", "steel"), ("poison", "flying", "psychic", "bug", "fairy"), ("ghost",)),
    "poison": (("grass", "fairy"), ("poison", "ground", "rock", "ghost"), ("steel",)),
    "ground": (("fire", "electric", "poison", "rock", "steel"), ("grass", "bug"), ("flying",)),
    "flying": (("grass", "fighting", "bug"), ("electric", "rock", "steel"), ()),
    "psychic": (("fighting", "poison"), ("psychic", "steel"), ("dark",)),
    "bug": (("grass", "psychic", "dark"), ("fire", "fighting", "poison", "flying", "ghost", "steel", "fairy"), ()),
    "rock": (("fire", "ice", "flying", "bug"), ("fighting", "ground", "steel"), ()),
    "ghost": (("psychic", "ghost"), ("dark",), ("normal",)),
    "dragon": (("dragon",), ("steel",), ("fairy",)),
    "dark": (("psychic", "ghost"), ("fighting", "dark", "fairy"), ()),
    "steel": (("ice", "rock", "fairy"), ("fire", "water", "electric", "steel"), ()),
    "fairy": (("fighting", "dragon", "dark"), ("fire", "poison", "steel"), ()),
}


def debolezze(tipi: list[str]) -> dict[float, list[str]]:
    """Moltiplicatore del danno ricevuto per ogni tipo attaccante, dato il tipo (o i due tipi) del Pokémon."""
    risultato: dict[float, list[str]] = {}
    difensori = [t for t in tipi if t in _TABELLA]
    for att in _TIPI:
        forte, debole, nulla = _TABELLA[att]
        m = 1.0
        for d in difensori:
            m *= 2.0 if d in forte else 0.5 if d in debole else 0.0 if d in nulla else 1.0
        if m != 1.0:
            risultato.setdefault(m, []).append(att)
    return risultato


_nomi_pokemon: tuple[float, list[str]] = (0.0, [])


async def _elenco_pokemon() -> list[str]:
    global _nomi_pokemon
    if time.monotonic() - _nomi_pokemon[0] < 86400 and _nomi_pokemon[1]:
        return _nomi_pokemon[1]
    testo = await _http(_pk("pokemon-species") + "?limit=2000", max_bytes=400_000)
    nomi = [r["name"] for r in json.loads(testo or "{}").get("results", []) if isinstance(r.get("name"), str)]
    if nomi:
        _nomi_pokemon = (time.monotonic(), nomi)
    return nomi


def _slug(nome: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", nome.casefold().replace(" ", "-").replace("’", "").replace("'", ""))


def _bello(slug: str) -> str:
    return slug.replace("-", " ").title()


async def cerca_pokemon(nome: str, lingua: str) -> dict | None:
    slug = _slug(nome)
    if not slug:
        return None
    testo = await _http(_pk("pokemon", slug))
    if testo is None:  # nome sbagliato o in italiano: si prova il più simile tra le specie
        vicino = difflib.get_close_matches(slug, await _elenco_pokemon(), 1, 0.75)
        testo = await _http(_pk("pokemon", vicino[0])) if vicino else None
        if testo is None:
            return None
    dati = json.loads(testo)
    specie = json.loads(await _http(_pk("pokemon-species", dati["species"]["name"])) or "{}")
    lg = "it" if lingua.startswith("it") else "en"
    nomi = {n["language"]["name"]: n["name"] for n in specie.get("names", [])}
    flavor = [f["flavor_text"] for f in specie.get("flavor_text_entries", []) if f["language"]["name"] == lg]
    tipi = [t["type"]["name"] for t in sorted(dati["types"], key=lambda t: t["slot"])]
    sigle = {"hp": "PS", "attack": "Att", "defense": "Dif", "special-attack": "AttSp", "special-defense": "DifSp", "speed": "Vel"}
    stat = " · ".join(f"{sigle.get(s['stat']['name'], s['stat']['name'])} {s['base_stat']}" for s in dati["stats"])
    arte = dati.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default")
    nome_ok = nomi.get(lg) or _bello(dati["name"])
    return _scheda(
        f"#{dati['id']} {nome_ok}", flavor[-1] if flavor else "", None,
        _https_di(arte, ("githubusercontent.com",)), None,
        [("scheda_campo_tipi", " / ".join(tipi)), ("scheda_campo_abilita", ", ".join(_bello(a["ability"]["name"]) for a in dati["abilities"])),
         ("scheda_campo_statistiche", stat), ("scheda_campo_altezza_peso", f"{dati['height'] / 10:g} m · {dati['weight'] / 10:g} kg")],
        tipi=tipi,
    )


# ---------------- anime e manga (AniList) ----------------
_QUERY_ANILIST = (
    "query($s:String,$t:MediaType){Media(search:$s,type:$t){title{romaji english} description(asHtml:false) siteUrl "
    "coverImage{large} format status episodes chapters averageScore genres isAdult}}"
)


async def cerca_anilist(nome: str, tipo: str) -> dict | None:
    testo = await _http(
        ANILIST, metodo="POST", headers={"Content-Type": "application/json", "Accept": "application/json"},
        json_corpo={"query": _QUERY_ANILIST, "variables": {"s": nome, "t": tipo}},
    )
    media = ((json.loads(testo or "{}").get("data") or {}).get("Media")) if testo else None
    if not media:
        return None
    desc = html.unescape(re.sub(r"<[^>]+>", " ", media.get("description") or ""))
    titoli = media.get("title") or {}
    generi = [g for g in (media.get("genres") or []) if isinstance(g, str)]
    voto = media.get("averageScore")
    return _scheda(
        titoli.get("english") or titoli.get("romaji") or nome, desc, _https_di(media.get("siteUrl"), ("anilist.co",)),
        _https_di((media.get("coverImage") or {}).get("large"), ("anilist.co",)), None,
        [("scheda_campo_formato", media.get("format")), ("scheda_campo_stato", media.get("status")),
         ("scheda_campo_episodi" if tipo == "ANIME" else "scheda_campo_capitoli", media.get("episodes") if tipo == "ANIME" else media.get("chapters")),
         ("scheda_campo_voto", f"{voto}/100" if voto else ""), ("scheda_campo_generi", ", ".join(generi[:6]))],
        adulti=bool(media.get("isAdult")) or "Hentai" in generi,
    )


# ---------------- Magic (Scryfall) ----------------
async def cerca_magic(nome: str) -> dict | None:
    await _ritmo("scryfall", 0.1)
    testo = await _http(SCRYFALL + quote(nome, safe=""), headers={"User-Agent": safe_http.USER_AGENT, "Accept": "application/json;q=0.9,*/*;q=0.8"})
    c = json.loads(testo or "{}") if testo else {}
    if c.get("object") != "card":
        return None
    facce = c.get("card_faces") or []
    img = (c.get("image_uris") or (facce[0].get("image_uris") if facce else None) or {}).get("normal")
    oracolo = c.get("oracle_text") or "\n".join(f.get("oracle_text", "") for f in facce)
    return _scheda(
        c.get("name"), "", _https_di(c.get("scryfall_uri"), ("scryfall.com",)), None, _https_di(img, ("scryfall.io", "scryfall.com")),
        [("scheda_campo_costo", c.get("mana_cost")), ("scheda_campo_tipo", c.get("type_line")), ("scheda_campo_testo", oracolo),
         ("scheda_campo_espansione", c.get("set_name")), ("scheda_campo_rarita", c.get("rarity"))],
    )


# ---------------- Hearthstone ----------------
_carte_hs: dict[str, tuple[float, list[dict]]] = {}


async def _carte_hearthstone(loc: str) -> list[dict]:
    visto = _carte_hs.get(loc)
    if visto and time.monotonic() - visto[0] < 86400:
        return visto[1]
    testo = await _http(HEARTHSTONE.format(loc=loc), max_bytes=8_000_000)
    carte = [
        {k: c.get(k) for k in ("id", "name", "text", "cost", "attack", "health", "type", "rarity", "cardClass")}
        for c in json.loads(testo or "[]") if isinstance(c, dict) and isinstance(c.get("name"), str) and isinstance(c.get("id"), str)
    ]
    if carte:
        _carte_hs[loc] = (time.monotonic(), carte)
    return carte


async def cerca_hearthstone(nome: str, lingua: str) -> dict | None:
    loc = "itIT" if lingua.startswith("it") else "enUS"
    carte = await _carte_hearthstone(loc)
    chiave = nome.casefold()
    c = next((x for x in carte if x["name"].casefold() == chiave), None) or next((x for x in carte if chiave in x["name"].casefold()), None)
    if c is None:
        vicino = difflib.get_close_matches(chiave, [x["name"].casefold() for x in carte], 1, 0.75)
        c = next((x for x in carte if vicino and x["name"].casefold() == vicino[0]), None)
    if c is None or not re.fullmatch(r"[A-Za-z0-9_]+", c["id"]):
        return None
    testo = html.unescape(re.sub(r"<[^>]+>", "", (c.get("text") or "").replace("\n", " ")))
    ah = f"{c['attack']}/{c['health']}" if c.get("attack") is not None and c.get("health") is not None else ""
    return _scheda(
        c["name"], "", None, None, HEARTHSTONE_IMG.format(loc=loc, id=c["id"]),
        [("scheda_campo_costo", c.get("cost")), ("scheda_campo_attacco_salute", ah), ("scheda_campo_tipo", _bello((c.get("type") or "").lower())),
         ("scheda_campo_classe", _bello((c.get("cardClass") or "").lower())), ("scheda_campo_rarita", _bello((c.get("rarity") or "").lower())),
         ("scheda_campo_testo", testo)],
    )


# ---------------- osu! ----------------
_token_osu: dict[str, object] = {"valore": None, "scade": 0.0}
_serratura_token = asyncio.Lock()


async def _token() -> str | None:
    async with _serratura_token:
        if _token_osu["valore"] and float(_token_osu["scade"]) > time.monotonic():  # type: ignore[arg-type]
            return str(_token_osu["valore"])
        id_, _, segreto = chiave_servizio("osu").partition(":")
        if not id_.isdigit() or not segreto:
            return None
        await _ritmo("osu", 1.0)
        testo = await _http(OSU_TOKEN, metodo="POST", headers={"Content-Type": "application/json", "Accept": "application/json"},
                            json_corpo={"client_id": int(id_), "client_secret": segreto, "grant_type": "client_credentials", "scope": "public"})
        dati = json.loads(testo or "{}") if testo else {}
        if not isinstance(dati.get("access_token"), str):
            return None
        _token_osu["valore"] = dati["access_token"]
        _token_osu["scade"] = time.monotonic() + max(60, int(dati.get("expires_in", 3600)) - 60)
        return dati["access_token"]


async def cerca_osu(nome: str) -> dict | None:
    token = await _token()
    if token is None:
        return None
    await _ritmo("osu", 1.0)  # al massimo 60 richieste al minuto
    testo = await _http(OSU_UTENTE.format(nome=quote(nome, safe="")), headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    u = json.loads(testo or "{}") if testo else {}
    if not isinstance(u.get("username"), str):
        return None
    s = u.get("statistics") or {}
    rango = s.get("global_rank")
    return _scheda(
        u["username"], "", f"https://osu.ppy.sh/users/{int(u['id'])}" if isinstance(u.get("id"), int) else None,
        _https_di(u.get("avatar_url"), ("ppy.sh",)), None,
        [("scheda_campo_rango", f"#{rango}" if rango else ""), ("scheda_campo_pp", f"{s.get('pp', 0):,.0f}"),
         ("scheda_campo_precisione", f"{s.get('hit_accuracy', 0):.2f}%"), ("scheda_campo_partite", s.get("play_count")),
         ("scheda_campo_livello", (s.get("level") or {}).get("current")), ("scheda_campo_ore", f"{int(s.get('play_time') or 0) // 3600}"),
         ("scheda_campo_paese", u.get("country_code"))],
    )


# ---------------- Fortnite ----------------
async def cerca_fortnite(nome: str) -> dict | None:
    testo = await _http(FORTNITE + quote(nome, safe=""), headers={"Authorization": chiave_servizio("fortnite"), "Accept": "application/json"})
    d = (json.loads(testo or "{}") if testo else {}).get("data") or {}
    tutto = ((d.get("stats") or {}).get("all") or {}).get("overall")
    if not tutto or not isinstance((d.get("account") or {}).get("name"), str):
        return None
    return _scheda(
        d["account"]["name"], "", None, None, None,
        [("scheda_campo_vittorie", tutto.get("wins")), ("scheda_campo_uccisioni", tutto.get("kills")), ("scheda_campo_partite", tutto.get("matches")),
         ("scheda_campo_kd", tutto.get("kd")), ("scheda_campo_percentuale_vittorie", f"{tutto.get('winRate', 0):.1f}%"),
         ("scheda_campo_ore", f"{int(tutto.get('minutesPlayed') or 0) // 60}"),
         ("scheda_campo_livello", ((d.get("battlePass") or {}).get("level")))],
    )


# ---------------- entrata unica ----------------
async def cerca(servizio: str, nome: str, lingua: str, cache) -> dict | None:
    """La scheda dalla cache o dal servizio. `cache` ha `leggi(chiave)` e `salva(chiave, dati, secondi)`."""
    nome = " ".join(nome.split())[:MAX_NOME]
    if servizio not in SERVIZI or not nome:
        return None
    lg = lingua[:2] if servizio in ("pokemon", "hearthstone") else ""
    chiave = f"scheda:{servizio}:{lg}:{nome.casefold()}"[:250]
    visto = await cache.leggi(chiave)
    if visto:
        return visto
    try:
        if servizio == "pokemon":
            dati = await cerca_pokemon(nome, lingua)
        elif servizio in ("anime", "manga"):
            dati = await cerca_anilist(nome, servizio.upper())
        elif servizio == "magic":
            dati = await cerca_magic(nome)
        elif servizio == "hearthstone":
            dati = await cerca_hearthstone(nome, lingua)
        elif servizio == "osu":
            dati = await cerca_osu(nome)
        else:
            dati = await cerca_fortnite(nome)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        logger.warning("Risposta di %s non leggibile: %s", servizio, type(exc).__name__)  # solo il tipo, mai il testo
        return None
    if dati:
        await cache.salva(chiave, dati, CACHE_SECONDI[servizio])
    return dati

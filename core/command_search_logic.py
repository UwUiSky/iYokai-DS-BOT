"""
core/command_search_logic.py
================================
Logica pura di -cerca-comando (nessuna infrastruttura di embedding/NLP
disponibile in questo progetto): punteggio per sovrapposizione di
parole tra la query e nome+descrizione di ogni comando, con un bonus
se la query intera compare come sottostringa. Semplice ma sufficiente
per query in linguaggio naturale corte tipiche di un comando slash
("banna qualcuno", "crea un sondaggio").
"""

# DA FARE (issue #77, fase F8): NF-06, Lingue italiano e inglese, e
#   `/utility cerca-comando`. Vedi revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import discord
from discord import app_commands

import re

logger = logging.getLogger("iyokai.command_search")


STOPWORD_ITALIANE = frozenset(
    {
        "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
        "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
        "e", "o", "ma", "che", "non", "si", "mi", "ti", "ci", "vi",
        "io", "tu", "lui", "lei", "noi", "voi", "loro",
        "voglio", "vorrei", "puoi", "potresti", "come", "cosa",
        "qualcuno", "qualcosa", "quale", "questo", "questa",
        "favore", "grazie", "per favore",
    }
)


def _tokenizza(testo: str) -> set[str]:
    parole = set(re.findall(r"[a-zàèéìòù0-9]+", testo.lower()))
    return parole - STOPWORD_ITALIANE


def _condividono_radice(parola_a: str, parola_b: str, prefisso_minimo: int = 4) -> bool:
    """
    Confronto per prefisso condiviso — non uno stemmer vero, ma
    sufficiente a far combaciare forme verbali italiane comuni della
    stessa radice ("bannare" vs "banna", "silenzia" vs "silenziare")
    senza aggiungere una libreria di NLP per un progetto che non ne
    ha altrimenti bisogno. Trovato necessario scrivendo il test: una
    query naturale come "voglio bannare qualcuno" non condivideva
    NESSUN token esatto con "banna" (comando) — il confronto per
    insieme di parole da solo non basta per l'italiano coniugato.
    """
    lunghezza_comune = min(len(parola_a), len(parola_b))
    if lunghezza_comune < prefisso_minimo:
        return parola_a == parola_b
    return parola_a[:prefisso_minimo] == parola_b[:prefisso_minimo]


def score_command(query: str, name: str, description: str) -> float:
    """
    Punteggio di rilevanza — non normalizzato a [0, 1] in modo
    rigoroso (il bonus sottostringa può farlo superare 1), pensato
    solo per ORDINARE i risultati e per un confronto con una soglia
    minima, non come probabilità.
    """
    parole_query = _tokenizza(query)
    if not parole_query:
        return 0.0

    testo_comando = f"{name} {description}"
    parole_comando = _tokenizza(testo_comando)

    corrispondenze = 0.0
    for parola in parole_query:
        if parola in parole_comando:
            corrispondenze += 1.0
        elif any(_condividono_radice(parola, pc) for pc in parole_comando):
            corrispondenze += 0.7  # radice condivisa, non un match esatto

    punteggio = corrispondenze / len(parole_query)

    if query.strip().lower() in testo_comando.lower():
        punteggio += 0.5

    return punteggio


def search_commands(
    query: str,
    commands: list[tuple[str, str]],
    threshold: float = 0.34,
    limit: int = 3,
) -> list[tuple[str, str, float]]:
    """
    commands è una lista di (nome, descrizione). Restituisce i
    migliori risultati SOPRA la soglia, ordinati per punteggio
    decrescente — una soglia troppo bassa restituirebbe risultati
    non pertinenti quanto quello vero, una troppo alta perderebbe
    corrispondenze legittime con parole diverse ma sinonimiche
    (limite intrinseco di un punteggio per sovrapposizione di parole,
    non un vero motore semantico).
    """
    risultati = [
        (nome, descrizione, score_command(query, nome, descrizione))
        for nome, descrizione in commands
    ]
    risultati = [r for r in risultati if r[2] >= threshold]
    risultati.sort(key=lambda r: r[2], reverse=True)
    return risultati[:limit]


# ======================================================================
# Pannello e ricerca di -cerca-comando (issue #147)
# ======================================================================
MAX_RISULTATI = 5
MAX_SUGGERIMENTI = 25  # limite di Discord per il completamento
CATEGORIE_PER_PAGINA = 20  # 4 righe da 5 bottoni; la quinta riga è per frecce e wiki (max 25 componenti)
COMANDI_PER_PAGINA = 10
MAX_OPZIONI_MOSTRATE = 10


@dataclass(frozen=True)
class Opzione:
    nome: str
    descrizione: str
    obbligatoria: bool


@dataclass(frozen=True)
class ComandoInfo:
    percorso: str  # "gruppo sottogruppo comando", senza barra
    descrizione: str
    gruppo: str  # il comando di primo livello
    opzioni: tuple[Opzione, ...]
    # Livelli richiesti per usarlo: quelli dei gruppi sopra di lui (`GruppoYokai.livello`)
    # e quelli dei suoi `@richiedi`.
    livelli: tuple = ()


def raccogli_comandi(comandi: Iterable, prefisso: str = "", livelli: tuple = ()) -> list[ComandoInfo]:
    """Cammina l'albero (gruppi annidati compresi) e dà un `ComandoInfo` per ogni comando foglia."""
    risultati: list[ComandoInfo] = []
    for cmd in comandi:
        percorso = f"{prefisso} {cmd.name}".strip()
        if isinstance(cmd, app_commands.Group):
            proprio = getattr(cmd, "livello", None)
            risultati.extend(raccogli_comandi(cmd.commands, percorso, livelli + ((proprio,) if proprio else ())))
            continue
        dei_check = tuple(l for l in (getattr(c, "livello", None) for c in getattr(cmd, "checks", ())) if l)
        opzioni = tuple(
            Opzione(p.name, str(p.description or ""), bool(p.required))
            for p in getattr(cmd, "parameters", ())
        )
        risultati.append(
            ComandoInfo(
                percorso, cmd.description or "(nessuna descrizione)", percorso.split(" ")[0], opzioni,
                livelli + dei_check,
            )
        )
    return risultati


def menzione(percorso: str, ids: Mapping[str, int]) -> str:
    """`</gruppo comando:ID>` (cliccabile su PC e cellulare); senza ID, il testo `/gruppo comando`."""
    id_comando = ids.get(percorso.split(" ")[0])
    if id_comando is None:
        return f"`/{percorso}`"
    return f"</{percorso}:{id_comando}>"


def pagina(elementi: Sequence, indice: int, per_pagina: int) -> tuple[list, int, int]:
    """(elementi della pagina, indice corretto, numero di pagine). Mai meno di una pagina."""
    totale = max(1, -(-len(elementi) // per_pagina))
    indice = min(max(indice, 0), totale - 1)
    return list(elementi[indice * per_pagina : (indice + 1) * per_pagina]), indice, totale


# Gruppi di sinonimi italiani (e qualche termine inglese): la ricerca prova a
# sostituire una parola della richiesta con le altre del gruppo.
SINONIMI: tuple[tuple[str, ...], ...] = (
    ("banna", "caccia", "espelli", "allontana", "kick", "ban"),
    ("silenzia", "muta", "zittisci", "timeout", "mute"),
    ("avvisa", "ammonisci", "richiama", "warn", "avviso"),
    ("cancella", "elimina", "pulisci", "rimuovi", "svuota"),
    ("sondaggio", "votazione", "referendum", "poll"),
    ("promemoria", "ricordami", "ricorda", "reminder", "sveglia"),
    ("musica", "canzone", "suona", "brano", "riproduci"),
    ("classifica", "livello", "livelli", "punti", "esperienza"),
    ("monete", "soldi", "denaro", "economia", "negozio"),
    ("compleanno", "compleanni", "birthday"),
    ("giveaway", "sorteggio", "estrazione", "regalo", "concorso"),
    ("segnala", "report", "denuncia", "segnalazione"),
    ("aiuto", "help", "guida", "istruzioni"),
    ("canale", "stanza", "chat"),
    ("ruolo", "ruoli", "grado"),
    ("benvenuto", "saluto", "accoglienza"),
    ("suggerimento", "proposta", "idea", "suggerisci"),
)


def _varianti(query: str) -> list[str]:
    parole = re.findall(r"[a-zàèéìòù0-9]+", query.lower())
    varianti = []
    for i, parola in enumerate(parole):
        if parola in STOPWORD_ITALIANE:
            continue
        for gruppo in SINONIMI:
            if any(_condividono_radice(parola, m) for m in gruppo):
                for membro in gruppo:
                    if membro != parola:
                        varianti.append(" ".join(parole[:i] + [membro] + parole[i + 1 :]))
    return varianti


def _punteggio(query: str, info: ComandoInfo) -> float:
    pulita = query.strip().lstrip("/").strip().lower()
    if not pulita:
        return 0.0
    if pulita == info.percorso.lower():
        return 10.0
    migliore = score_command(pulita, info.percorso, info.descrizione)
    for variante in _varianti(pulita):
        migliore = max(migliore, 0.9 * score_command(variante, info.percorso, info.descrizione))
    return migliore


def cerca(
    query: str, comandi: Sequence[ComandoInfo], limite: int = MAX_RISULTATI, soglia: float = 0.34
) -> list[ComandoInfo]:
    punti = [(_punteggio(query, c), c) for c in comandi]
    punti = [(p, c) for p, c in punti if p >= soglia]
    punti.sort(key=lambda t: (-t[0], t[1].percorso))
    return [c for _, c in punti[:limite]]


def suggerimenti(query: str, comandi: Sequence[ComandoInfo], limite: int = MAX_SUGGERIMENTI) -> list[tuple[str, str]]:
    """(etichetta, valore) per il completamento: al massimo 25, etichetta e valore fino a 100 caratteri."""
    pulita = query.strip().lstrip("/").strip().lower()
    if pulita:
        punti = []
        for c in comandi:
            if c.percorso.lower().startswith(pulita):
                p = 3.0
            elif pulita in c.percorso.lower():
                p = 2.0
            else:
                p = _punteggio(pulita, c)
            if p >= 0.34:
                punti.append((p, c))
        punti.sort(key=lambda t: (-t[0], t[1].percorso))
        scelti = [c for _, c in punti]
    else:
        scelti = list(comandi)
    risultato = []
    for c in scelti:
        if len(c.percorso) > 100:
            continue
        risultato.append((f"/{c.percorso} — {c.descrizione}"[:100], c.percorso))
        if len(risultato) >= limite:
            break
    return risultato


async def filtra_per_livelli(
    comandi: Iterable[ComandoInfo], puo: Callable[[object], Awaitable[bool]]
) -> list[ComandoInfo]:
    """Tiene i comandi i cui livelli sono tutti ammessi da `puo` (una domanda per livello distinto)."""
    memo: dict[object, bool] = {}
    visibili = []
    for c in comandi:
        for livello in c.livelli:
            if livello not in memo:
                memo[livello] = bool(await puo(livello))
        if all(memo[l] for l in c.livelli):
            visibili.append(c)
    return visibili


def url_wiki(base: str | None, percorso: str | None = None) -> str | None:
    """Indirizzo della wiki (solo se `WIKI_BASE_URL` è un http/https valido); `percorso` "a b" -> /a/b."""
    base = (base or "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    if not percorso:
        return base
    url = base + "/" + "/".join(quote(p) for p in percorso.split(" "))
    return url if len(url) <= 512 else base


def _taglia(testo: str, massimo: int, compatta: bool = True) -> str:
    testo = " ".join(str(testo).split()) if compatta else str(testo)
    return testo if len(testo) <= massimo else testo[: massimo - 1] + "…"


def _testo_opzioni(opzioni: Sequence[Opzione]) -> str:
    if not opzioni:
        return "Nessuna opzione."
    righe = []
    for o in opzioni[:MAX_OPZIONI_MOSTRATE]:
        sigla = "obbligatoria" if o.obbligatoria else "facoltativa"
        righe.append(f"• `{o.nome}` ({sigla}) {_taglia(o.descrizione, 60)}".rstrip())
    if len(opzioni) > MAX_OPZIONI_MOSTRATE:
        righe.append(f"…e altre {len(opzioni) - MAX_OPZIONI_MOSTRATE}.")
    return "\n".join(righe)


def embed_risultati(risultati: Sequence[ComandoInfo], ids: Mapping[str, int], query: str) -> discord.Embed:
    embed = discord.Embed(
        title=_taglia(f"🔍 Risultati per «{query}»", 256), color=discord.Color.blurple()
    )
    for c in risultati[:MAX_RISULTATI]:
        valore = f"{menzione(c.percorso, ids)}\n{_taglia(c.descrizione, 150)}\n{_testo_opzioni(c.opzioni)}"
        embed.add_field(name=_taglia(f"/{c.percorso}", 256), value=_taglia(valore, 1024, False), inline=False)
    return embed


def embed_pannello(ultimo: str | None, ids: Mapping[str, int], *, in_dm: bool) -> discord.Embed:
    righe = []
    if ultimo:
        righe.append(f"**Ultimo comando usato:** {menzione(ultimo, ids)}")
    else:
        righe.append("Non hai ancora usato nessun comando qui.")
    righe.append("Scegli una categoria con i bottoni, oppure scrivi cosa vuoi fare nel campo `query`.")
    if in_dm:
        righe.append("In privato puoi solo cercare: i comandi si usano nei server.")
    return discord.Embed(title="🔍 Cerca un comando", description="\n\n".join(righe), color=discord.Color.blurple())


def embed_categoria(
    gruppo: str, comandi: Sequence[ComandoInfo], ids: Mapping[str, int], indice: int
) -> tuple[discord.Embed, int, int]:
    pezzo, indice, totale = pagina(comandi, indice, COMANDI_PER_PAGINA)
    righe = [f"{menzione(c.percorso, ids)} — {_taglia(c.descrizione, 100)}" for c in pezzo]
    embed = discord.Embed(
        title=_taglia(f"📂 {gruppo}", 256),
        description=_taglia("\n".join(righe) or "Nessun comando.", 4096, False),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Pagina {indice + 1}/{totale}")
    return embed, indice, totale


class CacheIdComandi:
    """
    ID dei comandi di primo livello, letti da Discord (`fetch_commands`) per le menzioni
    cliccabili. Si ricarica quando scade (`ttl`), quando serve un comando che manca
    (comando nuovo dopo una sync) non più spesso di ogni `attesa_minima` secondi, o dopo
    `invalida()`. La lettura corre fuori dal lock, in un unico compito condiviso, e chi
    aspetta non supera `timeout` secondi: poi usa i vecchi ID (la lettura continua da sola).
    Un errore di Discord non solleva e non cancella l'invalidazione.
    """

    def __init__(
        self,
        ttl: float = 3600.0,
        attesa_minima: float = 60.0,
        orologio: Callable[[], float] = time.monotonic,
        timeout: float = 2.0,
    ):
        self.ttl = ttl
        self.attesa_minima = attesa_minima
        self.timeout = timeout
        self._orologio = orologio
        self._ids: dict[str, int] = {}
        self._caricata: float | None = None
        self._tentativo: float | None = None
        self._forzata = False
        self._lock = asyncio.Lock()
        self._compito: asyncio.Task | None = None

    def invalida(self) -> None:
        """Da chiamare dopo ogni sync dei comandi: il prossimo uso ricarica gli ID."""
        self._forzata = True

    async def _carica(self, fetch, adesso: float) -> None:
        try:
            self._ids = {c.name: c.id for c in await fetch()}
            self._caricata = adesso
            self._forzata = False  # azzerata solo se la lettura riesce
        except Exception as exc:
            logger.warning("ID dei comandi non letti (%s): uso quelli vecchi.", type(exc).__name__)

    async def ottieni(self, fetch: Callable[[], Awaitable[Iterable]], serve: Iterable[str] = ()) -> dict[str, int]:
        async with self._lock:  # solo la decisione: nessuna chiamata a Discord qui dentro
            adesso = self._orologio()
            if self._compito is None or self._compito.done():
                scaduta = self._caricata is None or adesso - self._caricata >= self.ttl
                manca = any(n not in self._ids for n in serve)
                puo_tentare = self._tentativo is None or adesso - self._tentativo >= self.attesa_minima
                if self._forzata or (puo_tentare and (scaduta or manca)):
                    self._tentativo = adesso
                    self._compito = asyncio.ensure_future(self._carica(fetch, adesso))
            compito = self._compito if self._compito is not None and not self._compito.done() else None
        if compito is not None:
            try:
                await asyncio.wait_for(asyncio.shield(compito), timeout=self.timeout)
            except asyncio.TimeoutError:
                logger.warning("Lettura degli ID dei comandi lenta: uso quelli vecchi.")
        return dict(self._ids)

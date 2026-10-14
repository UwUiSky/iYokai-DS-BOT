"""
core/command_search_logic.py
================================
Logica pura di -cerca-comando e del suo pannello (issue #147; nessuna
infrastruttura di embedding/NLP disponibile): punteggio per sovrapposizione di
parole tra la query e nome+descrizione di ogni comando, con un bonus
se la query intera compare come sottostringa. Semplice ma sufficiente
per query in linguaggio naturale corte tipiche di un comando slash
("banna qualcuno", "crea un sondaggio").
"""

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

from core.i18n import t

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


# NF-06: la ricerca capisce anche l'inglese (parole vuote comuni di una richiesta in inglese).
STOPWORD_INGLESI = frozenset(
    {
        "the", "an", "of", "to", "for", "and", "or", "with", "my", "me", "is", "are", "it",
        "how", "can", "do", "does", "want", "wanna", "need", "please", "i", "you", "someone",
        "something", "somebody", "this", "that", "some", "any", "what", "where",
    }
)
_STOPWORD = STOPWORD_ITALIANE | STOPWORD_INGLESI


def _tokenizza(testo: str) -> set[str]:
    parole = set(re.findall(r"[a-zàèéìòù0-9]+", testo.lower()))
    return parole - _STOPWORD


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


def score_command(query: str, name: str, description: str, bonus_sottostringa: bool = True) -> float:
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

    if bonus_sottostringa and query.strip().lower() in testo_comando.lower():
        punteggio += 0.5

    return punteggio


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
    # NF-06: lo stesso comando in inglese (come lo vede chi ha Discord in inglese) e i moduli
    # del server da cui dipende (vuoto = nessun modulo da accendere).
    percorso_en: str = ""
    descrizione_en: str = ""
    moduli: tuple = ()


def moduli_del_comando(cmd) -> tuple[str, ...]:
    """
    I moduli del server che servono a un comando: i nomi `MODULE_*` (stringhe) del file che lo definisce
    e che sono registrati come moduli. Euristica per file: un comando appare se ALMENO UNO è acceso.
    """
    import sys

    from core.premium import registry

    modulo = sys.modules.get(getattr(cmd, "module", None) or "")
    if modulo is None:
        return ()
    nomi = {
        valore
        for chiave, valore in vars(modulo).items()
        if chiave.startswith("MODULE_") and isinstance(valore, str) and registry.get(valore) is not None
    }
    return tuple(sorted(nomi))


def raccogli_comandi(comandi: Iterable, prefisso: str = "", livelli: tuple = ()) -> list[ComandoInfo]:
    """Cammina l'albero (gruppi annidati compresi) e dà un `ComandoInfo` per ogni comando foglia."""
    risultati: list[ComandoInfo] = []
    for cmd in comandi:
        percorso = f"{prefisso} {cmd.name}".strip()
        if isinstance(cmd, app_commands.Group):
            proprio = getattr(cmd, "livello", None)
            risultati.extend(raccogli_comandi(cmd.commands, percorso, livelli + ((proprio,) if proprio else ())))
            continue
        dei_check = tuple(liv for liv in (getattr(c, "livello", None) for c in getattr(cmd, "checks", ())) if liv)
        opzioni = tuple(
            Opzione(p.name, str(p.description or ""), bool(p.required))
            for p in getattr(cmd, "parameters", ())
        )
        from core.command_translator import descrizione_inglese, nome_inglese

        percorso_en = " ".join(nome_inglese(s) or s for s in percorso.split(" "))
        risultati.append(
            ComandoInfo(
                percorso, cmd.description or "(nessuna descrizione)", percorso.split(" ")[0], opzioni,
                livelli + dei_check,
                percorso_en=percorso_en,
                descrizione_en=descrizione_inglese(cmd.qualified_name) or "",
                moduli=moduli_del_comando(cmd),
            )
        )
    return risultati


def menzione(percorso: str, ids: Mapping[str, int]) -> str:
    """Menzione cliccabile (PC e cellulare); senza ID, il testo semplice con la barra."""
    id_comando = ids.get(percorso.split(" ")[0])
    if id_comando is None:
        return f"`/{percorso}`"
    return f"</{percorso}:{id_comando}>"


def menziona_percorsi(testo: str, percorsi: Iterable[str], ids: Mapping[str, int]) -> str:
    """
    Ogni `/percorso` citato nel testo diventa una menzione cliccabile, solo a confine di
    parola: `/mod ban` non tocca `/mod banlist` né `/mod ban-lista`. Un solo passaggio, dal
    percorso più lungo, così una menzione già messa non si ritocca; i backtick intorno si tolgono.
    """
    nomi = sorted({p for p in percorsi if p}, key=len, reverse=True)
    if not nomi:
        return testo
    schema = re.compile(r"(?<![\w/])(`?)/(" + "|".join(re.escape(n) for n in nomi) + r")(?![\w-])\1")
    return schema.sub(lambda m: menzione(m.group(2), ids), testo)


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
    # Inglese (NF-06): stesse idee, con le parole che un utente inglese scrive davvero.
    ("ban", "kick", "expel", "remove", "throw"),
    ("silence", "mute", "timeout", "shush", "gag"),
    ("warn", "warning", "strike", "caution"),
    ("delete", "clear", "purge", "clean", "wipe"),
    ("poll", "vote", "survey"),
    ("remind", "reminder", "alarm"),
    ("music", "song", "play", "track", "tune"),
    ("rank", "level", "leaderboard", "xp", "experience", "points"),
    ("coins", "money", "economy", "shop", "store", "cash"),
    ("giveaway", "raffle", "draw", "prize"),
    ("report", "flag", "complaint"),
    ("help", "guide", "support", "instructions"),
    ("channel", "room", "chat"),
    ("role", "roles", "rank"),
    ("welcome", "greeting", "greet"),
    ("suggestion", "suggest", "idea", "proposal"),
    ("language", "lingua", "idioma", "locale"),
    ("privacy", "data", "gdpr", "dati", "erase", "forget"),
    ("ticket", "support", "assistance", "modmail"),
    ("backup", "restore", "ripristino", "copy"),
    ("premium", "pro", "subscription", "abbonamento", "upgrade"),
)


def _varianti(query: str) -> list[str]:
    parole = re.findall(r"[a-zàèéìòù0-9]+", query.lower())
    varianti = []
    for i, parola in enumerate(parole):
        if parola in _STOPWORD:
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
    if info.percorso_en and pulita == info.percorso_en.lower():
        return 10.0
    testi = [(info.percorso, info.descrizione)]
    if info.percorso_en:
        testi.append((info.percorso_en, info.descrizione_en))
    migliore = 0.0
    varianti = _varianti(pulita)
    for nome, descrizione in testi:
        migliore = max(migliore, score_command(pulita, nome, descrizione))
        for variante in varianti:
            migliore = max(migliore, 0.9 * score_command(variante, nome, descrizione, bonus_sottostringa=False))
    return migliore


def cerca(
    query: str, comandi: Sequence[ComandoInfo], limite: int = MAX_RISULTATI, soglia: float = 0.34
) -> list[ComandoInfo]:
    punti = [(_punteggio(query, c), c) for c in comandi]
    punti = [(p, c) for p, c in punti if p >= soglia]
    punti.sort(key=lambda t: (-t[0], t[1].percorso))
    return [c for _, c in punti[:limite]]


def mostra(c: ComandoInfo, lingua: str) -> tuple[str, str]:
    """(percorso, descrizione) da far vedere: in inglese se la lingua lo chiede e la traduzione c'è."""
    if lingua == "en" and c.percorso_en and c.descrizione_en:
        return c.percorso_en, c.descrizione_en
    return c.percorso, c.descrizione


def suggerimenti(
    query: str, comandi: Sequence[ComandoInfo], limite: int = MAX_SUGGERIMENTI, lingua: str = "it"
) -> list[tuple[str, str]]:
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
        percorso_mostrato, descrizione = mostra(c, lingua)
        risultato.append((f"/{percorso_mostrato} — {descrizione}"[:100], c.percorso))
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
        if all(memo[liv] for liv in c.livelli):
            visibili.append(c)
    return visibili


async def filtra_per_moduli(
    comandi: Iterable[ComandoInfo], attivo: Callable[[str], Awaitable[bool]]
) -> list[ComandoInfo]:
    """Toglie i comandi i cui moduli sono TUTTI spenti nel server. Senza moduli dichiarati il comando resta."""
    memo: dict[str, bool] = {}
    visibili = []
    for c in comandi:
        if not c.moduli:
            visibili.append(c)
            continue
        for nome in c.moduli:
            if nome not in memo:
                memo[nome] = bool(await attivo(nome))
        if any(memo[nome] for nome in c.moduli):
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


def _testo_opzioni(opzioni: Sequence[Opzione], lingua: str = "it") -> str:
    if not opzioni:
        return t("cerca_opzioni_nessuna", lingua)
    righe = []
    for o in opzioni[:MAX_OPZIONI_MOSTRATE]:
        sigla = t("cerca_obbligatoria" if o.obbligatoria else "cerca_facoltativa", lingua)
        righe.append(f"• `{o.nome}` ({sigla}) {_taglia(o.descrizione, 60)}".rstrip())
    if len(opzioni) > MAX_OPZIONI_MOSTRATE:
        righe.append(t("cerca_opzioni_altre", lingua, n=len(opzioni) - MAX_OPZIONI_MOSTRATE))
    return "\n".join(righe)


def embed_risultati(
    risultati: Sequence[ComandoInfo], ids: Mapping[str, int], query: str, lingua: str = "it"
) -> discord.Embed:
    embed = discord.Embed(
        title=_taglia(t("cerca_titolo", lingua, query=query), 256), color=discord.Color.blurple()
    )
    for c in risultati[:MAX_RISULTATI]:
        percorso_mostrato, descrizione = mostra(c, lingua)
        valore = f"{menzione(c.percorso, ids)}\n{_taglia(descrizione, 150)}\n{_testo_opzioni(c.opzioni, lingua)}"
        embed.add_field(name=_taglia(f"/{percorso_mostrato}", 256), value=_taglia(valore, 1024, False), inline=False)
    return embed


def embed_pannello(ultimo: str | None, ids: Mapping[str, int], *, in_dm: bool, lingua: str = "it") -> discord.Embed:
    righe = []
    if ultimo:
        righe.append(t("cerca_ultimo", lingua, comando=menzione(ultimo, ids)))
    else:
        righe.append(t("cerca_nessun_uso", lingua))
    righe.append(t("cerca_scegli", lingua))
    if in_dm:
        righe.append(t("cerca_in_dm", lingua))
    return discord.Embed(title=t("cerca_pannello_titolo", lingua), description="\n\n".join(righe), color=discord.Color.blurple())


def embed_categoria(
    gruppo: str, comandi: Sequence[ComandoInfo], ids: Mapping[str, int], indice: int, lingua: str = "it"
) -> tuple[discord.Embed, int, int]:
    pezzo, indice, totale = pagina(comandi, indice, COMANDI_PER_PAGINA)
    righe = [f"{menzione(c.percorso, ids)} — {_taglia(mostra(c, lingua)[1], 100)}" for c in pezzo]
    embed = discord.Embed(
        title=_taglia(f"📂 {gruppo}", 256),
        description=_taglia("\n".join(righe) or t("cerca_nessun_comando", lingua), 4096, False),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=t("cerca_pagina", lingua, i=indice + 1, n=totale))
    return embed, indice, totale


class CacheIdComandi:
    """
    ID dei comandi di primo livello, letti da Discord (`fetch_commands`) per le menzioni
    cliccabili. Si ricarica quando scade (`ttl`), quando serve un comando che manca
    (comando nuovo dopo una sync) non più spesso di ogni `attesa_minima` secondi. La lettura corre fuori dal lock, in un unico compito condiviso, e chi
    aspetta non supera `timeout` secondi: poi usa i vecchi ID (la lettura continua da sola).
    Un errore di Discord non solleva: restano i vecchi ID e si riprova dopo `attesa_minima`.
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
        self._lock = asyncio.Lock()
        self._compito: asyncio.Task | None = None

    async def _carica(self, fetch, adesso: float) -> None:
        try:
            self._ids = {c.name: c.id for c in await fetch()}
            self._caricata = adesso
        except Exception as exc:
            logger.warning("ID dei comandi non letti (%s): uso quelli vecchi.", type(exc).__name__)

    async def ottieni(self, fetch: Callable[[], Awaitable[Iterable]], serve: Iterable[str] = ()) -> dict[str, int]:
        async with self._lock:  # solo la decisione: nessuna chiamata a Discord qui dentro
            adesso = self._orologio()
            if self._compito is None or self._compito.done():
                scaduta = self._caricata is None or adesso - self._caricata >= self.ttl
                manca = any(n not in self._ids for n in serve)
                puo_tentare = self._tentativo is None or adesso - self._tentativo >= self.attesa_minima
                if puo_tentare and (scaduta or manca):
                    self._tentativo = adesso
                    self._compito = asyncio.ensure_future(self._carica(fetch, adesso))
            compito = self._compito if self._compito is not None and not self._compito.done() else None
        if compito is not None:
            try:
                await asyncio.wait_for(asyncio.shield(compito), timeout=self.timeout)
            except asyncio.TimeoutError:
                logger.warning("Lettura degli ID dei comandi lenta: uso quelli vecchi.")
        return dict(self._ids)

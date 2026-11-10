"""
core/music_sources.py
=====================
Registro delle fonti musicali: quali sono, come si riconosce un link, quali
chiavi servono (solo presenti sì/no, mai il valore), stato di ogni fonte e
circuito di pausa (8 s di attesa, 2 ripieghi, 3 errori = pausa di 10 minuti).
Spotify e Apple Music: le chiavi stanno su Lavalink; se il bot non le vede si prova
lo stesso e Lavalink decide (vedi FONTI_CHIAVI_SU_LAVALINK).
Funzioni coperte: SPEC §9.5, issue #126 (B1), D73
Dipende da: variabili d'ambiente MUSIC_SOURCES_ENABLED e chiavi delle fonti
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

TIMEOUT_SECONDI = 8
MAX_RIPIEGHI = 2
PAUSA_SECONDI = 600
ERRORI_DI_FILA = 3
FINESTRA_BLOCCO_SECONDI = 60
CODICI_BLOCCO = (401, 403, 429)
MAX_LUNGHEZZA_LINK = 300

STATO_OK = "ok"
STATO_SPENTA = "spenta"
STATO_SENZA_CHIAVI = "senza_chiavi"
STATO_IN_PAUSA = "in_pausa"

# Fonti con le chiavi lette da Lavalink (LavaSrc): se manca la chiave nell'.env del bot
# non le rifiutiamo, proviamo e vale la risposta di Lavalink.
FONTI_CHIAVI_SU_LAVALINK = ("spotify", "applemusic")

# Fonti accese se MUSIC_SOURCES_ENABLED non è impostata. Yandex, Tidal e Deezer: spente di base.
FONTI_DI_BASE = (
    "youtube", "soundcloud", "bandcamp", "http", "twitch", "vimeo", "spotify", "applemusic",
)


@dataclass(frozen=True)
class Fonte:
    nome: str
    etichetta: str
    tipo_provider: str  # nativa | plugin | metadati | diretta
    domini: tuple[str, ...] = ()
    # Gruppi alternativi di variabili: la fonte ha le chiavi se UN gruppo è tutto presente.
    chiavi: tuple[tuple[str, ...], ...] = ()


FONTI: dict[str, Fonte] = {
    f.nome: f
    for f in (
        Fonte("youtube", "YouTube", "plugin", ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be")),
        Fonte("soundcloud", "SoundCloud", "nativa", ("soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com")),
        Fonte("bandcamp", "Bandcamp", "nativa", ("bandcamp.com",)),
        Fonte("http", "Link diretti", "nativa"),
        Fonte("twitch", "Twitch", "nativa", ("twitch.tv", "www.twitch.tv")),
        Fonte("vimeo", "Vimeo", "nativa", ("vimeo.com", "www.vimeo.com")),
        Fonte("spotify", "Spotify", "metadati", ("open.spotify.com",),
              (("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"),)),
        Fonte("applemusic", "Apple Music", "metadati", ("music.apple.com",),
              (("APPLE_MUSIC_TOKEN",), ("APPLE_KEY_ID", "APPLE_TEAM_ID", "APPLE_PRIVATE_KEY_PATH"))),
        Fonte("tidal", "Tidal", "metadati", ("tidal.com", "www.tidal.com", "listen.tidal.com"), (("TIDAL_TOKEN",),)),
        # Deezer: solo metadati dall'API pubblica. Mai chiave di decifrazione né cookie (D73).
        Fonte("deezer", "Deezer", "metadati", ("deezer.com", "www.deezer.com")),
        Fonte("yandex", "Yandex Music", "diretta",
              ("music.yandex.ru", "music.yandex.com", "music.yandex.by", "music.yandex.kz", "music.yandex.uz"),
              (("YANDEX_MUSIC_TOKEN",),)),
    )
}


# --- chiavi e fonti accese -----------------------------------------------
def _tutte_le_variabili() -> list[str]:
    return [v for f in FONTI.values() for g in f.chiavi for v in g]


def chiavi_presenti(nome: str) -> bool:
    """Vero se la fonte non vuole chiavi o ne ha un gruppo completo. Mai il valore."""
    gruppi = FONTI[nome].chiavi
    if not gruppi:
        return True
    return any(all(os.environ.get(v, "").strip() for v in g) for g in gruppi)


def fonti_accese_dall_owner() -> set[str]:
    grezzo = os.environ.get("MUSIC_SOURCES_ENABLED", "").strip()
    if not grezzo:
        return set(FONTI_DI_BASE)
    return {p.strip().lower() for p in grezzo.split(",") if p.strip().lower() in FONTI}


def ripulisci(testo: str) -> str:
    """Toglie da un testo ogni valore di chiave presente nell'ambiente (per log e messaggi)."""
    for v in _tutte_le_variabili():
        valore = os.environ.get(v, "").strip()
        if len(valore) >= 4:
            testo = testo.replace(valore, "***")
    return testo


_CODICE = re.compile(r"\b(401|403|429)\b")


def codice_da_errore(testo: str) -> int | None:
    trovato = _CODICE.search(testo or "")
    return int(trovato.group(1)) if trovato else None


# --- circuito di pausa ----------------------------------------------------
@dataclass
class _Stato:
    di_fila: int = 0
    blocchi: list[float] = field(default_factory=list)
    fino: float = 0.0
    prova_in_corso: bool = False
    ultimo_errore: str = ""


class RegistroFonti:
    """Contatori in memoria per fonte (nessun database): vale per tutti i server."""

    def __init__(self) -> None:
        self._stati: dict[str, _Stato] = {}

    def reset(self) -> None:
        self._stati.clear()

    def _stato(self, nome: str) -> _Stato:
        return self._stati.setdefault(nome, _Stato())

    def ok(self, nome: str) -> None:
        stato = self._stato(nome)
        stato.di_fila, stato.blocchi, stato.fino, stato.prova_in_corso = 0, [], 0.0, False

    def errore(self, nome: str, testo: str, adesso: float | None = None, codice: int | None = None) -> None:
        adesso = time.monotonic() if adesso is None else adesso
        stato = self._stato(nome)
        stato.ultimo_errore = ripulisci(testo or "errore")[:100]
        stato.di_fila += 1
        pausa = stato.prova_in_corso or stato.di_fila >= ERRORI_DI_FILA
        if codice in CODICI_BLOCCO:
            stato.blocchi = [t for t in stato.blocchi if adesso - t <= FINESTRA_BLOCCO_SECONDI] + [adesso]
            pausa = pausa or len(stato.blocchi) >= 2
        if pausa:
            stato.di_fila, stato.blocchi, stato.prova_in_corso = 0, [], False
            stato.fino = adesso + PAUSA_SECONDI

    def in_pausa(self, nome: str, adesso: float | None = None) -> bool:
        adesso = time.monotonic() if adesso is None else adesso
        stato = self._stato(nome)
        return stato.fino > 0 and adesso < stato.fino

    def rilascia_prova(self, nome: str) -> None:
        """La richiesta di prova è finita senza esito (annullata, brano non trovato)."""
        self._stato(nome).prova_in_corso = False

    def puo_provare(self, nome: str, adesso: float | None = None) -> bool:
        """Fuori pausa sì; a pausa finita passa UNA sola richiesta di prova."""
        adesso = time.monotonic() if adesso is None else adesso
        stato = self._stato(nome)
        if stato.fino == 0:
            return True
        if adesso < stato.fino or stato.prova_in_corso:
            return False
        stato.prova_in_corso = True
        return True

    def ultimo_errore(self, nome: str) -> str:
        return self._stato(nome).ultimo_errore


registro = RegistroFonti()


def stato_fonte(nome: str, adesso: float | None = None) -> str:
    if nome not in fonti_accese_dall_owner():
        return STATO_SPENTA
    if not chiavi_presenti(nome):
        return STATO_SENZA_CHIAVI
    if registro.in_pausa(nome, adesso):
        return STATO_IN_PAUSA
    return STATO_OK


def prefissi_ricerca_testo() -> list[str]:
    """Dove cercare un titolo senza link: YouTube Music, poi SoundCloud (se usabili)."""
    prefissi = []
    if stato_fonte("youtube") == STATO_OK:
        prefissi.append("ytmsearch:")
    if stato_fonte("soundcloud") == STATO_OK:
        prefissi.append("scsearch:")
    return prefissi


# --- classificatore dei link ----------------------------------------------
@dataclass(frozen=True)
class LinkFonte:
    fonte: str
    tipo: str  # brano | album | playlist | artista | diretta


_SPOTIFY_URI = re.compile(r"^spotify:(track|album|playlist|artist):[A-Za-z0-9]{10,40}$")
_TIPI = {"track": "brano", "song": "brano", "album": "album", "playlist": "playlist", "artist": "artista"}
_P_SPOTIFY = re.compile(r"^/(?:intl-[a-z]{2,5}/)?(track|album|playlist|artist)/[A-Za-z0-9]{10,40}/?$")
_P_APPLE = re.compile(r"^/[a-z]{2}/(song|album|playlist|artist)/(?:[^/]+/)?[A-Za-z0-9.\-]+/?$")
_P_TIDAL = re.compile(r"^(?:/browse)?/(track|album|playlist|artist)/[A-Za-z0-9\-]+/?$")
_P_DEEZER = re.compile(r"^/(?:[a-z]{2}/)?(track|album|playlist|artist)/\d+/?$")
_P_YANDEX = re.compile(
    r"^/(?:album/\d+/(track)/\d+|(album)/\d+|(artist)/\d+|users/[^/]+/(playlists)/\d+)/?$"
)
_P_SOUNDCLOUD = re.compile(r"^/[^/]+/(sets/)?[^/]+/?$|^/[A-Za-z0-9]+/?$")
_P_BANDCAMP = re.compile(r"^/(track|album)/[^/]+/?$")
_P_TWITCH = re.compile(r"^/[A-Za-z0-9_]{3,25}/?$")
_P_VIMEO = re.compile(r"^/\d+/?$")


def _fonte_dell_host(host: str) -> str | None:
    for fonte in FONTI.values():
        if fonte.nome == "bandcamp":
            if host == "bandcamp.com" or host.endswith(".bandcamp.com"):
                return "bandcamp"
        elif host in fonte.domini:
            return fonte.nome
    return None


def _tipo_youtube(host: str, percorso: str, query: str) -> str | None:
    if host == "youtu.be":
        return "brano" if re.fullmatch(r"/[\w\-]{6,20}", percorso) else None
    if percorso.removeprefix("/") == "watch" and parse_qs(query).get("v"):
        return "brano"
    if percorso == "/playlist" and parse_qs(query).get("list"):
        return "playlist"
    if re.fullmatch(r"/shorts/[\w\-]{6,20}", percorso):
        return "brano"
    return None


def classifica_link(testo: str) -> LinkFonte | None:
    """
    Il link di una fonte nota: (fonte, tipo). None per tutto il resto (titoli, siti non
    noti = link diretti, http su un servizio noto, host solo simili, tipi non supportati).
    Solo https, host esatto, niente userinfo né porta; massimo 300 caratteri.
    """
    t = (testo or "").strip()
    if not t or len(t) > MAX_LUNGHEZZA_LINK:
        return None
    if _SPOTIFY_URI.match(t):
        return LinkFonte("spotify", _TIPI[t.split(":")[1]])
    try:
        url = urlparse(t)
    except ValueError:
        return None
    if url.scheme != "https" or not url.hostname:
        return None
    if "\\" in t or "@" in url.netloc or ":" in url.netloc:
        return None  # userinfo, porta o barra rovesciata: mai un link di fonte
    host, percorso = url.hostname.lower(), url.path or "/"
    nome = _fonte_dell_host(host)
    if nome is None:
        return None
    tipo = _tipo_del_percorso(nome, host, percorso, url.query)
    return LinkFonte(nome, tipo) if tipo else None


def _tipo_del_percorso(nome: str, host: str, percorso: str, query: str) -> str | None:
    if nome == "youtube":
        return _tipo_youtube(host, percorso, query)
    if nome == "soundcloud":
        if not _P_SOUNDCLOUD.match(percorso):
            return None
        return "playlist" if "/sets/" in percorso else "brano"
    if nome == "bandcamp":
        trovato = _P_BANDCAMP.match(percorso)
        return _TIPI[trovato.group(1)] if trovato else None
    if nome == "twitch":
        return "diretta" if _P_TWITCH.match(percorso) else None
    if nome == "vimeo":
        return "brano" if _P_VIMEO.match(percorso) else None
    if nome == "yandex":
        trovato = _P_YANDEX.match(percorso)
        if not trovato:
            return None
        parola = next(g for g in trovato.groups() if g)
        return {"track": "brano", "album": "album", "artist": "artista", "playlists": "playlist"}[parola]
    schema = {"spotify": _P_SPOTIFY, "applemusic": _P_APPLE, "tidal": _P_TIDAL, "deezer": _P_DEEZER}.get(nome)
    trovato = schema.match(percorso) if schema else None
    if not trovato:
        return None
    tipo = _TIPI[trovato.group(1)]
    if nome == "applemusic" and tipo == "album" and parse_qs(query).get("i"):
        return "brano"  # album?i=<id> è un singolo brano
    return tipo


# --- messaggi e ricerca ---------------------------------------------------
class FonteNonRisponde(Exception):
    """Nessuna fonte ha risposto in tempo (timeout o errori). Mai mostrare il testo tecnico."""

    def __init__(self, fonte: str = "") -> None:
        super().__init__(fonte)
        self.fonte = fonte


async def messaggio_per_fonte(fonte: str, guild_id: int | None = None, utente_id: int | None = None) -> str:
    """Il messaggio per l'utente (nella sua lingua) quando una fonte non si può usare."""
    from core.i18n import lingua_risposta, t

    lingua = await lingua_risposta(guild_id, utente_id)
    if fonte not in FONTI:
        return t("music_nessun_risultato_ora", lingua)
    chiave = "music_fonte_non_risponde" if _si_puo_provare(fonte) else "music_fonte_non_attiva"
    return t(chiave, lingua, fonte=FONTI[fonte].etichetta)


def _si_puo_provare(fonte: str) -> bool:
    """Accesa e con le chiavi (o chiavi lette da Lavalink). La pausa si guarda a parte."""
    stato = stato_fonte(fonte)
    return stato != STATO_SPENTA and (stato != STATO_SENZA_CHIAVI or fonte in FONTI_CHIAVI_SU_LAVALINK)


def fonte_usabile(fonte: str) -> bool:
    """Vero se la fonte è accesa, ha le chiavi e non è in pausa (a pausa finita passa una prova)."""
    return _si_puo_provare(fonte) and registro.puo_provare(fonte)


async def _con_circuito(fonte: str, esegui):
    try:
        risultato = await asyncio.wait_for(esegui(), TIMEOUT_SECONDI)
    except asyncio.CancelledError:
        registro.rilascia_prova(fonte)  # niente prova rimasta appesa
        raise
    except Exception as exc:
        if getattr(exc, "severity", "") == "common":
            registro.rilascia_prova(fonte)
            return []  # brano tolto o non trovato: non è un guasto della fonte
        testo = str(exc) or type(exc).__name__
        registro.errore(fonte, testo, codice=codice_da_errore(testo))
        raise FonteNonRisponde(fonte) from exc
    registro.ok(fonte)
    return risultato


async def cerca_link(fonte: str, esegui):
    """Esegue la ricerca di un link con timeout di 8 s e circuito. `esegui()` è una coroutine."""
    return await _con_circuito(fonte, esegui)


async def cerca_testo(testo: str, esegui_con_prefisso):
    """
    Cerca un titolo: YouTube Music, poi SoundCloud (al massimo 2 ripieghi, un solo giro).
    Un risultato vuoto NON è un errore. `esegui_con_prefisso(query)` è una coroutine.
    """
    prefissi = prefissi_ricerca_testo()[: MAX_RIPIEGHI + 1]
    nomi = {"ytmsearch:": "youtube", "scsearch:": "soundcloud"}
    for prefisso in prefissi:
        if not registro.puo_provare(nomi[prefisso]):
            continue  # pausa appena finita: la prova è già in corso
        try:
            return await _con_circuito(nomi[prefisso], lambda p=prefisso: esegui_con_prefisso(p + testo))
        except FonteNonRisponde:
            continue
    raise FonteNonRisponde("")


def righe_stato(lingua: str | None = None) -> list[str]:
    """Una riga per fonte per /owner radio fonti, nella lingua di chi legge. Chiavi solo sì/no."""
    from core.i18n import t

    righe = []
    for nome, fonte in FONTI.items():
        stato = stato_fonte(nome)
        if stato == STATO_SENZA_CHIAVI and nome in FONTI_CHIAVI_SU_LAVALINK:
            # Le chiavi stanno su Lavalink: il bot non le vede, ma la fonte si prova lo stesso.
            righe.append(t("music_stato_chiavi_su_lavalink", lingua, fonte=fonte.etichetta))
            continue
        if not fonte.chiavi:
            chiavi = t("music_chiavi_non_servono", lingua)
        else:
            chiavi = t("music_chiavi_si" if chiavi_presenti(nome) else "music_chiavi_no", lingua)
        riga = t("music_stato_riga", lingua, fonte=fonte.etichetta, stato=t(f"music_stato_{stato}", lingua), chiavi=chiavi)
        errore = registro.ultimo_errore(nome)
        if errore and stato == STATO_IN_PAUSA:
            riga += " " + t("music_stato_ultimo_errore", lingua, errore=errore)
        righe.append(riga)
    return righe

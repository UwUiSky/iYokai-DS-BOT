"""
core/controllo_link.py
======================
Il punto unico per giudicare un link (AMD-030, D111): `valuta(url)` dà sicuro, sospetto o pericoloso, con fonte e
categoria. Usato dall'AutoMod («Link pericolosi») e da chi pubblica link scritti da utenti (embed, annunci, alert,
tag, saluti). Ordine: domini ufficiali e whitelist, liste locali e scaricate, euristica, poi i servizi con chiave
(Google, Cloudflare, VirusTotal). Cache con scadenza, tetti per servizio, nessuna chiamata bloccante. Nei log mai l'URL intero.
Funzioni coperte: SPEC §6.21 (AMD-030, D111, D112)
Dipende da: core/controllo_link_liste.py, core/controllo_link_servizi.py, core/phishing_logic.py, core/safe_http.py
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import parse_qs

from yarl import URL

from core import controllo_link_servizi as servizi
from core import safe_http
from core.bounded_cache import BoundedCache
from core.controllo_link_liste import stato as liste
from core.controllo_link_servizi import PERICOLOSO, SICURO, SOSPETTO

logger = logging.getLogger("iyokai.controllo_link")

MAX_URL = 2048
MAX_LINK_PER_MESSAGGIO = 5  # ogni link costa quota: gli altri non si controllano
DURATA_CACHE = {PERICOLOSO: 6 * 3600, SOSPETTO: 3600, SICURO: 3600}
DURATA_CACHE_ERRORE = 120  # servizi senza risposta: si riprova presto
_cache: BoundedCache[str, tuple[float, "Esito"]] = BoundedCache(20_000)
_salti_al_minuto: list[float] = []
MAX_SALTI_AL_MINUTO = 30  # redirect degli accorciatori seguiti per minuto, in tutto il bot

# Siti che rimandano a un indirizzo scritto nei parametri: l'indirizzo vero sta nel parametro, senza richieste di rete.
_RIMANDI = {
    "google.com": ("url", ("q", "url")),
    "l.facebook.com": ("l.php", ("u",)),
    "lm.facebook.com": ("l.php", ("u",)),
    "discord.com": ("linkfilter", ("url",)),
}


@dataclass(frozen=True)
class Esito:
    livello: str
    fonte: str = ""
    categoria: str = ""
    dominio: str = ""

    @property
    def e_pericoloso(self) -> bool:
        return self.livello == PERICOLOSO

    @property
    def e_sospetto(self) -> bool:
        return self.livello == SOSPETTO


def normalizza(url: str) -> URL | None:
    """URL pulito: schema http/https, host in minuscolo e punycode, niente utente né frammento. None se non è un link valido."""
    testo = (url or "").strip().strip("<>")
    if not testo or len(testo) > MAX_URL:
        return None
    if "://" not in testo:
        testo = "https://" + testo
    try:
        grezzo = URL(testo)
        if grezzo.scheme not in ("http", "https") or not grezzo.raw_host:
            return None
        host = grezzo.raw_host.lower().rstrip(".")
        host = host.encode("ascii").decode() if host.isascii() else host.encode("idna").decode()
        return grezzo.with_user(None).with_host(host).with_fragment(None)
    except (ValueError, UnicodeError):
        return None


def scarta_rimando(url: URL) -> URL:
    """Se è un rimando noto (google.com/url?q=...), l'indirizzo vero dentro il parametro. Altrimenti lo stesso URL."""
    host = (url.raw_host or "").removeprefix("www.")
    regola = _RIMANDI.get(host)
    if regola and url.path.lstrip("/") == regola[0]:
        valori = parse_qs(url.raw_query_string)
        for nome in regola[1]:
            if valori.get(nome):
                interno = normalizza(valori[nome][0])
                if interno is not None:
                    return interno
    return url


async def _risolvi_accorciatore(url: URL, segui) -> URL:
    """Segue un accorciatore noto con safe_http (tetto globale al minuto). Se non riesce resta l'URL di partenza."""
    from core.phishing_logic import ACCORCIATORI, lista_siti

    host = (url.raw_host or "").removeprefix("www.")
    if host not in ACCORCIATORI or host in lista_siti("ip_logger"):  # un sito che cattura l'IP non si visita mai
        return url
    adesso = time.monotonic()
    _salti_al_minuto[:] = [t for t in _salti_al_minuto if adesso - t < 60]
    if len(_salti_al_minuto) >= MAX_SALTI_AL_MINUTO:
        return url
    _salti_al_minuto.append(adesso)
    finale = await segui(str(url))
    arrivo = normalizza(finale) if finale else None
    return arrivo if arrivo is not None else url


def _giudizio_locale(host: str, consentiti: tuple[str, ...]) -> Esito | None:
    from core.automod_advanced_logic import normalize_domain
    from core.phishing_logic import carica_lista_locale, e_phishing, e_sito_pericoloso, sembra_phishing

    trovato = liste.cerca(host)
    if trovato is not None:
        fonte, categoria = trovato
        return Esito(PERICOLOSO, fonte, categoria, host)
    if e_phishing([host], carica_lista_locale(), consentiti=consentiti):
        return Esito(PERICOLOSO, "lista_locale", "phishing", host)
    if e_sito_pericoloso([host], ("malware",), consentiti=consentiti):
        return Esito(PERICOLOSO, "lista_locale", "malware", host)
    if e_sito_pericoloso([host], ("ip_logger",), consentiti=consentiti):
        return Esito(SOSPETTO, "lista_locale", "ip_logger", host)
    if sembra_phishing(normalize_domain(host)):
        return Esito(SOSPETTO, "euristica", "phishing", host)
    return None


async def valuta(
    url: str,
    *,
    consentiti: tuple[str, ...] = (),
    chiavi: servizi.Chiavi | None = None,
    richiesta=safe_http.safe_richiesta,
    segui=safe_http.safe_segui_redirect,
) -> Esito:
    """Giudica un link. Non solleva mai: un servizio che non risponde conta come «nessun parere»."""
    from core.automod_advanced_logic import normalize_domain
    from core.phishing_logic import _ufficiale

    pulito = normalizza(url)
    if pulito is None:
        return Esito(SICURO, "ignorato")
    pulito = scarta_rimando(pulito)
    pulito = await _risolvi_accorciatore(pulito, segui)
    host = pulito.raw_host or ""
    chiave_cache = f"{pulito.scheme}://{host}{pulito.raw_path}?{pulito.raw_query_string}"[:MAX_URL]
    voce = _cache.get(chiave_cache)
    if voce is not None and voce[0] > time.monotonic():
        return voce[1]

    liste.aggiorna_se_serve()
    consentiti_n = tuple(normalize_domain(c) for c in consentiti)
    if any(host == c or host.endswith("." + c) for c in consentiti_n if c) or _ufficiale(host):
        return Esito(SICURO, "ufficiale", "", host)  # niente quota spesa per discord.com o per la whitelist

    esito = _giudizio_locale(host, consentiti)
    scadenza = DURATA_CACHE_ERRORE
    if esito is None or esito.livello != PERICOLOSO:
        esito, scadenza = await _chiedi_ai_servizi(str(pulito), host, esito, chiavi or servizi.chiavi_da_config(), richiesta)
    else:
        scadenza = DURATA_CACHE[PERICOLOSO]
    _cache.set(chiave_cache, (time.monotonic() + scadenza, esito))
    if esito.livello != SICURO:
        logger.info("Link %s: %s (%s, %s).", esito.livello, host, esito.fonte, esito.categoria)
    return esito


async def _chiedi_ai_servizi(url: str, host: str, locale: Esito | None, k: servizi.Chiavi, richiesta) -> tuple[Esito, int]:
    """Interroga i servizi accesi, uno dopo l'altro e fermandosi al primo «pericoloso». Torna (esito, secondi di cache)."""
    migliore = locale or Esito(SICURO, "", "", host)
    risposte = 0
    tentativi = (
        ("google", lambda: servizi.google_safe_browsing(url, k.google, richiesta)),
        ("cloudflare", lambda: servizi.cloudflare_intel(host, k.cloudflare_token, k.cloudflare_account, richiesta)),
        ("virustotal", lambda: servizi.virustotal(host, k.virustotal, richiesta)),
    )
    for nome, chiama in tentativi:
        try:
            parere = await chiama()
        except Exception as errore:  # noqa: BLE001  # un servizio rotto non ferma gli altri
            logger.warning("Servizio %s: errore %s.", nome, type(errore).__name__)
            continue
        if parere is None:
            continue
        risposte += 1
        livello, categoria = parere
        if livello == PERICOLOSO:
            return Esito(PERICOLOSO, nome, categoria, host), DURATA_CACHE[PERICOLOSO]
        if livello == SOSPETTO and migliore.livello == SICURO:
            migliore = Esito(SOSPETTO, nome, categoria, host)
    # Nessun servizio acceso o nessuna risposta: giudizio locale, riprovo presto.
    return migliore, DURATA_CACHE[migliore.livello] if risposte else DURATA_CACHE_ERRORE


def link_nel_testo(testo: str, massimo: int = MAX_LINK_PER_MESSAGGIO) -> tuple[str, ...]:
    """I link http/https di un testo, senza doppioni e senza punteggiatura finale, al massimo `massimo`."""
    from core.automod_advanced_logic import _URL_PATTERN

    visti: list[str] = []
    for grezzo in _URL_PATTERN.findall(testo or ""):
        link = grezzo.rstrip(".,;:!?)]}>*_~|")
        if link not in visti:
            visti.append(link)
        if len(visti) >= massimo:
            break
    return tuple(visti)


async def primo_pericoloso(testo: str, *, anche_sospetti: bool = False, consentiti: tuple[str, ...] = ()) -> Esito | None:
    """AutoMod e annunci: l'esito del primo link pericoloso (o sospetto, se richiesto) nel testo; None se va bene."""
    for link in link_nel_testo(testo):
        esito = await valuta(link, consentiti=consentiti)
        if esito.e_pericoloso or (anche_sospetti and esito.e_sospetto):
            return esito
    return None


SEGNO_BLOCCATO = "⛔ link bloccato"


async def togli_link_pericolosi(testo: str, *, consentiti: tuple[str, ...] = ()) -> tuple[str, int]:
    """Per chi pubblica testo di utenti (tag, risposte automatiche, voci di feed): ogni link pericoloso diventa «⛔ link bloccato».
    Torna (testo nuovo, quanti link tolti). Si guardano al massimo MAX_LINK_PER_MESSAGGIO link."""
    tolti = 0
    for link in link_nel_testo(testo):
        if (await valuta(link, consentiti=consentiti)).e_pericoloso:
            testo = testo.replace(link, SEGNO_BLOCCATO)
            tolti += 1
    return testo, tolti


async def e_link_pericoloso(url: str, *, consentiti: tuple[str, ...] = ()) -> bool:
    """True se `valuta` giudica il link pericoloso. Per chi ha già controllato l'indirizzo con `url_e_sicuro`."""
    return (await valuta(url, consentiti=consentiti)).e_pericoloso


async def url_pubblicabile(url: str) -> bool:
    """Per chi pubblica un link scritto da un utente: raggiungibile in sicurezza (SSRF) e non pericoloso."""
    if not await safe_http.url_e_sicuro(url):
        return False
    return not (await valuta(url)).e_pericoloso


def svuota_cache() -> None:
    """Per i test."""
    _cache.clear()
    _salti_al_minuto.clear()

"""
core/controllo_link_liste.py
============================
Liste pubbliche di siti pericolosi (URLhaus, Phishing Army, OpenPhish, Phishing.Database, e le liste italiane
AGCOM e ADM se l'owner mette l'indirizzo): scaricate con core/safe_http, tetto di byte, cache su disco,
al massimo un giro ogni 12 ore. Senza rete restano le liste del disco. Ogni fonte si spegne da sola se fallisce.
Funzioni coperte: SPEC §6.21 (AMD-030, D111, D112)
Dipende da: core/safe_http.py, core/phishing_logic.py (normalizzazione dei domini)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from core import safe_http

logger = logging.getLogger("iyokai.controllo_link")

INTERVALLO_SECONDI = 12 * 3600
MAX_BYTE_LISTA = 8 * 1024 * 1024
MAX_DOMINI_PER_FONTE = 400_000
CARTELLA_BASE = Path(__file__).resolve().parent.parent / "data" / "cache_liste"
VARIABILE_ATTIVE = "LINK_LISTE_ATTIVE"
VARIABILE_CARTELLA = "LINK_LISTE_CARTELLA"

CATEGORIA_PHISHING = "phishing"
CATEGORIA_MALWARE = "malware"
CATEGORIA_PIRATERIA = "pirateria"
CATEGORIA_GIOCO = "gioco_azzardo"

_DOMINIO = re.compile(r"^(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?\.)+[a-z0-9-]{2,63}$")
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


@dataclass(frozen=True)
class FonteLista:
    """Una lista scaricabile. `formato`: «domini» (uno per riga), «url» (un URL per riga), «hosts» (riga «0.0.0.0 dominio»)."""

    nome: str
    url: str
    categoria: str
    formato: str
    licenza: str
    variabile_url: str = ""  # se c'è, l'indirizzo viene da questa variabile (liste italiane)


FONTI: tuple[FonteLista, ...] = (
    FonteLista("urlhaus", "https://urlhaus.abuse.ch/downloads/text_online/", CATEGORIA_MALWARE, "url", "CC0 1.0 (abuse.ch)"),
    FonteLista(
        "phishing_army", "https://phishing.army/download/phishing_army_blocklist.txt", CATEGORIA_PHISHING, "domini",
        "CC BY-NC 4.0 (solo uso non commerciale)",
    ),
    FonteLista("openphish", "https://openphish.com/feed.txt", CATEGORIA_PHISHING, "url", "feed gratuito OpenPhish (uso non commerciale)"),
    FonteLista(
        "phishing_database",
        "https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database/master/phishing-domains-ACTIVE.txt",
        CATEGORIA_PHISHING, "domini", "MIT (Phishing.Database)",
    ),
    FonteLista("agcom", "", CATEGORIA_PIRATERIA, "domini", "dati pubblici AGCOM: l'indirizzo lo sceglie l'owner", "LINK_LISTA_AGCOM_URL"),
    FonteLista("adm", "", CATEGORIA_GIOCO, "domini", "dati pubblici ADM: l'indirizzo lo sceglie l'owner", "LINK_LISTA_ADM_URL"),
)
NOMI_DI_PARTENZA = ("urlhaus", "phishing_army", "openphish", "phishing_database", "agcom", "adm")


def fonti_attive() -> tuple[FonteLista, ...]:
    """Le fonti accese: `LINK_LISTE_ATTIVE` (nomi separati da virgola, «nessuna» le spegne), di base tutte; senza indirizzo non scarica."""
    grezzo = os.environ.get(VARIABILE_ATTIVE, "").strip().lower()
    scelte = set(NOMI_DI_PARTENZA) if not grezzo else {n.strip() for n in grezzo.split(",")}
    return tuple(f for f in FONTI if f.nome in scelte and _indirizzo(f))


def _indirizzo(fonte: FonteLista) -> str:
    url = os.environ.get(fonte.variabile_url, "").strip() if fonte.variabile_url else fonte.url
    return url if url.startswith("https://") else ""


def pulisci_dominio(grezzo: str) -> str:
    """Un dominio valido in minuscolo (senza www., punto finale, IP), oppure ''."""
    d = grezzo.strip().lower().rstrip(".")
    if d.startswith("www."):
        d = d[4:]
    if not d or len(d) > 253 or _IPV4.match(d) or not _DOMINIO.match(d):
        return ""
    return d


def interpreta(corpo: str, formato: str) -> frozenset[str]:
    """I domini di una lista scaricata. Righe vuote, commenti e voci non valide si scartano; tetto MAX_DOMINI_PER_FONTE."""
    trovati: set[str] = set()
    for riga in corpo.splitlines():
        riga = riga.strip()
        if not riga or riga[0] in "#!;[":
            continue
        if formato == "url":
            host = urlparse(riga if "://" in riga else "http://" + riga).hostname or ""
        elif formato == "hosts":
            pezzi = riga.split()
            host = pezzi[-1] if len(pezzi) >= 2 else ""
        else:
            primo = riga.split()[0]
            host = (urlparse(primo).hostname or "") if "://" in primo else primo.split("/")[0]
        dominio = pulisci_dominio(host)
        if dominio:
            trovati.add(dominio)
            if len(trovati) >= MAX_DOMINI_PER_FONTE:
                break
    return frozenset(trovati)


def _cartella() -> Path:
    scelta = os.environ.get(VARIABILE_CARTELLA, "").strip()
    return Path(scelta) if scelta else CARTELLA_BASE


def _catena(dominio: str) -> list[str]:
    parti = dominio.split(".")
    return [".".join(parti[i:]) for i in range(len(parti) - 1)] or [dominio]


class StatoListe:
    """Le liste in memoria. Si legge e si scrive solo qui; la ricerca è un confronto tra insiemi (veloce, nessuna rete)."""

    def __init__(self) -> None:
        self._per_fonte: dict[str, frozenset[str]] = {}
        self._categorie: dict[str, frozenset[str]] = {}
        self._letto_da_disco = False
        self._ultimo_giro = 0.0
        self._compito: asyncio.Task | None = None

    def imposta(self, nome: str, domini: frozenset[str]) -> None:
        self._per_fonte[nome] = domini
        self._categorie.clear()
        self._avvisa_liste_collegate()

    def categoria(self, categoria: str) -> frozenset[str]:
        if categoria not in self._categorie:
            nomi = {f.nome for f in FONTI if f.categoria == categoria}
            unite: set[str] = set()
            for nome in nomi:
                unite |= self._per_fonte.get(nome, frozenset())
            self._categorie[categoria] = frozenset(unite)
        return self._categorie[categoria]

    def cerca(self, dominio: str) -> tuple[str, str] | None:
        """(fonte, categoria) se il dominio o un suo dominio padre sta in una lista, altrimenti None."""
        catena = _catena(dominio)
        for fonte in FONTI:
            insieme = self._per_fonte.get(fonte.nome)
            if insieme and any(d in insieme for d in catena):
                return fonte.nome, fonte.categoria
        return None

    def svuota(self) -> None:
        self._per_fonte.clear()
        self._categorie.clear()
        self._letto_da_disco = False
        self._ultimo_giro = 0.0
        self._avvisa_liste_collegate()

    @staticmethod
    def _avvisa_liste_collegate() -> None:
        """La lista dei malware di AMD-031 (data/siti_malware.txt) si riempie anche da qui: si rilegge al prossimo uso."""
        try:
            from core import phishing_logic

            phishing_logic._liste_siti.pop("malware", None)
        except Exception:  # noqa: BLE001  # mai far fallire una lista per un'altra
            logger.warning("Lista dei malware non aggiornata.")

    def carica_da_disco(self) -> None:
        """Legge le liste già scaricate (chiamata in un thread). Una lista rotta si salta."""
        for fonte in FONTI:
            percorso = _cartella() / f"{fonte.nome}.txt"
            try:
                if percorso.is_file() and percorso.stat().st_size <= MAX_BYTE_LISTA:
                    self._per_fonte[fonte.nome] = interpreta(percorso.read_text(encoding="utf-8", errors="ignore"), "domini")
            except OSError:
                logger.warning("Lista %s non letta dal disco.", fonte.nome)
        self._categorie.clear()
        self._letto_da_disco = True
        self._avvisa_liste_collegate()

    async def scarica_fonte(self, fonte: FonteLista) -> bool:
        """Scarica una fonte con safe_http. True se la lista nuova è valida e ha preso il posto della vecchia."""
        url = _indirizzo(fonte)
        if not url:
            return False
        corpo = await safe_http.safe_get(url, max_bytes=MAX_BYTE_LISTA)
        if not corpo:
            logger.warning("Lista %s non scaricata (resta quella di prima).", fonte.nome)
            return False
        domini = interpreta(corpo, fonte.formato)
        if len(domini) < 10 and fonte.nome not in ("agcom", "adm"):
            logger.warning("Lista %s sospetta (troppo corta): ignorata.", fonte.nome)
            return False
        self.imposta(fonte.nome, domini)
        await asyncio.to_thread(self._salva, fonte.nome, domini)
        return True

    @staticmethod
    def _salva(nome: str, domini: frozenset[str]) -> None:
        cartella = _cartella()
        try:
            cartella.mkdir(parents=True, exist_ok=True)
            provvisorio = cartella / f"{nome}.txt.tmp"
            provvisorio.write_text("\n".join(sorted(domini)) + "\n", encoding="utf-8")
            os.replace(provvisorio, cartella / f"{nome}.txt")
        except OSError:
            logger.warning("Lista %s non salvata su disco.", nome)

    async def aggiorna(self) -> int:
        """Rilegge il disco la prima volta, poi scarica le fonti accese una dopo l'altra. Quante ne sono riuscite."""
        if not self._letto_da_disco:
            await asyncio.to_thread(self.carica_da_disco)
        riuscite = 0
        for fonte in fonti_attive():
            try:
                if await self.scarica_fonte(fonte):
                    riuscite += 1
            except Exception as errore:  # noqa: BLE001  # una fonte rotta non ferma le altre
                logger.warning("Lista %s: errore %s.", fonte.nome, type(errore).__name__)
        return riuscite

    def aggiorna_se_serve(self) -> None:
        """Lancia il giro in sottofondo se è passato l'intervallo; torna subito, mai bloccante."""
        adesso = time.monotonic()
        if self._compito is not None and not self._compito.done():
            return
        if self._letto_da_disco and not fonti_attive():
            return
        if self._ultimo_giro and adesso - self._ultimo_giro < INTERVALLO_SECONDI:
            return
        try:
            ciclo = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._ultimo_giro = adesso
        self._compito = ciclo.create_task(self.aggiorna())


stato = StatoListe()

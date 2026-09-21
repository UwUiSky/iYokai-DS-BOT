"""
core/feed_parsing_logic.py
==============================
Logica pura di Custom RSS/Alert (SPEC.md §10.3, §10.7, §10.8).
Decisione tecnica presa per questa sezione: lo schema originale
chiedeva EventSub (Twitch) e PubSubHubbub (YouTube), entrambi
webhook PUSH — richiedono un endpoint HTTPS pubblico raggiungibile
da Twitch/Google, che questo bot non ha (nessun server web, verificato
prima di scrivere questo file — solo un client Gateway Discord).
Aggiungerlo significherebbe dominio, certificato TLS, apertura di
una porta sulla VM: un cambio di infrastruttura, non solo di codice.

Invece: POLLING periodico (stesso principio già usato per Memory
Guard, Event Log Retention, Escalation), su feed RSS/Atom che
YouTube e Reddit espongono NATIVAMENTE, senza bisogno di nessuna
chiave API:
  - YouTube: https://www.youtube.com/feeds/videos.xml?channel_id=XXX
  - Reddit:  https://www.reddit.com/r/nomesubreddit/new/.rss
             https://www.reddit.com/user/nomeutente/.rss
Un URL RSS/Atom qualsiasi (§10.8) funziona con lo stesso identico
meccanismo — YouTube e Reddit non sono casi speciali, sono solo due
fonti che già parlano RSS/Atom.

Nessuna rete qui dentro: il download del feed vive nel cog (aiohttp,
già disponibile tramite discord.py), qui solo il parsing del testo
XML già scaricato e la logica di "cos'è nuovo".
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass(frozen=True)
class FeedEntry:
    entry_id: str
    title: str
    link: str


def parse_feed(xml_text: str) -> list[FeedEntry]:
    """
    Analizza sia RSS 2.0 (<rss><channel><item>) sia Atom
    (<feed><entry>) — le due famiglie di formati che coprono
    praticamente ogni fonte RSS reale, incluse quelle native di
    YouTube e Reddit (entrambe Atom). Un feed malformato o di un
    formato non riconosciuto restituisce una lista vuota, non
    solleva — un feed esterno rotto non deve far fallire il ciclo di
    polling per tutti gli altri feed configurati.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    tag_pulito = root.tag.rsplit("}", 1)[-1]
    if tag_pulito == "rss":
        return _parse_rss(root)
    if tag_pulito == "feed":
        return _parse_atom(root)
    return []


def _testo_o_default(elemento, default: str = "") -> str:
    if elemento is None or elemento.text is None:
        return default
    return elemento.text.strip()


def _parse_rss(root: ET.Element) -> list[FeedEntry]:
    canale = root.find("channel")
    if canale is None:
        return []

    voci = []
    for item in canale.findall("item"):
        link = _testo_o_default(item.find("link"))
        entry_id = _testo_o_default(item.find("guid")) or link
        if not entry_id:
            continue  # senza un ID univoco non possiamo distinguerlo dai già visti
        voci.append(
            FeedEntry(
                entry_id=entry_id,
                title=_testo_o_default(item.find("title"), "(senza titolo)"),
                link=link,
            )
        )
    return voci


def _parse_atom(root: ET.Element) -> list[FeedEntry]:
    voci = []
    for entry in root.findall("atom:entry", ATOM_NS):
        link_el = entry.find("atom:link", ATOM_NS)
        link = link_el.get("href", "") if link_el is not None else ""
        entry_id = _testo_o_default(entry.find("atom:id", ATOM_NS)) or link
        if not entry_id:
            continue
        voci.append(
            FeedEntry(
                entry_id=entry_id,
                title=_testo_o_default(entry.find("atom:title", ATOM_NS), "(senza titolo)"),
                link=link,
            )
        )
    return voci


def find_new_entries(
    entries: list[FeedEntry], last_seen_entry_id: str | None
) -> list[FeedEntry]:
    """
    Voci NUOVE dall'ultimo controllo, nell'ordine del feed (di
    solito più recente per primo), fino a incontrare l'ultimo ID già
    visto.

    last_seen_entry_id=None (primo controllo mai fatto su questo
    feed) restituisce SEMPRE lista vuota: altrimenti il primo
    controllo pubblicherebbe l'intero storico del feed in un colpo
    solo, spammando il canale configurato — il chiamante deve solo
    memorizzare l'ID più recente come "visto", senza pubblicare
    nulla la prima volta.
    """
    if last_seen_entry_id is None:
        return []

    nuove = []
    for entry in entries:
        if entry.entry_id == last_seen_entry_id:
            break
        nuove.append(entry)
    return nuove


def render_alert_message(template: str, label: str, title: str, link: str) -> str:
    """
    Sostituisce {label}/{title}/{link} nel template personalizzabile
    (SPEC.md §10.9). Un placeholder sconosciuto nel template (typo
    dell'utente, es. {titolo} invece di {title}) non deve far fallire
    l'invio dell'alert — meglio un messaggio col template originale
    lasciato così com'è (il typo resta visibile, l'utente lo nota e
    lo corregge) che nessun messaggio.
    """
    try:
        return template.format(label=label, title=title, link=link)
    except (KeyError, IndexError):
        return template

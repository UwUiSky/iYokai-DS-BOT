"""
core/alert_piattaforme_logic.py
===============================
Scorciatoie che costruiscono l'indirizzo di un feed per piattaforme senza una interfaccia dedicata:
Bluesky (ALR-006), subreddit (ALR-014, 016), notizie di anime e manga (ALR-015), giochi gratis (ALR-017).
Solo testo: nessuna rete qui. Funzioni coperte: SPEC §10.8 (#129 ALR-006, 014, 015, 016, 017)
"""

from __future__ import annotations

import re

_HANDLE_BLUESKY = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]([a-z0-9-]{0,61}[a-z0-9])?$")
_SUBREDDIT = re.compile(r"^[A-Za-z0-9_]{3,21}$")

# Feed noti, scelti dall'owner del bot (ALR-015, 017). Chiave: nome nel comando.
FEED_NOTI: dict[str, tuple[str, str]] = {
    "anime-news": ("https://www.animenewsnetwork.com/all/rss.xml", "Notizie di anime e manga (Anime News Network)"),
    "mal-news": ("https://myanimelist.net/rss/news.xml", "Notizie di MyAnimeList"),
    "manga-uscite": ("https://www.mangaupdates.com/rss.php", "Nuovi capitoli e uscite manga (MangaUpdates)"),
    "anime-reddit": ("https://www.reddit.com/r/anime/new/.rss", "Discussioni nuove su r/anime"),
    "giochi-gratis": ("https://www.gamerpower.com/rss", "Giochi e contenuti gratis del momento (GamerPower)"),
    "giochi-gratis-reddit": ("https://www.reddit.com/r/FreeGameFindings/new/.rss", "Offerte gratis trovate su r/FreeGameFindings"),
}
# ALR-016: «comando di ricerca come avviso periodico» solo per sorgenti sicure: subreddit scelti, mai testo libero verso altri siti.
SUBREDDIT_SICURI = ("memes", "aww", "earthporn", "wholesomememes", "mildlyinteresting", "showerthoughts", "todayilearned", "space")


def indirizzo_bluesky(testo: str) -> str | None:
    """«@nome.bsky.social» o l'indirizzo del profilo -> il feed RSS del profilo; None se non è un handle valido."""
    t = (testo or "").strip().lower().removeprefix("@")
    t = re.sub(r"^https?://bsky\.app/profile/", "", t).split("/")[0].split("?")[0]
    if not _HANDLE_BLUESKY.match(t):
        return None
    return "/".join(("https://bsky.app/profile", t, "rss"))


def indirizzo_subreddit(nome: str, solo_sicuri: bool = False) -> str | None:
    """Feed dei post nuovi di un subreddit. Con `solo_sicuri` solo quelli dell'elenco (avviso periodico di immagini)."""
    n = (nome or "").strip().lower().removeprefix("r/").removeprefix("/r/")
    if not _SUBREDDIT.match(n):
        return None
    if solo_sicuri and n not in SUBREDDIT_SICURI:
        return None
    return f"https://www.reddit.com/r/{n}/new/.rss"


def nome_picarto_valido(testo: str) -> str | None:
    t = (testo or "").strip().lower()
    t = re.sub(r"^(https?://)?(www\.)?picarto\.tv/", "", t).strip("/")
    return t if re.fullmatch(r"[a-z0-9_]{2,40}", t) else None

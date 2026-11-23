"""
core/web_panel_pubblico.py
==========================
Ciò che un server può rendere pubblico dal pannello web, senza rete né Discord vero:
- statistiche pubbliche (STA-012), con la lista dei membri a parte e l'anonimato di STA-028 (chi ha scelto di
  essere anonimo compare come «utente anonimo»; si mostrano solo canali che @everyone può vedere);
- classifica XP su pagina web con indirizzo breve scelto dal server (LIV-062): validato, unico, senza nomi riservati;
- chiave per l'API di sola lettura (STA-061): si mostra una sola volta, si salva solo l'impronta SHA-256.
Funzioni coperte: SPEC §24.8 (STA-012, STA-028, LIV-062, STA-061; issue #130, #124)
Dipende da: core/repositories/web_panel_pubblico_repo.py, core/repositories/activity_stats_repo.py,
core/repositories/leveling_repo.py
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import date, timedelta

from core.config_schema import ImpostazioneNonValida

ANONIMO = "utente anonimo"
GIORNI_STATISTICHE = 30
RIGHE_CLASSIFICA_PUBBLICA = 10
RIGHE_CLASSIFICA_WEB = 50
RIGHE_NEGOZIO_WEB = 50  # ECO-080
SETTING_NEGOZIO_WEB = "negozio_web"  # ECO-080: spento di base, lo accende lo staff
PREFISSO_CHIAVE = "iyk_"
LUNGHEZZA_VISIBILE_PREFISSO = 8  # «iyk_» + 4 caratteri: basta a riconoscerla, non a indovinarla

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")
# Nomi che il sito usa o potrebbe usare, e nomi che farebbero credere di essere il bot o Discord.
NOMI_RISERVATI = frozenset({
    "admin", "api", "accedi", "callback", "esci", "server", "static", "wiki", "privacy", "termini", "proprietario",
    "miei-dati", "miei-inviti", "invito", "verifica", "allegato", "attivita", "stats", "statistiche", "classifica",
    "iyokai", "yokai", "bot", "discord", "everyone", "here", "owner", "staff", "support", "help", "login", "logout",
    "oauth", "www", "home", "index", "status", "premium", "marchio", "desktop", "app",
})


def valida_slug(testo: str) -> str:
    """L'indirizzo breve pronto da salvare (minuscolo). Storto = ImpostazioneNonValida."""
    slug = (testo or "").strip().lower()
    if not slug.isascii() or not _SLUG.match(slug) or "--" in slug:
        raise ImpostazioneNonValida("L'indirizzo ha da 3 a 32 caratteri: lettere, numeri e trattini (non all'inizio, non alla fine, non doppi).")
    if slug in NOMI_RISERVATI or slug.startswith(("iyokai", "discord")) or slug.isdigit():
        raise ImpostazioneNonValida("Questo indirizzo non è disponibile: sceglierne un altro.")
    return slug


async def imposta_slug(guild_id: int, testo: str, changed_by: int | None) -> str | None:
    """Pubblica la classifica a questo indirizzo; testo vuoto = non più pubblica. Ritorna l'indirizzo o None."""
    from core.database import db
    from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo

    if not (testo or "").strip():
        await web_panel_pubblico_repo.imposta_slug(guild_id, None)
        await db._record_config_change(guild_id, changed_by, "setting", "classifica_web", None, None)
        return None
    slug = valida_slug(testo)
    if not await web_panel_pubblico_repo.imposta_slug(guild_id, slug):
        raise ImpostazioneNonValida("Questo indirizzo è già usato da un altro server.")
    await db._record_config_change(guild_id, changed_by, "setting", "classifica_web", None, slug)
    return slug


async def imposta_statistiche(guild_id: int, pubbliche: bool, membri: bool, changed_by: int | None) -> bool:
    """Accende o spegne la pagina pubblica e, a parte, la lista dei membri (vale anche per l'API)."""
    from core.database import db
    from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo

    prima = await web_panel_pubblico_repo.leggi(guild_id)
    membri = bool(membri)
    if (prima.stat_pubbliche, prima.stat_membri) == (bool(pubbliche), membri):
        return False
    await web_panel_pubblico_repo.imposta_statistiche(guild_id, bool(pubbliche), membri)
    await db._record_config_change(
        guild_id, changed_by, "setting", "statistiche_pubbliche",
        {"pubbliche": prima.stat_pubbliche, "membri": prima.stat_membri}, {"pubbliche": bool(pubbliche), "membri": membri},
    )
    return True


# --------------------------------------------------------------- chiave API
def impronta_chiave(chiave: str) -> str:
    return hashlib.sha256(chiave.encode("utf-8")).hexdigest()


def forma_valida(chiave: str) -> bool:
    return chiave.startswith(PREFISSO_CHIAVE) and 20 <= len(chiave) <= 80 and chiave.isascii() and chiave.isprintable()


async def crea_chiave(guild_id: int, creata_da: int | None) -> str:
    """Una chiave nuova (la vecchia smette di valere). Il chiamante la mostra UNA volta: qui resta solo l'impronta."""
    from core.database import db
    from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo

    chiave = PREFISSO_CHIAVE + secrets.token_urlsafe(32)
    await web_panel_pubblico_repo.imposta_chiave(
        guild_id, impronta_chiave(chiave), chiave[:LUNGHEZZA_VISIBILE_PREFISSO], creata_da
    )
    await db._record_config_change(guild_id, creata_da, "setting", "api_chiave", None, "creata")
    return chiave


async def revoca_chiave(guild_id: int, revocata_da: int | None) -> None:
    from core.database import db
    from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo

    await web_panel_pubblico_repo.imposta_chiave(guild_id, None, None, revocata_da)
    await db._record_config_change(guild_id, revocata_da, "setting", "api_chiave", None, "revocata")


async def guild_della_chiave(chiave: str) -> int | None:
    """Il server a cui appartiene la chiave, o None. Il confronto è sull'impronta (mai la chiave in chiaro)."""
    from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo

    if not forma_valida(chiave):
        return None
    impronta = impronta_chiave(chiave)
    guild_id = await web_panel_pubblico_repo.guild_da_impronta(impronta)
    if guild_id is None:
        return None
    return guild_id if hmac.compare_digest(impronta, impronta_chiave(chiave)) else None


# ------------------------------------------------------------------- dati
def _canale_pubblico(guild, canale_id: int):
    """Il canale solo se @everyone lo vede: i nomi dei canali privati non escono dal server."""
    canale = guild.get_channel(canale_id)
    if canale is None:
        return None
    try:
        return canale if canale.permissions_for(guild.default_role).view_channel else None
    except Exception:  # noqa: BLE001 - nel dubbio resta chiuso
        return None


def _nome_membro(guild, user_id: int, anonimi: set[int]) -> str:
    if user_id in anonimi:
        return ANONIMO
    membro = guild.get_member(user_id)
    return membro.display_name[:80] if membro is not None else "ex membro"


async def dati_statistiche(guild, *, con_membri: bool, con_id: bool = False) -> dict:
    """Le statistiche degli ultimi 30 giorni, senza nulla di privato. `con_id`: solo per l'API (mai per gli anonimi)."""
    from core.repositories.activity_stats_repo import activity_stats_repo as repo

    dal = date.today() - timedelta(days=GIORNI_STATISTICHE)
    canali = []
    for canale_id, n in await repo.top_channels(guild.id, dal, "messages", RIGHE_CLASSIFICA_PUBBLICA * 5):
        canale = _canale_pubblico(guild, canale_id)
        if canale is not None:
            canali.append({"nome": canale.name[:100], "messaggi": n})
        if len(canali) >= RIGHE_CLASSIFICA_PUBBLICA:
            break
    giorni = await repo.by_day(guild.id, dal, "messages")
    dati = {
        "server": guild.name[:100], "membri": guild.member_count, "giorni": GIORNI_STATISTICHE,
        "canali": canali,
        "messaggi_per_giorno": [{"giorno": g.isoformat(), "messaggi": n} for g, n in sorted(giorni.items())],
        "membri_piu_attivi": [],
    }
    if con_membri:
        top = await repo.top_members(guild.id, dal, "messages", RIGHE_CLASSIFICA_PUBBLICA)
        anonimi = await repo.anonymous_among([u for u, _ in top])
        for user_id, n in top:
            voce = {"nome": _nome_membro(guild, user_id, anonimi), "messaggi": n}
            if con_id and user_id not in anonimi:
                voce["id"] = str(user_id)
            dati["membri_piu_attivi"].append(voce)
    return dati


async def dati_classifica(guild) -> list[dict]:
    """La classifica XP di sempre, per la pagina web. Gli anonimi di STA-028 restano anonimi."""
    from core.repositories.activity_stats_repo import activity_stats_repo
    from core.repositories.leveling_repo import leveling_repo

    voci = await leveling_repo.top_xp_alltime(guild.id, RIGHE_CLASSIFICA_WEB)
    anonimi = await activity_stats_repo.anonymous_among([v.user_id for v in voci])
    return [
        {"posto": i, "nome": _nome_membro(guild, v.user_id, anonimi), "xp": v.amount} for i, v in enumerate(voci, start=1)
    ]


async def dati_negozio_da_oggetti(oggetti) -> list[dict]:
    """ECO-080: le righe del negozio per la pagina pubblica. Solo nome, prezzo, descrizione, categoria e se è esaurito:
    mai il ruolo richiesto, il messaggio di acquisto o l'azione. Al massimo 50; i testi si tagliano (l'escape lo fa il modello)."""
    voci = []
    for o in oggetti:
        if getattr(o, "a_rotazione", False):
            continue  # gli oggetti a rotazione compaiono in vetrina solo certi giorni: non si mostrano qui
        voci.append({
            "nome": str(o.name)[:100],
            "prezzo": int(o.price),
            "descrizione": (str(o.description)[:300] if o.description else ""),
            "categoria": (str(o.category)[:50] if o.category else ""),
            "esaurito": o.stock is not None and o.stock <= 0,
        })
        if len(voci) >= RIGHE_NEGOZIO_WEB:
            break
    return voci


async def dati_negozio(guild) -> list[dict]:
    from core.repositories.shop_repo import shop_repo

    return await dati_negozio_da_oggetti(await shop_repo.list_items(guild.id))

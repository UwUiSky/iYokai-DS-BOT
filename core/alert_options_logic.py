"""
core/alert_options_logic.py
===========================
Come si pubblica un avviso (feed, Twitch, YouTube, Kick): ruolo da avvisare,
bottone «Guarda», pubblicazione nei canali annunci, fine diretta (messaggio
sì/no, avviso cancellato). Un solo punto per tutti i watcher, così le
menzioni sono sempre esplicite (D12): `@everyone` e `@here` mai, un ruolo solo
se chi ha configurato l'avviso poteva pingare i ruoli.
Funzioni coperte: SPEC §10.9, §10.13 (#129 ALR-025, 026, 027, 028; #103 NF-32)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import discord

from core.ui_base import BaseView

logger = logging.getLogger("iyokai.alert_options")

SIGLE_CON_OPZIONI = {"RSS": "feed", "TW": "Twitch", "YT": "YouTube", "KK": "Kick"}
SIGLE_DIRETTA = ("TW", "YT", "KK")

GUIDA_SOCIAL = (
    "**TikTok, Instagram e X** non hanno interfacce gratuite per gli avvisi, "
    "quindi ci si arriva con due strade già presenti nel bot.\n\n"
    "**1. Feed «ponte» (consigliato)**\n"
    "Un servizio esterno trasforma il profilo in un feed RSS (per esempio un'istanza di RSSHub, "
    "o un servizio a pagamento che offre feed per i social). Poi usa "
    "`/moduli alert feed` incollando l'indirizzo del feed. Controllo ogni 5 minuti.\n\n"
    "**2. Webhook in ingresso**\n"
    "Con `/moduli alert webhook` ottieni un indirizzo segreto. Collegalo a uno strumento di "
    "automazione (Zapier, Make, IFTTT, n8n) che manda un messaggio JSON, "
    "per esempio `{\"message\": \"Nuovo video!\", \"url\": \"https://…\"}`, quando c'è un post nuovo.\n\n"
    "**Chiave a pagamento (facoltativa)**\n"
    "Chi vuole il collegamento diretto può farlo con il servizio a pagamento di un fornitore terzo: "
    "il bot non la richiede e non la conserva.\n\n"
    "**Kick** invece ha un'interfaccia gratuita: `/moduli alert kick`. "
    "Il proprietario del bot imposta `KICK_CLIENT_ID` e `KICK_CLIENT_SECRET`."
)

MAX_MESSAGGIO = 2000
MAX_URL_BOTTONE = 512


@dataclass(frozen=True)
class AlertOptions:
    mention_role_id: int | None = None
    ping_allowed: bool = False
    notify_end: bool = True
    delete_on_end: bool = False
    watch_button: bool = True
    crosspost: bool = False
    live_member_id: int | None = None
    last_message_id: int | None = None


def menzioni_avviso(opz: AlertOptions) -> discord.AllowedMentions:
    """Nessun utente, nessun everyone; il ruolo scelto solo se chi ha configurato poteva pingarlo."""
    ruoli = [discord.Object(id=opz.mention_role_id)] if opz.ping_allowed and opz.mention_role_id else False
    return discord.AllowedMentions(everyone=False, users=False, roles=ruoli, replied_user=False)


def testo_con_menzione(testo: str, opz: AlertOptions) -> str:
    if opz.mention_role_id:
        testo = f"<@&{opz.mention_role_id}> {testo}"
    return testo[:MAX_MESSAGGIO]


def vista_guarda(url: str | None, opz: AlertOptions) -> discord.ui.View | None:
    if not opz.watch_button or not url or not url.startswith(("https://", "http://")) or len(url) > MAX_URL_BOTTONE:
        return None
    vista = BaseView(timeout=None)
    vista.add_item(discord.ui.Button(label="Guarda", style=discord.ButtonStyle.link, url=url))
    return vista


async def invia_alert(canale, testo: str, opz: AlertOptions, url: str | None = None):
    """Invia l'avviso (con ruolo, bottone, pubblicazione). Solleva discord.HTTPException se l'invio fallisce."""
    kwargs = {"allowed_mentions": menzioni_avviso(opz)}
    vista = vista_guarda(url, opz)
    if vista is not None:
        kwargs["view"] = vista
    messaggio = await canale.send(testo_con_menzione(testo, opz), **kwargs)
    if opz.crosspost and canale.is_news():
        try:
            await messaggio.publish()
        except discord.HTTPException:
            logger.warning("Avviso non pubblicato nel canale annunci %s", canale.id)
    return messaggio


async def avviso_live(canale, testo: str, opz: AlertOptions, url: str | None = None) -> int | None:
    """Messaggio «in diretta»: restituisce l'id da ricordare per cancellarlo a fine diretta."""
    messaggio = await invia_alert(canale, testo, opz, url)
    return getattr(messaggio, "id", None)


async def avviso_fine(canale, testo: str, opz: AlertOptions) -> None:
    """Fine diretta: cancella l'avviso (se richiesto) e manda il messaggio di chiusura (se acceso)."""
    if opz.delete_on_end and opz.last_message_id:
        try:
            await canale.get_partial_message(opz.last_message_id).delete()
        except discord.HTTPException:
            pass  # già cancellato o niente permesso: la diretta è finita comunque
    if opz.notify_end:
        # Il messaggio di chiusura non porta il ruolo, né il bottone, né la pubblicazione.
        await invia_alert(canale, testo, replace(opz, mention_role_id=None, watch_button=False, crosspost=False))


def leggi_id_avviso(testo: str) -> tuple[str, int] | None:
    """«TW-2» -> ("TW", 2). Solo le sigle che hanno opzioni (non i webhook)."""
    sigla, _, numero = testo.strip().upper().partition("-")
    if sigla not in SIGLE_CON_OPZIONI or not numero.isdigit():
        return None
    return sigla, int(numero)

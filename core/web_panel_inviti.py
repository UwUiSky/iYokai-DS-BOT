"""
core/web_panel_inviti.py
========================
Rotte del pannello web per i link d'invito personali «finto vanity» e lo storico degli inviti:
`/invito/<slug>` (pubblico: porta all'invito Discord dedicato), «I miei inviti» (`/miei-inviti`)
e la pagina dell'admin `/server/<id>/inviti` (opzioni, classifica, ultimi ingressi). Le opzioni
passano da `core/invite_service.py`, lo stesso punto dei comandi (D16).
Si registra con una riga da `core/web_panel_server.py`; i controlli comuni (sessione, permessi
sul server a ogni richiesta, CSRF, limite di scritture, escape) sono quelli del pannello.
Funzioni coperte: SPEC §23 (NF-27, link personali r10), §24 (pannello)
Dipende da: core/invite_service.py, core/web_panel_logic.py
"""

from __future__ import annotations

import logging
import re

import discord
from aiohttp import web

from core import invite_links_logic as logica, invite_service, web_panel_logic as regole
from core.config_schema import ImpostazioneNonValida
from core.repositories.invite_links_repo import invite_links_repo
from core.repositories.invite_stats_repo import invite_stats_repo

logger = logging.getLogger("iyokai.web_panel_inviti")

MAX_SERVER_ELENCATI = 25
MAX_VOCI_SELECT = 250
CODICE_DISCORD = re.compile(r"^[A-Za-z0-9-]{2,32}$")

# Messaggi della pagina «I miei inviti» (nell'URL c'è solo il codice).
ESITI_LINK = {
    "link_creato": ("Il tuo link è pronto.", False),
    logica.MODULO_SPENTO: (logica.testo_esito(logica.MODULO_SPENTO), True),
    logica.RUOLO_MANCANTE: (logica.testo_esito(logica.RUOLO_MANCANTE), True),
    logica.NON_NEL_SERVER: (logica.testo_esito(logica.NON_NEL_SERVER), True),
    logica.INVITI_DISABILITATI: (logica.testo_esito(logica.INVITI_DISABILITATI), True),
    logica.SENZA_PERMESSO: (logica.testo_esito(logica.SENZA_PERMESSO), True),
    logica.NESSUN_CANALE: (logica.testo_esito(logica.NESSUN_CANALE), True),
    logica.MEMBRO_SENZA_PERMESSO: (logica.testo_esito(logica.MEMBRO_SENZA_PERMESSO), True),
}
# Cosa dice il sito a chi apre un link che non può usare (mai nomi di persone).
PAGINE_LINK = {
    logica.INVITI_DISABILITATI: (503, "Inviti in pausa", "Questo server ha messo in pausa gli inviti: riprova più tardi."),
    logica.SENZA_PERMESSO: (503, "Link non disponibile", "Il bot di questo server non ha il permesso «Crea invito»: avvisa un amministratore."),
    logica.NESSUN_CANALE: (503, "Link non disponibile", "Il bot non trova un canale dove creare l'invito."),
    logica.ERRORE_DISCORD: (503, "Riprova tra poco", "Discord non ha creato l'invito in questo momento."),
    logica.TROPPI_INVITI: (503, "Link non disponibile", "Il server ha raggiunto il numero massimo di link personali: avvisa un amministratore."),
}
PAGINA_NON_ATTIVO = (404, "Link non attivo", "Questo link non esiste o non è attivo in questo momento.")


def _nome(guild: discord.Guild, user_id: int | None) -> str:
    if not user_id:
        return "nessuno di riconosciuto"
    membro = guild.get_member(user_id)
    return membro.display_name if membro is not None else f"utente {user_id}"


async def _riga_server(guild: discord.Guild, user_id: int, link) -> dict | None:
    """Cosa mostrare di un server in «I miei inviti»: link, esito se può averlo, numeri."""
    opzioni = await invite_service.leggi_opzioni(guild.id)
    if not opzioni.attivo:
        return None
    membro = guild.get_member(user_id)
    puo = await invite_service.puo_avere_il_link(guild, membro)
    statistiche = await invite_stats_repo.stats_for(guild.id, user_id)
    ingresso = await invite_stats_repo.ingresso_di(guild.id, user_id)
    return {
        "id": guild.id,
        "nome": guild.name,
        "indirizzo": invite_service.indirizzo(link) if link else None,
        "puo_crearlo": puo == logica.OK,
        "motivo": None if puo == logica.OK else logica.testo_esito(puo),
        "totale": statistiche.totale,
        "presenti": statistiche.presenti,
        "usciti": statistiche.totale - statistiche.presenti,
        "invitato_da": _nome(guild, ingresso.inviter_id) if ingresso else None,
        "tipo": logica.ETICHETTE_TIPO.get(ingresso.kind) if ingresso else None,
    }


def registra_rotte(app: web.Application, *, bot, pagina, errore, server, scrittura, ip, chiave_utente) -> None:
    """
    `pagina(request, modello, codice_http, **dati)`, `errore(request, codice, titolo, testo)`,
    `server(request)` -> (guild, rifiuto), `scrittura(request)` -> (modulo, rifiuto), `ip(request)`:
    gli aiuti di `build_app`. `chiave_utente`: la chiave della sessione nella richiesta.
    """
    limite_link = regole.LimiteFrequenza(20, 60)  # per IP: ogni apertura può chiamare Discord

    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    # ------------------------------------------------ il link (pubblico)
    async def apri(request: web.Request) -> web.Response:
        if not limite_link.consenti(ip(request)):
            return errore(request, 429, "Troppe richieste", "Aspetta un minuto e riprova.")
        esito, codice = await invite_service.apri_link(bot, request.match_info["slug"])
        if codice is None or not CODICE_DISCORD.fullmatch(codice):
            return errore(request, *PAGINE_LINK.get(esito, PAGINA_NON_ATTIVO))
        risposta = vai(logica.indirizzo_discord(codice))
        risposta.headers["Cache-Control"] = "no-store"
        return risposta

    # ------------------------------------------------ I miei inviti
    async def miei_inviti(request: web.Request) -> web.Response:
        utente_id = request.get(chiave_utente)
        if utente_id is None:
            return vai("/accedi")
        link_per_server = {l.guild_id: l for l in await invite_links_repo.dell_utente(utente_id)}
        server_ids = set(link_per_server)
        for guild in bot.guilds:
            if guild.get_member(utente_id) is not None:
                server_ids.add(guild.id)
        righe = []
        for guild_id in sorted(server_ids):
            guild = bot.get_guild(guild_id)
            if guild is None:
                continue
            riga = await _riga_server(guild, utente_id, link_per_server.get(guild_id))
            if riga is not None:
                righe.append(riga)
            if len(righe) >= MAX_SERVER_ELENCATI:
                break
        esito = ESITI_LINK.get(request.query.get("esito", ""))
        extra = {"messaggio": esito[0], "errore": esito[1]} if esito else {}
        return pagina(request, "inviti_miei.html", server=righe, sito_attivo=bool(invite_service.url_pubblico()), **extra)

    async def crea_link(request: web.Request) -> web.Response:
        if request.get(chiave_utente) is None:
            return vai("/accedi")
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        testo = str(form.get("guild_id", ""))
        guild = bot.get_guild(int(testo)) if testo.isascii() and testo.isdigit() and len(testo) <= 20 else None
        if guild is None:
            return vai("/miei-inviti?esito=" + logica.NON_NEL_SERVER)
        utente_id = request[chiave_utente]
        membro = guild.get_member(utente_id)
        if membro is None:
            try:
                membro = await guild.fetch_member(utente_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                membro = None
        esito, link = await invite_service.ottieni_link(guild, membro)
        return vai("/miei-inviti?esito=" + ("link_creato" if link is not None else esito))

    # ------------------------------------------------ pagina dell'admin
    async def pagina_admin(request: web.Request) -> web.Response:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        opzioni = await invite_service.leggi_opzioni(guild.id)
        canali = sorted(guild.text_channels, key=lambda c: c.position)[:MAX_VOCI_SELECT]
        ruoli = sorted(
            (r for r in guild.roles if r.id != guild.id and not r.managed), key=lambda r: -r.position
        )[:MAX_VOCI_SELECT]
        classifica = [
            {"nome": _nome(guild, uid), "presenti": s.presenti, "totale": s.totale}
            for uid, s in await invite_stats_repo.top(guild.id)
        ]
        ultimi = [
            {
                "chi": _nome(guild, uid),
                "invitante": _nome(guild, ing.inviter_id),
                "tipo": logica.ETICHETTE_TIPO.get(ing.kind, ing.kind),
                "quando": ing.joined_at,
                "uscito": ing.left_at,
            }
            for uid, ing in await invite_stats_repo.ultimi_ingressi(guild.id)
        ]
        per_tipo = await invite_stats_repo.per_tipo(guild.id)
        return pagina(
            request, "inviti_server.html", guild=guild, opzioni=opzioni, canali=canali, ruoli=ruoli,
            classifica=classifica, ultimi=ultimi, modalita_link=list(logica.ETICHETTE_MODALITA.items()),
            per_tipo=[(logica.ETICHETTE_TIPO[t], per_tipo.get(t, 0)) for t in logica.TIPI_INGRESSO],
            sito_attivo=bool(invite_service.url_pubblico()),
        )

    async def salva_admin(request: web.Request) -> web.Response:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        indietro = f"/server/{guild.id}/inviti?esito="

        def leggi_id(nome: str):
            testo = str(form.get(nome, ""))
            if not testo:
                return None
            if not testo.isascii() or not testo.isdigit() or len(testo) > 20:
                raise ImpostazioneNonValida("Valore non valido.")
            return int(testo)

        try:
            cambiato = await invite_service.imposta_opzioni(
                guild, canale_log=leggi_id("canale_id"), ruolo_link=leggi_id("ruolo_id"),
                modalita=str(form.get("modalita", "")) or invite_service.NON_CAMBIARE, changed_by=request[chiave_utente],
            )
        except ImpostazioneNonValida:
            return vai(indietro + "non_valido")
        return vai(indietro + ("salvato" if cambiato else "invariato"))

    app.router.add_get(r"/invito/{slug:[a-z0-9\-]{3,80}}", apri)
    app.router.add_get("/miei-inviti", miei_inviti)
    app.router.add_post("/miei-inviti", crea_link)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/inviti", pagina_admin)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/inviti", salva_admin)

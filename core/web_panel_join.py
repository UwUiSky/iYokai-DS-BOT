"""
core/web_panel_join.py
======================
Pagina di consenso per il rientro dopo un ripristino (BKP-039, D113): `/join/<nome>`, con nome, icona e colori del server.
Il server la accende dal pannello (`/server/<id>/join`), sceglie un nome breve unico (3-32 caratteri: minuscole, cifre e trattini,
nomi riservati esclusi; senza nome vale l'ID) e due colori. La persona entra con Discord, poi autorizza: da lì parte lo STESSO
flusso OAuth del ripristino utenti (`core/restore_oauth_logic.py`, `state` firmato e monouso, legato a chi l'ha chiesto,
solo consenso, stessa callback): niente cambia nella sua sicurezza. Pagina e colori sono pubblici, con limite per IP; nome
inesistente, pagina spenta, server senza il bot, ripristino «solo invito» e funzione non configurata hanno la STESSA 404.
Funzioni coperte: SPEC §24.12 (BKP-039, D113, issue #121)
Dipende da: core/web_panel_pubblico.py (stessa validazione degli indirizzi brevi, LIV-062), core/restore_oauth_logic.py
"""

from __future__ import annotations

import logging
import re

from aiohttp import web

from core import web_panel_logic as regole, web_panel_pubblico as pubblico
from core.config_schema import ImpostazioneNonValida
from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo
from core.restore_batch_logic import DEFAULT_RESTORE_MODE, MODE_CLASSIC_INVITE
from core.restore_oauth_logic import RestoreStateSigningError, build_authorize_url
from core.restore_web_server import CONSENT_ONLY_TARGET

logger = logging.getLogger("iyokai.web_panel_join")

SETTING_RESTORE_MODE = "backup_restore_mode"  # lo stesso di cogs/utility/restore.py
NOMI_RISERVATI_JOIN = pubblico.NOMI_RISERVATI | frozenset({
    "join", "ripristino", "restore", "backup", "consenso", "colori", "rientro", "avvia", "accedi",
})
_COLORE = re.compile(r"^#[0-9a-f]{6}$")
ICONA_CDN = "https://cdn.discordapp.com/"
NON_DISPONIBILE = (404, "Pagina non disponibile", "Questa pagina non esiste o non è disponibile in questo momento.")
PERCORSO_RITORNO = re.compile(r"^/join/[a-z0-9-]{1,32}$")  # le sole destinazioni dopo l'accesso (nessun redirect libero)
RISPOSTE = {"join_salvata": "Pagina di rientro salvata.", "join_spenta": "Pagina di rientro spenta."}


def valida_nome(testo: str) -> str:
    """Il nome breve pronto da salvare. Storto o riservato = ImpostazioneNonValida (stesse regole degli altri indirizzi brevi)."""
    nome = pubblico.valida_slug(testo)
    if nome in NOMI_RISERVATI_JOIN:
        raise ImpostazioneNonValida("Questo indirizzo non è disponibile: sceglierne un altro.")
    return nome


def valida_colore(testo: str) -> str | None:
    """`#rrggbb` (minuscolo) o None se vuoto. Altro = ImpostazioneNonValida: il colore finisce in un foglio di stile."""
    colore = (testo or "").strip().lower()
    if not colore:
        return None
    if not colore.isascii() or not _COLORE.match(colore):
        raise ImpostazioneNonValida("I colori si scrivono come #rrggbb (per esempio #c24a3a).")
    return colore


async def imposta_pagina(guild_id: int, attiva: bool, nome: str, accento: str, sfondo: str, changed_by: int | None) -> str | None:
    """Accende o spegne la pagina e salva nome e colori (un solo punto, D16). Ritorna il nome scelto o None."""
    from core.database import db

    slug = valida_nome(nome) if (nome or "").strip() else None
    a, s = valida_colore(accento), valida_colore(sfondo)
    if not await web_panel_pubblico_repo.imposta_join(guild_id, bool(attiva), slug, a, s):
        raise ImpostazioneNonValida("Questo indirizzo è già usato da un altro server.")
    await db._record_config_change(guild_id, changed_by, "setting", "pagina_rientro", None, slug or ("id" if attiva else None))
    return slug


def _luminanza(colore: str) -> float:
    r, g, b = (int(colore[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def foglio_colori(accento: str | None, sfondo: str | None) -> str:
    """Il foglio di stile dei colori del server. Solo `#rrggbb` già controllati entrano qui (altro viene ignorato)."""
    regole_css = []
    if sfondo and _COLORE.match(sfondo):
        scuro = _luminanza(sfondo) < 0.5
        regole_css += [f"--sfondo:{sfondo}", f"--testo:{'#ececf2' if scuro else '#1d1d24'}", f"--tenue:{'#b4b4c2' if scuro else '#4a4a58'}",
                       f"--carta:{'#ffffff1a' if scuro else '#ffffffcc'}"]
    if accento and _COLORE.match(accento):
        regole_css.append(f"--accento:{accento}")
    return ":root{" + ";".join(regole_css) + "}" if regole_css else ""


def icona_del_server(guild) -> str | None:
    icona = getattr(guild, "icon", None)
    url = str(getattr(icona, "url", "") or "") if icona else ""
    return url if url.startswith(ICONA_CDN) else None


async def pagina_disponibile(bot, guild_id: int):
    """Il server se la pagina può mostrarsi: il bot c'è e il ripristino non è «solo invito classico»."""
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None
    from core.database import db

    modalita = await db.get_guild_setting(guild_id, SETTING_RESTORE_MODE, DEFAULT_RESTORE_MODE)
    return None if modalita == MODE_CLASSIC_INVITE else guild


def registra_rotte(
    app: web.Application, *, bot, pagina, errore, server, scrittura, chiave_utente, ip, client_id: str,
    restore_redirect_uri: str, chiave_firma: str, imposta_ritorno, puo_gestire,
) -> None:
    """`imposta_ritorno(risposta, percorso)`: ricorda dove tornare dopo l'accesso. `puo_gestire(guild, user_id)`: permessi del ripristino."""
    limite_pubbliche = regole.LimiteFrequenza(30, 60)  # per IP: pagina e colori interrogano il database
    limite_avvio = regole.LimiteFrequenza(5, 60)  # per persona: ogni avvio crea uno state

    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    def non_disponibile(request: web.Request) -> web.Response:
        return errore(request, *NON_DISPONIBILE)

    async def trova(request: web.Request):
        """(server, scelte) se la pagina è disponibile, altrimenti None: la stessa risposta per ogni motivo."""
        if not (restore_redirect_uri and chiave_firma and client_id):
            return None
        nome = request.match_info["nome"]
        guild_id = await web_panel_pubblico_repo.guild_da_join(nome)
        guild = await pagina_disponibile(bot, guild_id) if guild_id is not None else None
        if guild is None:
            return None
        return guild, await web_panel_pubblico_repo.leggi(guild.id)

    async def mostra(request: web.Request) -> web.StreamResponse:
        if not limite_pubbliche.consenti(ip(request)):
            return errore(request, 429, "Troppe richieste", "Aspetta un minuto e riprova.")
        trovato = await trova(request)
        if trovato is None:
            return non_disponibile(request)
        guild, scelte = trovato
        return pagina(
            request, "join.html", guild=guild, nome=request.match_info["nome"], icona=icona_del_server(guild),
            con_colori=bool(foglio_colori(scelte.join_accento, scelte.join_sfondo)),
        )

    async def colori(request: web.Request) -> web.StreamResponse:
        if not limite_pubbliche.consenti(ip(request)):
            return web.Response(status=429, text="")
        trovato = await trova(request)
        if trovato is None:
            return web.Response(status=404, text="")
        _, scelte = trovato
        return web.Response(text=foglio_colori(scelte.join_accento, scelte.join_sfondo), content_type="text/css")

    async def accedi(request: web.Request) -> web.StreamResponse:
        if not limite_pubbliche.consenti(ip(request)):
            return errore(request, 429, "Troppe richieste", "Aspetta un minuto e riprova.")
        if await trova(request) is None:
            return non_disponibile(request)
        percorso = f"/join/{request.match_info['nome']}"
        risposta = vai("/accedi")
        if PERCORSO_RITORNO.match(percorso):
            imposta_ritorno(risposta, percorso)
        return risposta

    async def avvia(request: web.Request) -> web.StreamResponse:
        utente = request.get(chiave_utente)
        if utente is None:
            return vai("/accedi")
        _, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        if not limite_avvio.consenti(f"j:{utente}"):
            return errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        trovato = await trova(request)
        if trovato is None:
            return non_disponibile(request)
        guild, _ = trovato
        try:  # lo stesso `state` del ripristino: per chi l'ha chiesto, a scadenza, monouso
            url = build_authorize_url(
                client_id=client_id, redirect_uri=restore_redirect_uri, source_guild_id=guild.id,
                target_guild_id=CONSENT_ONLY_TARGET, user_id=utente, signing_key_b64=chiave_firma,
            )
        except RestoreStateSigningError:
            logger.warning("Pagina di rientro: OAUTH_ENCRYPTION_KEY non valida, nessun link creato.")
            return non_disponibile(request)
        return vai(url)

    # ----------------------------------------------- impostazioni del server (admin)
    async def ammesso(request: web.Request):
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return None, rifiuto
        if not await puo_gestire(guild, request[chiave_utente]):  # come i backup: chi può ripristinare
            return None, errore(request, 403, "Accesso negato", "Non puoi gestire il ripristino di questo server.")
        return guild, None

    async def impostazioni(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await ammesso(request)
        if rifiuto is not None:
            return rifiuto
        return pagina(request, "join_impostazioni.html", guild=guild, p=await web_panel_pubblico_repo.leggi(guild.id))

    async def salva(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await ammesso(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        indietro = f"/server/{guild.id}/join"
        try:
            await imposta_pagina(
                guild.id, form.get("attiva") == "1", str(form.get("nome", ""))[:64], str(form.get("accento", ""))[:16],
                str(form.get("sfondo", ""))[:16], request[chiave_utente],
            )
        except ImpostazioneNonValida as exc:
            return pagina(
                request, "join_impostazioni.html", 400, guild=guild, p=await web_panel_pubblico_repo.leggi(guild.id),
                messaggio=str(exc), errore=True,
            )
        return vai(f"{indietro}?esito={'join_salvata' if form.get('attiva') == '1' else 'join_spenta'}")

    app.router.add_get(r"/join/{nome:[a-z0-9\-]{1,32}}", mostra)
    app.router.add_get(r"/join/{nome:[a-z0-9\-]{1,32}}/colori.css", colori)
    app.router.add_get(r"/join/{nome:[a-z0-9\-]{1,32}}/accedi", accedi)
    app.router.add_post(r"/join/{nome:[a-z0-9\-]{1,32}}/avvia", avvia)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/join", impostazioni)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/join", salva)

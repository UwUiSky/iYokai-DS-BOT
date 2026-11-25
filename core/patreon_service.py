"""
core/patreon_service.py
=======================
Patreon (CFG-036): collega l'account Patreon a quello Discord con OAuth (stato monouso, token cifrati), applica gli
eventi del webhook (idempotenti) e traduce i livelli Patreon in livelli del bot (`core/piani.py`, fonte `patreon`).
La rete passa da `ClientePatreon`, così i test la sostituiscono. Spento senza le chiavi: nessuna funzione qui
viene chiamata (le rotte non esistono).
Funzioni coperte: CFG-036
Dipende da: core/patreon_logic.py, core/piani.py, core/oauth_crypto.py, core/migrations/0913_patreon.sql
"""

from __future__ import annotations

import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from core import piani
from core.patreon_logic import DaConfermare, EventoPatreon, impronta_corpo, livello_da_tiers

logger = logging.getLogger("iyokai.patreon")

URL_AUTORIZZA = "https://www.patreon.com/oauth2/authorize"
URL_TOKEN = "https://www.patreon.com/api/oauth2/token"
URL_IDENTITA = "https://www.patreon.com/api/oauth2/v2/identity"
VALIDITA_STATO = timedelta(minutes=10)
GIORNI_DI_GRAZIA = 45  # un sostegno mensile si rinnova a ogni evento; se i rinnovi spariscono il livello scade da solo
CONSERVA_EVENTI_GIORNI = 400  # le impronte non hanno dati personali: tenute a lungo, un evento vecchio rimandato non conta
TEMPO_RETE = 15  # secondi


class PatreonSpento(RuntimeError):
    """Le chiavi non ci sono."""


class CollegamentoFallito(RuntimeError):
    """Stato scaduto o già usato, codice rifiutato, risposta di Patreon incomprensibile."""


def _pool():
    from core.database import db

    return db.pool


def _config():
    from core.config import config

    return config


def acceso() -> bool:
    from core.patreon_logic import chiavi_presenti

    c = _config()
    return chiavi_presenti(c.PATREON_CLIENT_ID, c.PATREON_CLIENT_SECRET, c.PATREON_WEBHOOK_SECRET)


def _redirect() -> str:
    return _config().WEB_PANEL_PUBLIC_URL.rstrip("/") + "/patreon/callback"


class ClientePatreon:
    """Le due chiamate a Patreon. Host fissi, mai un URL scelto da un utente."""

    async def scambia_codice(self, codice: str) -> dict:
        import aiohttp

        c = _config()
        dati = {"code": codice, "grant_type": "authorization_code", "client_id": c.PATREON_CLIENT_ID,
                "client_secret": c.PATREON_CLIENT_SECRET, "redirect_uri": _redirect()}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TEMPO_RETE)) as s, s.post(URL_TOKEN, data=dati) as r:
            if r.status != 200:
                raise CollegamentoFallito(f"token {r.status}")
            return await r.json()

    async def identita(self, access_token: str) -> dict:
        import aiohttp

        params = {"include": "memberships.currently_entitled_tiers", "fields[member]": "patron_status"}
        intestazioni = {"Authorization": f"Bearer {access_token}"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TEMPO_RETE)) as s, \
                s.get(URL_IDENTITA, params=params, headers=intestazioni) as r:
            if r.status != 200:
                raise CollegamentoFallito(f"identita {r.status}")
            return await r.json()


# ---------------------------------------------------------------- OAuth
async def crea_stato(discord_user_id: int, impronta_sessione: str) -> str:
    """
    Il segreto monouso (10 minuti) che lega il ritorno da Patreon alla persona che ha cominciato dal pannello.
    Porta anche l'impronta della SESSIONE del pannello: il ritorno vale solo nello stesso browser (stesso cookie).
    Un link scritto da un altro, aperto da chi è già dentro, non collega niente.
    """
    if not acceso():
        raise PatreonSpento()
    if not impronta_sessione:
        raise CollegamentoFallito("sessione")
    stato = secrets.token_urlsafe(32)
    await _pool().execute("DELETE FROM patreon_stati WHERE scade_il < now()")
    await _pool().execute(
        "INSERT INTO patreon_stati (impronta, discord_user_id, scade_il, sessione_impronta) VALUES ($1, $2, $3, $4)",
        impronta_corpo(stato.encode()), discord_user_id, datetime.now(timezone.utc) + VALIDITA_STATO, impronta_sessione,
    )
    return stato


def url_collegamento(stato: str) -> str:
    c = _config()
    return URL_AUTORIZZA + "?" + urlencode({
        "response_type": "code", "client_id": c.PATREON_CLIENT_ID, "redirect_uri": _redirect(),
        "scope": "identity identity.memberships", "state": stato,
    })


async def _consuma_stato(stato: str, impronta_sessione: str) -> int:
    """
    Atomico: lo stato vale una volta sola, e solo con la stessa sessione del pannello che l'ha creato.
    Se la sessione non è quella, lo stato si brucia lo stesso (chi riprova deve ricominciare dal pannello).
    """
    riga = await _pool().fetchrow(
        "DELETE FROM patreon_stati WHERE impronta = $1 AND scade_il > now() RETURNING discord_user_id, sessione_impronta",
        impronta_corpo((stato or "").encode()),
    )
    if riga is None:
        raise CollegamentoFallito("stato")
    atteso = riga["sessione_impronta"] or ""
    if not impronta_sessione or not atteso or not hmac.compare_digest(atteso.encode(), impronta_sessione.encode()):
        raise CollegamentoFallito("sessione")
    return riga["discord_user_id"]


def _leggi_identita(risposta: dict) -> tuple[str, bool, tuple[str, ...]]:
    try:
        utente = str(risposta["data"]["id"])
    except (KeyError, TypeError):
        raise CollegamentoFallito("identita") from None
    attivo, tiers = False, []
    for voce in risposta.get("included", []) or []:
        if voce.get("type") == "member" and voce.get("attributes", {}).get("patron_status") == "active_patron":
            attivo = True
            tiers += [str(t["id"]) for t in voce.get("relationships", {}).get("currently_entitled_tiers", {}).get("data", []) if "id" in t]
    return utente, attivo, tuple(dict.fromkeys(tiers))


async def _scrivi_collegamento(
    conn, discord_id: int, patreon_id: str, token_cifrato: str, refresh_cifrato: str | None, attivo: bool, tiers
) -> list[int]:
    """Il collegamento e lo stato del sostenitore, in una transazione. Restituisce le persone a cui l'account è stato tolto."""
    vecchi = await conn.fetch(
        "DELETE FROM patreon_collegamenti WHERE patreon_id = $1 AND discord_user_id <> $2 RETURNING discord_user_id",
        patreon_id, discord_id,
    )
    await conn.execute(
        """
        INSERT INTO patreon_collegamenti (discord_user_id, patreon_id, token_cifrato, refresh_cifrato)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (discord_user_id) DO UPDATE SET patreon_id = EXCLUDED.patreon_id,
            token_cifrato = EXCLUDED.token_cifrato, refresh_cifrato = EXCLUDED.refresh_cifrato, creato_il = now()
        """,
        discord_id, patreon_id, token_cifrato, refresh_cifrato,
    )
    await conn.execute(
        """
        INSERT INTO patreon_membri (patreon_id, attivo, tiers) VALUES ($1, $2, $3)
        ON CONFLICT (patreon_id) DO UPDATE SET attivo = EXCLUDED.attivo, tiers = EXCLUDED.tiers, aggiornato_il = now()
        """,
        patreon_id, attivo, list(tiers),
    )
    return [v["discord_user_id"] for v in vecchi]


async def completa_collegamento(stato: str, codice: str, impronta_sessione: str, cliente: ClientePatreon | None = None) -> int:
    """
    Il ritorno da Patreon: collega l'account, salva i token cifrati e applica il livello. Restituisce l'utente Discord.
    Se quell'account Patreon è già di un'altra persona NON lo sposta: salva i token in attesa e solleva `DaConfermare`
    (la persona conferma dal pannello con `conferma_spostamento`).
    """
    from core.oauth_crypto import encrypt_token

    if not acceso():
        raise PatreonSpento()
    cliente = cliente or ClientePatreon()
    discord_id = await _consuma_stato(stato, impronta_sessione)
    token = await cliente.scambia_codice(codice)
    accesso = token.get("access_token")
    if not isinstance(accesso, str) or not accesso:
        raise CollegamentoFallito("token")
    patreon_id, attivo, tiers = _leggi_identita(await cliente.identita(accesso))
    chiave = _config().OAUTH_ENCRYPTION_KEY
    if not chiave:
        raise CollegamentoFallito("cifratura")
    aad = f"patreon:{discord_id}".encode()
    refresh = token.get("refresh_token")
    token_cifrato = encrypt_token(accesso, chiave, aad=aad)
    refresh_cifrato = encrypt_token(refresh, chiave, aad=aad) if isinstance(refresh, str) and refresh else None
    da_confermare = False
    vecchi: list[int] = []
    async with _pool().acquire() as conn, conn.transaction():
        # Un blocco per account Patreon: due ritorni insieme non si superano a vicenda.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"patreon:{patreon_id}")
        occupato = await conn.fetchval(
            "SELECT 1 FROM patreon_collegamenti WHERE patreon_id = $1 AND discord_user_id <> $2", patreon_id, discord_id
        )
        if occupato:
            await conn.execute(
                """
                INSERT INTO patreon_spostamenti (discord_user_id, patreon_id, token_cifrato, refresh_cifrato, attivo, tiers, scade_il)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (discord_user_id) DO UPDATE SET patreon_id = EXCLUDED.patreon_id, token_cifrato = EXCLUDED.token_cifrato,
                    refresh_cifrato = EXCLUDED.refresh_cifrato, attivo = EXCLUDED.attivo, tiers = EXCLUDED.tiers, scade_il = EXCLUDED.scade_il
                """,
                discord_id, patreon_id, token_cifrato, refresh_cifrato, attivo, list(tiers), datetime.now(timezone.utc) + VALIDITA_STATO,
            )
            da_confermare = True  # si solleva fuori dalla transazione: un errore qui annullerebbe l'attesa appena scritta
        else:
            vecchi = await _scrivi_collegamento(conn, discord_id, patreon_id, token_cifrato, refresh_cifrato, attivo, tiers)
    if da_confermare:
        raise DaConfermare(discord_id)
    for vecchio in vecchi:
        await piani.revoca("utente", vecchio, "patreon")
    await sincronizza(patreon_id)
    return discord_id


async def spostamento_in_attesa(discord_user_id: int) -> bool:
    """Questa persona ha un collegamento Patreon da confermare (account già di un'altra persona)?"""
    return bool(await _pool().fetchval(
        "SELECT 1 FROM patreon_spostamenti WHERE discord_user_id = $1 AND scade_il > now()", discord_user_id
    ))


async def conferma_spostamento(discord_user_id: int, conferma: bool) -> bool:
    """
    La persona risponde alla domanda «spostare l'account Patreon qui?». Con `conferma` l'account passa a lei e la
    concessione della persona di prima si toglie; senza, i token in attesa si cancellano. False se non c'era niente
    da confermare (scaduto o già deciso). Vale una volta sola: la riga si prende e si cancella nella stessa transazione.
    """
    async with _pool().acquire() as conn, conn.transaction():
        riga = await conn.fetchrow(
            "DELETE FROM patreon_spostamenti WHERE discord_user_id = $1 AND scade_il > now() RETURNING *", discord_user_id
        )
        if riga is None:
            return False
        if not conferma:
            return True
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"patreon:{riga['patreon_id']}")
        vecchi = await _scrivi_collegamento(
            conn, discord_user_id, riga["patreon_id"], riga["token_cifrato"], riga["refresh_cifrato"], riga["attivo"], riga["tiers"]
        )
    for vecchio in vecchi:
        await piani.revoca("utente", vecchio, "patreon")
    await sincronizza(riga["patreon_id"])
    return True


async def collegato(discord_user_id: int) -> bool:
    """Questa persona ha un account Patreon collegato?"""
    return bool(await _pool().fetchval("SELECT 1 FROM patreon_collegamenti WHERE discord_user_id = $1", discord_user_id))


async def scollega(discord_user_id: int) -> bool:
    """La persona toglie il collegamento: token cancellati e livello Patreon tolto."""
    riga = await _pool().fetchrow("DELETE FROM patreon_collegamenti WHERE discord_user_id = $1 RETURNING patreon_id", discord_user_id)
    await piani.revoca("utente", discord_user_id, "patreon")
    return riga is not None


# ---------------------------------------------------------------- webhook
async def mappa_livelli() -> dict[str, str]:
    return {r["tier_id"]: r["livello"] for r in await _pool().fetch("SELECT tier_id, livello FROM patreon_livelli")}


async def imposta_livello_tier(tier_id: str, livello: str | None) -> None:
    """L'owner associa un livello Patreon a un livello del bot (None = toglie l'associazione)."""
    if not tier_id or len(tier_id) > 40 or not tier_id.isalnum():
        raise piani.PianoNonValido("tier")
    if livello is None:
        await _pool().execute("DELETE FROM patreon_livelli WHERE tier_id = $1", tier_id)
    else:
        if livello not in piani.LIVELLI_A_PAGAMENTO:
            raise piani.PianoNonValido("livello")
        await _pool().execute(
            "INSERT INTO patreon_livelli (tier_id, livello) VALUES ($1, $2) ON CONFLICT (tier_id) DO UPDATE SET livello = EXCLUDED.livello",
            tier_id, livello,
        )
    await _risincronizza_tutti()


async def _risincronizza_tutti() -> None:
    for riga in await _pool().fetch("SELECT patreon_id FROM patreon_collegamenti"):
        await sincronizza(riga["patreon_id"])


async def sincronizza(patreon_id: str) -> str | None:
    """Allinea la concessione `patreon` della persona collegata allo stato salvato. Restituisce il livello dato, o None."""
    collegato = await _pool().fetchval("SELECT discord_user_id FROM patreon_collegamenti WHERE patreon_id = $1", patreon_id)
    if collegato is None:
        return None
    membro = await _pool().fetchrow("SELECT attivo, tiers FROM patreon_membri WHERE patreon_id = $1", patreon_id)
    livello = livello_da_tiers(membro["tiers"], await mappa_livelli()) if membro and membro["attivo"] else None
    if livello is None:
        await piani.revoca("utente", collegato, "patreon")
        return None
    await piani.concedi("utente", collegato, livello, "patreon", giorni=GIORNI_DI_GRAZIA, riferimento="patreon")
    return livello


async def applica_evento(evento: EventoPatreon, corpo: bytes) -> bool:
    """
    Un evento del webhook. False se già visto (stesso corpo): Patreon ripete gli eventi se non risponde in tempo.
    Salvare l'evento e lo stato è una transazione sola.
    """
    async with _pool().acquire() as conn, conn.transaction():
        nuovo = await conn.fetchval(
            "INSERT INTO patreon_eventi (impronta, tipo) VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING 1",
            impronta_corpo(corpo), evento.tipo,
        )
        if nuovo is None:
            return False
        await conn.execute("DELETE FROM patreon_eventi WHERE ricevuto_il < now() - make_interval(days => $1)", CONSERVA_EVENTI_GIORNI)
        # Un evento più vecchio dell'ultimo addebito già visto è un rimando: non rimette in piedi un sostegno disdetto.
        visto = await conn.fetchval("SELECT ultima_carica FROM patreon_membri WHERE patreon_id = $1 FOR UPDATE", evento.patreon_id)
        if evento.ultima_carica is not None and visto is not None and evento.ultima_carica < visto:
            logger.info("Evento Patreon più vecchio dello stato salvato: ignorato.")
            return False
        await conn.execute(
            """
            INSERT INTO patreon_membri (patreon_id, member_id, attivo, tiers, ultima_carica) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (patreon_id) DO UPDATE SET member_id = EXCLUDED.member_id, attivo = EXCLUDED.attivo,
                tiers = EXCLUDED.tiers, aggiornato_il = now(),
                ultima_carica = COALESCE(EXCLUDED.ultima_carica, patreon_membri.ultima_carica)
            """,
            evento.patreon_id, evento.member_id, evento.attivo, list(evento.tiers), evento.ultima_carica,
        )
    await sincronizza(evento.patreon_id)
    return True

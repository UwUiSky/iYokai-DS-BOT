"""
core/command_permissions.py
===========================
Nascondere dalla lista i gruppi di comandi a chi non può usarli (#148, D24).

La lista dei comandi la decide Discord, da `default_permissions` e dalle regole per
ruolo impostate in Impostazioni → Integrazioni. Il token del bot non può scrivere
quelle regole: serve il token OAuth2 di un admin con scope
`applications.commands.permissions.update`. Questo modulo ha tutto ciò che si può
provare senza Discord vero: lo state firmato, il link, la fusione delle regole,
il client HTTP e l'applicazione del ruolo scelto.
Funzioni coperte: SPEC §20 (#148)
Dipende da: core/command_access.py, core/oauth_crypto.py

Senza autorizzazione resta la base: permessi di Discord + controllo nel codice.
Le regole si UNISCONO a quelle già impostate dall'admin (la scrittura di Discord
sostituisce tutto): si toglie solo il ruolo che il bot aveva messo prima.
Limiti: al massimo 100 regole per comando; una regola non dà il comando a chi non
ha il ruolo, lo rende visibile a chi lo ha. Mai un token nei log né nei messaggi.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core.command_access import TipoRuolo

logger = logging.getLogger("iyokai.command_permissions")

SCOPE = "applications.commands.permissions.update"
URL_AUTORIZZAZIONE = "https://discord.com/oauth2/authorize"
API = "https://discord.com/api/v10"
MAX_REGOLE = 100
TIPO_REGOLA_RUOLO = 1
STATE_TTL_SECONDI = 15 * 60
RINNOVA_SE_SCADE_ENTRO = timedelta(hours=6)
_HKDF_INFO = b"iyokai-command-permissions-state-v1"
_SCOPO_STATE = "cmdperm"

STATO_OK = "ok"
STATO_PARZIALE = "parziale"
STATO_SENZA_AUTORIZZAZIONE = "senza_autorizzazione"
STATO_TOKEN_NON_VALIDO = "token_non_valido"

# Quali gruppi apre ogni ruolo scelto nel setup (issue #148).
GRUPPI_DEL_RUOLO: dict[TipoRuolo, tuple[str, ...]] = {
    TipoRuolo.ADMIN: ("admin", "gestione", "moduli", "security", "automod", "log"),
    TipoRuolo.MOD: ("mod",),
    TipoRuolo.MODBAN: ("modban",),
}


class PermessiNonConfigurati(RuntimeError):
    """Manca OAUTH_ENCRYPTION_KEY: senza chiave niente state firmato né token salvati."""


class TroppeRegole(ValueError):
    """Il comando ha già 100 regole: Discord non ne accetta altre."""


class ErroreDiscord(RuntimeError):
    """Risposta non riuscita di Discord. Porta solo il codice: mai il corpo né i token."""

    def __init__(self, stato: int, dettaglio: str = "") -> None:
        self.stato = stato
        super().__init__(f"Discord ha risposto {stato}")


@dataclass(frozen=True)
class TokenPermessi:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    scade_il: datetime
    user_id: int | None = None


@dataclass(frozen=True)
class StatoOAuth:
    guild_id: int
    user_id: int


@dataclass
class EsitoPermessi:
    stato: str
    gruppi_scritti: list[str] = field(default_factory=list)
    saltati: list[str] = field(default_factory=list)
    errori: dict = field(default_factory=dict)


# ----------------------------------------------------------------------
# State firmato (scade presto) e link di autorizzazione
# ----------------------------------------------------------------------
def _chiave_firma(chiave_b64: str) -> bytes:
    if not chiave_b64:
        raise PermessiNonConfigurati("OAUTH_ENCRYPTION_KEY non è impostata.")
    try:
        base = base64.urlsafe_b64decode(chiave_b64)
    except Exception as exc:
        raise PermessiNonConfigurati("OAUTH_ENCRYPTION_KEY non è base64 valido.") from exc
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(base)


def crea_state(guild_id: int, user_id: int, chiave_b64: str, *, ora: float | None = None) -> str:
    adesso = time.time() if ora is None else ora
    corpo = json.dumps(
        {
            "p": _SCOPO_STATE,
            "g": guild_id,
            "u": user_id,
            "e": adesso + STATE_TTL_SECONDI,
            "n": base64.urlsafe_b64encode(os.urandom(12)).decode("ascii"),
        },
        separators=(",", ":"),
    ).encode()
    firma = hmac.new(_chiave_firma(chiave_b64), corpo, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(corpo).decode("ascii") + "." + firma


def verifica_state(raw: str, chiave_b64: str, *, ora: float | None = None) -> StatoOAuth | None:
    """None se malformato, manomesso, scaduto o nato per un altro scopo. Mai un'eccezione."""
    if "." not in raw:
        return None
    corpo_b64, _, firma = raw.partition(".")
    try:
        corpo = base64.urlsafe_b64decode(corpo_b64 + "=" * (-len(corpo_b64) % 4))
        attesa = hmac.new(_chiave_firma(chiave_b64), corpo, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(attesa.encode(), firma.encode()):
            return None
        dati = json.loads(corpo)
        if dati["p"] != _SCOPO_STATE or float(dati["e"]) <= (time.time() if ora is None else ora):
            return None
        return StatoOAuth(guild_id=int(dati["g"]), user_id=int(dati["u"]))
    except (PermessiNonConfigurati, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def url_autorizzazione(
    client_id: str, redirect_uri: str, guild_id: int, user_id: int, chiave_b64: str
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": crea_state(guild_id, user_id, chiave_b64),
        }
    )
    return f"{URL_AUTORIZZAZIONE}?{query}"


# ----------------------------------------------------------------------
# Regole
# ----------------------------------------------------------------------
def unisci_regole(
    esistenti: list[dict], ruolo_vecchio: int | None, ruolo_nuovo: int | None
) -> list[dict]:
    """Toglie la regola del ruolo che il bot aveva messo, aggiunge quella nuova, tiene il resto."""

    def e_nostro_vecchio(regola: dict) -> bool:
        return (
            ruolo_vecchio is not None
            and regola.get("type") == TIPO_REGOLA_RUOLO
            and str(regola.get("id")) == str(ruolo_vecchio)
        )

    regole = [r for r in esistenti if not e_nostro_vecchio(r)]
    if ruolo_nuovo is not None:
        nostra = {"id": str(ruolo_nuovo), "type": TIPO_REGOLA_RUOLO, "permission": True}
        if not any(r.get("type") == TIPO_REGOLA_RUOLO and str(r.get("id")) == str(ruolo_nuovo) for r in regole):
            regole.append(nostra)
    if len(regole) > MAX_REGOLE:
        raise TroppeRegole(f"Il comando avrebbe {len(regole)} regole, il massimo è {MAX_REGOLE}.")
    return regole


# ----------------------------------------------------------------------
# Client HTTP (la sessione aiohttp si passa da fuori: nei test è finta)
# ----------------------------------------------------------------------
class ClientPermessi:
    def __init__(self, sessione, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self._sessione = sessione
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def __repr__(self) -> str:  # niente segreti nei log
        return f"ClientPermessi(client_id={self._client_id!r})"

    async def _chiedi(self, metodo: str, url: str, **kw):
        async with self._sessione.request(metodo, url, **kw) as risposta:
            if risposta.status >= 400:
                raise ErroreDiscord(risposta.status)
            return await risposta.json(content_type=None)

    def _token(self, corpo: dict, user_id: int | None = None) -> TokenPermessi:
        return TokenPermessi(
            access_token=corpo["access_token"],
            refresh_token=corpo["refresh_token"],
            scade_il=datetime.now(timezone.utc) + timedelta(seconds=int(corpo.get("expires_in", 604800))),
            user_id=user_id,
        )

    async def scambia_codice(self, codice: str, user_id: int | None = None) -> TokenPermessi:
        corpo = await self._chiedi(
            "POST",
            f"{API}/oauth2/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "authorization_code",
                "code": codice,
                "redirect_uri": self._redirect_uri,
            },
        )
        return self._token(corpo, user_id)

    async def rinnova(self, refresh_token: str, user_id: int | None = None) -> TokenPermessi:
        corpo = await self._chiedi(
            "POST",
            f"{API}/oauth2/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        return self._token(corpo, user_id)

    def _url(self, app_id: int, guild_id: int, command_id: int) -> str:
        return f"{API}/applications/{app_id}/guilds/{guild_id}/commands/{command_id}/permissions"

    async def leggi(self, app_id: int, guild_id: int, command_id: int, token: str) -> list[dict]:
        try:
            corpo = await self._chiedi(
                "GET", self._url(app_id, guild_id, command_id), headers={"Authorization": f"Bearer {token}"}
            )
        except ErroreDiscord as e:
            if e.stato == 404:  # nessuna regola ancora impostata
                return []
            raise
        return list(corpo.get("permissions", []))

    async def scrivi(self, app_id: int, guild_id: int, command_id: int, regole: list[dict], token: str) -> None:
        await self._chiedi(
            "PUT",
            self._url(app_id, guild_id, command_id),
            headers={"Authorization": f"Bearer {token}"},
            json={"permissions": regole},
        )


# ----------------------------------------------------------------------
# Applicare il ruolo scelto
# ----------------------------------------------------------------------
async def applica_ruolo(
    guild_id: int,
    tipo: TipoRuolo,
    ruolo_vecchio: int | None,
    ruolo_nuovo: int | None,
    *,
    repo,
    client,
    app_id: int,
    comandi: dict[str, int],
) -> EsitoPermessi:
    """
    Scrive le regole dei gruppi legati a `tipo`. `comandi` è {nome del gruppo: id del
    comando su Discord}. Senza token salvato non fa niente: resta la base.
    """
    token = await repo.get(guild_id)
    if token is None:
        return EsitoPermessi(STATO_SENZA_AUTORIZZAZIONE)

    try:
        if token.scade_il - datetime.now(timezone.utc) < RINNOVA_SE_SCADE_ENTRO:
            token = await client.rinnova(token.refresh_token)
            if token.user_id is None:
                precedente = await repo.get(guild_id)
                token = TokenPermessi(token.access_token, token.refresh_token, token.scade_il,
                                      precedente.user_id if precedente else None)
            await repo.salva(guild_id, token.user_id, token)
    except ErroreDiscord:
        await repo.cancella(guild_id)
        return EsitoPermessi(STATO_TOKEN_NON_VALIDO)

    esito = EsitoPermessi(STATO_OK)
    for nome in GRUPPI_DEL_RUOLO[tipo]:
        command_id = comandi.get(nome)
        if command_id is None:
            esito.saltati.append(nome)
            continue
        try:
            esistenti = await client.leggi(app_id, guild_id, command_id, token.access_token)
            regole = unisci_regole(esistenti, ruolo_vecchio, ruolo_nuovo)
            await client.scrivi(app_id, guild_id, command_id, regole, token.access_token)
            esito.gruppi_scritti.append(nome)
        except TroppeRegole:
            esito.errori[nome] = "troppe_regole"
        except ErroreDiscord as e:
            if e.stato in (401, 403):  # token revocato o admin senza più permessi
                await repo.cancella(guild_id)
                return EsitoPermessi(STATO_TOKEN_NON_VALIDO, esito.gruppi_scritti, esito.saltati, esito.errori)
            esito.errori[nome] = e.stato
    if esito.errori:
        esito.stato = STATO_PARZIALE
    return esito


# ----------------------------------------------------------------------
# Collegamento al bot (usato da main.py tramite command_access.registra_dopo_imposta_ruolo)
# ----------------------------------------------------------------------
async def sincronizza_dal_bot(bot, guild, tipo: TipoRuolo, ruolo_vecchio: int | None, ruolo_nuovo: int | None):
    """
    Dopo che l'admin sceglie un ruolo: scrive i permessi dei gruppi su Discord, se il
    server ha autorizzato il bot. Senza OAuth2 configurato o senza token non fa niente.
    """
    import aiohttp

    from core.config import config
    from core.repositories.command_permission_token_repo import command_permission_token_repo

    if not (config.OAUTH2_CLIENT_ID and config.OAUTH2_CLIENT_SECRET and config.OAUTH_ENCRYPTION_KEY):
        return None
    if await command_permission_token_repo.get(guild.id) is None:
        return None
    comandi = {c.name: c.id for c in await bot.tree.fetch_commands()}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sessione:
        client = ClientPermessi(sessione, config.OAUTH2_CLIENT_ID, config.OAUTH2_CLIENT_SECRET, config.OAUTH2_REDIRECT_URI)
        esito = await applica_ruolo(
            guild.id, tipo, ruolo_vecchio, ruolo_nuovo,
            repo=command_permission_token_repo, client=client,
            app_id=bot.application_id, comandi=comandi,
        )
    if esito.stato != STATO_OK:
        logger.warning("Permessi dei comandi nel server %s: %s (errori: %s)", guild.id, esito.stato, esito.errori)
    return esito

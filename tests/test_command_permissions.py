"""
tests/test_command_permissions.py
=================================
#148: nascondere i gruppi dalla lista a chi non può usarli, scrivendo i permessi dei
comandi con il token OAuth2 dell'admin. Qui tutto con HTTP finto: nessun token vero.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

from core import command_permissions as cp
from core.command_access import TipoRuolo
from core.oauth_crypto import generate_key

CHIAVE = generate_key()
GUILD = 5000


# ------------------------------------------------------------------ gruppi per ruolo
def test_i_gruppi_di_ogni_ruolo_sono_quelli_della_issue():
    assert cp.GRUPPI_DEL_RUOLO[TipoRuolo.ADMIN] == ("admin", "gestione", "moduli", "security", "automod", "log")
    assert cp.GRUPPI_DEL_RUOLO[TipoRuolo.MOD] == ("mod",)
    assert cp.GRUPPI_DEL_RUOLO[TipoRuolo.MODBAN] == ("modban",)


def test_i_gruppi_esistono_nella_mappa_dei_comandi():
    from core.command_groups import nomi_gruppi

    for gruppi in cp.GRUPPI_DEL_RUOLO.values():
        assert set(gruppi) <= set(nomi_gruppi())


# ------------------------------------------------------------------ regole
def test_unisci_regole_aggiunge_il_ruolo_e_tiene_le_regole_dell_admin():
    esistenti = [{"id": "11", "type": 2, "permission": True}, {"id": "22", "type": 1, "permission": False}]
    nuove = cp.unisci_regole(esistenti, ruolo_vecchio=None, ruolo_nuovo=33)
    assert {"id": "33", "type": 1, "permission": True} in nuove
    assert esistenti[0] in nuove and esistenti[1] in nuove


def test_cambiando_ruolo_il_vecchio_esce_e_il_nuovo_entra():
    esistenti = [{"id": "33", "type": 1, "permission": True}, {"id": "11", "type": 2, "permission": True}]
    nuove = cp.unisci_regole(esistenti, ruolo_vecchio=33, ruolo_nuovo=44)
    assert [r["id"] for r in nuove] == ["11", "44"]


def test_togliendo_il_ruolo_esce_solo_il_nostro():
    esistenti = [{"id": "33", "type": 1, "permission": True}, {"id": "11", "type": 2, "permission": True}]
    assert cp.unisci_regole(esistenti, ruolo_vecchio=33, ruolo_nuovo=None) == [esistenti[1]]


def test_non_si_raddoppia_la_regola_del_ruolo():
    esistenti = [{"id": "33", "type": 1, "permission": True}]
    assert cp.unisci_regole(esistenti, ruolo_vecchio=None, ruolo_nuovo=33) == esistenti


def test_oltre_100_regole_si_rifiuta():
    esistenti = [{"id": str(i), "type": 2, "permission": True} for i in range(100)]
    with pytest.raises(cp.TroppeRegole):
        cp.unisci_regole(esistenti, ruolo_vecchio=None, ruolo_nuovo=999)


def test_con_cento_regole_e_il_ruolo_gia_dentro_va_bene():
    esistenti = [{"id": str(i), "type": 1, "permission": True} for i in range(100)]
    # il vecchio (5) esce, il nuovo (7) c'era già: restano 99
    assert len(cp.unisci_regole(esistenti, ruolo_vecchio=5, ruolo_nuovo=7)) == 99


# ------------------------------------------------------------------ state e link
def test_il_link_porta_lo_scope_giusto_e_uno_state_firmato():
    url = cp.url_autorizzazione("CID", "https://x.example/cb", GUILD, 77, CHIAVE)
    assert "applications.commands.permissions.update" in url.replace("%2E", ".")
    assert "client_id=CID" in url and "response_type=code" in url
    state = url.split("state=")[1].split("&")[0]
    from urllib.parse import unquote

    letto = cp.verifica_state(unquote(state), CHIAVE)
    assert (letto.guild_id, letto.user_id) == (GUILD, 77)


def test_uno_state_manomesso_o_scaduto_o_di_un_altro_scopo_e_rifiutato():
    state = cp.crea_state(GUILD, 77, CHIAVE, ora=1000.0)
    assert cp.verifica_state(state, CHIAVE, ora=1000.0 + 10) is not None
    assert cp.verifica_state(state, CHIAVE, ora=1000.0 + cp.STATE_TTL_SECONDI + 1) is None
    corpo, firma = state.split(".")
    assert cp.verifica_state(corpo + "." + "0" * len(firma), CHIAVE, ora=1000.0) is None
    assert cp.verifica_state("spazzatura", CHIAVE) is None
    # uno state del ripristino utenti non vale qui
    from core.restore_oauth_logic import RestoreState, encode_state

    altro = encode_state(RestoreState(1, 2, 3), CHIAVE)
    assert cp.verifica_state(altro, CHIAVE) is None


def test_senza_chiave_nessuno_state():
    with pytest.raises(cp.PermessiNonConfigurati):
        cp.crea_state(GUILD, 1, "")
    assert cp.verifica_state("a.b", "") is None


# ------------------------------------------------------------------ client HTTP finto
class _Risposta:
    def __init__(self, stato, corpo):
        self.status = stato
        self._corpo = corpo

    async def json(self, content_type=None):
        return self._corpo

    async def text(self):
        return str(self._corpo)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class SessioneFinta:
    def __init__(self, risposte):
        self.risposte = list(risposte)
        self.chiamate = []

    def request(self, metodo, url, **kw):
        self.chiamate.append((metodo, url, kw))
        return self.risposte.pop(0)


@pytest.mark.asyncio
async def test_il_client_scambia_il_codice_senza_stampare_i_segreti():
    sessione = SessioneFinta([_Risposta(200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 604800})])
    client = cp.ClientPermessi(sessione, "CID", "SEGRETO", "https://x.example/cb")

    token = await client.scambia_codice("CODICE")

    assert token.access_token == "AT" and token.refresh_token == "RT"
    assert 600_000 < (token.scade_il - datetime.now(timezone.utc)).total_seconds() <= 604_800
    metodo, url, kw = sessione.chiamate[0]
    assert metodo == "POST" and url.endswith("/oauth2/token")
    assert kw["data"]["grant_type"] == "authorization_code"
    assert "SEGRETO" not in repr(client) and "AT" not in repr(token)


@pytest.mark.asyncio
async def test_errore_http_diventa_errore_discord_senza_il_token_nel_messaggio():
    sessione = SessioneFinta([_Risposta(401, {"message": "401: Unauthorized"})])
    client = cp.ClientPermessi(sessione, "CID", "S", "r")

    with pytest.raises(cp.ErroreDiscord) as e:
        await client.leggi(1, GUILD, 9, "TOKEN-SEGRETO")

    assert e.value.stato == 401
    assert "TOKEN-SEGRETO" not in str(e.value)


# ------------------------------------------------------------------ orchestrazione
class RepoFinto:
    def __init__(self, token):
        self.token = token
        self.salvati = []
        self.cancellati = []

    async def get(self, guild_id):
        return self.token

    async def salva(self, guild_id, user_id, token):
        self.salvati.append((guild_id, user_id, token))
        self.token = token

    async def cancella(self, guild_id):
        self.cancellati.append(guild_id)
        self.token = None


class ClientFinto:
    def __init__(self, esistenti=None, fallisce_su=None):
        self.esistenti = esistenti or {}
        self.scritti = {}
        self.fallisce_su = fallisce_su or {}
        self.rinnovi = 0

    async def leggi(self, app_id, guild_id, command_id, token):
        return list(self.esistenti.get(command_id, []))

    async def scrivi(self, app_id, guild_id, command_id, regole, token):
        if command_id in self.fallisce_su:
            raise cp.ErroreDiscord(self.fallisce_su[command_id], "x")
        self.scritti[command_id] = regole

    async def rinnova(self, refresh_token):
        self.rinnovi += 1
        return cp.TokenPermessi("NUOVO", "NUOVO-R", datetime.now(timezone.utc) + timedelta(days=7))


def _token(scade_tra_ore=100):
    return cp.TokenPermessi("AT", "RT", datetime.now(timezone.utc) + timedelta(hours=scade_tra_ore), user_id=77)


COMANDI = {"admin": 1, "gestione": 2, "moduli": 3, "security": 4, "automod": 5, "log": 6, "mod": 7, "modban": 8}


@pytest.mark.asyncio
async def test_senza_autorizzazione_non_scrive_niente_e_lo_dice():
    client = ClientFinto()
    esito = await cp.applica_ruolo(GUILD, TipoRuolo.ADMIN, None, 33, repo=RepoFinto(None), client=client, app_id=1, comandi=COMANDI)

    assert esito.stato == cp.STATO_SENZA_AUTORIZZAZIONE
    assert client.scritti == {}


@pytest.mark.asyncio
async def test_il_ruolo_admin_arriva_a_sei_gruppi():
    client = ClientFinto()
    esito = await cp.applica_ruolo(GUILD, TipoRuolo.ADMIN, None, 33, repo=RepoFinto(_token()), client=client, app_id=1, comandi=COMANDI)

    assert esito.stato == cp.STATO_OK
    assert sorted(client.scritti) == [1, 2, 3, 4, 5, 6]
    assert client.scritti[1] == [{"id": "33", "type": 1, "permission": True}]
    assert sorted(esito.gruppi_scritti) == sorted(cp.GRUPPI_DEL_RUOLO[TipoRuolo.ADMIN])


@pytest.mark.asyncio
async def test_il_ruolo_mod_arriva_solo_a_mod():
    client = ClientFinto()
    await cp.applica_ruolo(GUILD, TipoRuolo.MOD, 5, 6, repo=RepoFinto(_token()), client=client, app_id=1, comandi=COMANDI)
    assert list(client.scritti) == [7]


@pytest.mark.asyncio
async def test_token_in_scadenza_viene_rinnovato_e_salvato():
    repo, client = RepoFinto(_token(scade_tra_ore=1)), ClientFinto()

    await cp.applica_ruolo(GUILD, TipoRuolo.MODBAN, None, 6, repo=repo, client=client, app_id=1, comandi=COMANDI)

    assert client.rinnovi == 1
    assert repo.salvati and repo.salvati[0][2].access_token == "NUOVO"
    assert repo.salvati[0][1] == 77


@pytest.mark.asyncio
async def test_token_rifiutato_da_discord_viene_dimenticato():
    repo = RepoFinto(_token())
    client = ClientFinto(fallisce_su={7: 401})

    esito = await cp.applica_ruolo(GUILD, TipoRuolo.MOD, None, 6, repo=repo, client=client, app_id=1, comandi=COMANDI)

    assert esito.stato == cp.STATO_TOKEN_NON_VALIDO
    assert repo.cancellati == [GUILD]


@pytest.mark.asyncio
async def test_un_gruppo_che_fallisce_non_ferma_gli_altri():
    client = ClientFinto(fallisce_su={2: 500})

    esito = await cp.applica_ruolo(GUILD, TipoRuolo.ADMIN, None, 33, repo=RepoFinto(_token()), client=client, app_id=1, comandi=COMANDI)

    assert esito.stato == cp.STATO_PARZIALE
    assert sorted(client.scritti) == [1, 3, 4, 5, 6]
    assert esito.errori == {"gestione": 500}


@pytest.mark.asyncio
async def test_gruppo_non_ancora_sincronizzato_viene_saltato():
    comandi = {k: v for k, v in COMANDI.items() if k != "log"}
    client = ClientFinto()

    esito = await cp.applica_ruolo(GUILD, TipoRuolo.ADMIN, None, 33, repo=RepoFinto(_token()), client=client, app_id=1, comandi=comandi)

    assert esito.saltati == ["log"]
    assert 6 not in client.scritti


@pytest.mark.asyncio
async def test_troppe_regole_su_un_gruppo_si_segnalano_senza_scrivere():
    cento = [{"id": str(i), "type": 2, "permission": True} for i in range(100)]
    client = ClientFinto(esistenti={7: cento})

    esito = await cp.applica_ruolo(GUILD, TipoRuolo.MOD, None, 6, repo=RepoFinto(_token()), client=client, app_id=1, comandi=COMANDI)

    assert esito.errori == {"mod": "troppe_regole"}
    assert 7 not in client.scritti


# ------------------------------------------------------------------ archivio dei token
@pytest.mark.asyncio
async def test_il_token_si_salva_cifrato_e_si_rilegge(clean_db):
    from core.repositories.command_permission_token_repo import CommandPermissionTokenRepository

    repo = CommandPermissionTokenRepository(pool_provider=lambda: clean_db, chiave_provider=lambda: CHIAVE)
    await repo.salva(GUILD, 77, _token())

    grezzo = await clean_db.fetchrow("SELECT * FROM command_permission_tokens")
    assert "AT" != grezzo["encrypted_access_token"] and "RT" != grezzo["encrypted_refresh_token"]
    letto = await repo.get(GUILD)
    assert (letto.access_token, letto.refresh_token, letto.user_id) == ("AT", "RT", 77)

    await repo.cancella(GUILD)
    assert await repo.get(GUILD) is None


@pytest.mark.asyncio
async def test_senza_chiave_di_cifratura_non_si_salva(clean_db):
    from core.repositories.command_permission_token_repo import CommandPermissionTokenRepository

    repo = CommandPermissionTokenRepository(pool_provider=lambda: clean_db, chiave_provider=lambda: "")
    with pytest.raises(cp.PermessiNonConfigurati):
        await repo.salva(GUILD, 77, _token())


# ------------------------------------------------------------------ collegamento a imposta_ruolo
@pytest.mark.asyncio
async def test_imposta_ruolo_avvisa_chi_si_e_registrato_con_vecchio_e_nuovo(clean_db, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    import core.command_access as ca
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    guild = MagicMock()
    guild.id = GUILD
    guild.get_role = lambda rid: object()
    ruolo = MagicMock()
    ruolo.id = 33
    chiamate = []

    async def callback(g, tipo, vecchio, nuovo):
        chiamate.append((tipo, vecchio, nuovo))

    ca.registra_dopo_imposta_ruolo(callback)
    try:
        await ca.imposta_ruolo(guild, TipoRuolo.ADMIN, ruolo)
        nuovo_ruolo = MagicMock()
        nuovo_ruolo.id = 44
        await ca.imposta_ruolo(guild, TipoRuolo.ADMIN, nuovo_ruolo)
        await ca.imposta_ruolo(guild, TipoRuolo.ADMIN, None)
    finally:
        ca.registra_dopo_imposta_ruolo(None)

    assert chiamate == [(TipoRuolo.ADMIN, None, 33), (TipoRuolo.ADMIN, 33, 44), (TipoRuolo.ADMIN, 44, None)]


@pytest.mark.asyncio
async def test_se_il_callback_fallisce_il_ruolo_resta_salvato(clean_db, monkeypatch):
    from unittest.mock import MagicMock

    import core.command_access as ca
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    guild = MagicMock()
    guild.id = GUILD
    guild.get_role = lambda rid: object()
    ruolo = MagicMock()
    ruolo.id = 33

    async def rotto(*a):
        raise RuntimeError("discord giù")

    ca.registra_dopo_imposta_ruolo(rotto)
    try:
        await ca.imposta_ruolo(guild, TipoRuolo.MOD, ruolo)
    finally:
        ca.registra_dopo_imposta_ruolo(None)

    assert await ca.leggi_ruolo(GUILD, TipoRuolo.MOD) == 33


@pytest.mark.asyncio
async def test_senza_oauth_configurato_la_sincronizzazione_non_fa_niente(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import core.config as config_module

    monkeypatch.setattr(
        config_module, "config", SimpleNamespace(OAUTH2_CLIENT_ID="", OAUTH2_CLIENT_SECRET="", OAUTH_ENCRYPTION_KEY="")
    )
    guild = MagicMock()
    guild.id = GUILD

    assert await cp.sincronizza_dal_bot(MagicMock(), guild, TipoRuolo.ADMIN, None, 33) is None


@pytest.mark.asyncio
async def test_il_client_scrive_sul_percorso_giusto_con_il_bearer():
    sessione = SessioneFinta([_Risposta(200, {})])
    client = cp.ClientPermessi(sessione, "CID", "S", "r")

    await client.scrivi(11, GUILD, 22, [{"id": "1", "type": 1, "permission": True}], "TOK")

    metodo, url, kw = sessione.chiamate[0]
    assert metodo == "PUT"
    assert url == f"https://discord.com/api/v10/applications/11/guilds/{GUILD}/commands/22/permissions"
    assert kw["headers"] == {"Authorization": "Bearer TOK"}
    assert kw["json"] == {"permissions": [{"id": "1", "type": 1, "permission": True}]}


# ------------------------------------------------------------------ secondo giro (cacciatore-bug 12/10)
class ClientConRotazione:
    """Come Discord: ogni rinnovo brucia il refresh token e ne dà uno nuovo; il vecchio dà 400 invalid_grant."""

    def __init__(self, validi=("RT",), errore=None):
        self.validi = set(validi)
        self.errore = errore  # (stato, codice) da sollevare a ogni rinnovo
        self.rinnovi = 0
        self.scritti = {}

    async def rinnova(self, refresh_token):
        self.rinnovi += 1
        await asyncio.sleep(0.05)
        if self.errore:
            raise cp.ErroreDiscord(*self.errore)
        if refresh_token not in self.validi:
            raise cp.ErroreDiscord(400, "invalid_grant")
        self.validi.discard(refresh_token)
        nuovo = f"RT{self.rinnovi}"
        self.validi.add(nuovo)
        return cp.TokenPermessi(f"AT{self.rinnovi}", nuovo, datetime.now(timezone.utc) + timedelta(days=7))

    async def leggi(self, app_id, guild_id, command_id, token):
        return []

    async def scrivi(self, app_id, guild_id, command_id, regole, token):
        self.scritti[command_id] = regole


@pytest.mark.asyncio
@pytest.mark.parametrize("stato,codice", [(429, ""), (500, ""), (503, ""), (0, ""), (400, "invalid_request")])
async def test_un_rinnovo_che_non_riesce_per_colpa_di_discord_non_cancella_il_token(stato, codice):
    repo = RepoFinto(_token(scade_tra_ore=1))
    client = ClientConRotazione(errore=(stato, codice))

    esito = await cp.applica_ruolo(GUILD, TipoRuolo.MOD, None, 6, repo=repo, client=client, app_id=1, comandi=COMANDI)

    assert esito.stato == cp.STATO_DA_RIPROVARE
    assert repo.cancellati == [] and repo.token is not None
    assert client.scritti == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("stato", [400, 401])
async def test_solo_invalid_grant_cancella_il_token(stato):
    repo = RepoFinto(_token(scade_tra_ore=1))
    client = ClientConRotazione(errore=(stato, "invalid_grant"))

    esito = await cp.applica_ruolo(GUILD, TipoRuolo.MOD, None, 6, repo=repo, client=client, app_id=1, comandi=COMANDI)

    assert esito.stato == cp.STATO_TOKEN_NON_VALIDO
    assert repo.cancellati == [GUILD]


@pytest.mark.asyncio
async def test_il_client_vero_legge_il_codice_ma_non_il_corpo():
    class Risposta:
        status = 400

        async def json(self, content_type=None):
            return {"error": "invalid_grant", "error_description": "refresh_token=SEGRETO"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Sessione:
        def request(self, *a, **k):
            return Risposta()

    with pytest.raises(cp.ErroreDiscord) as e:
        await cp.ClientPermessi(Sessione(), "C", "S", "r").rinnova("RT")

    assert e.value.token_non_piu_valido
    assert "SEGRETO" not in str(e.value) and "SEGRETO" not in repr(e.value.__dict__)


@pytest.mark.asyncio
async def test_due_rinnovi_insieme_non_si_calpestano(clean_db):
    """Gather vera su un database vero: il secondo rinnovo non brucia il token nuovo del primo."""
    from core.repositories.command_permission_token_repo import CommandPermissionTokenRepository
    from tests.support.concorrenza import apri_connessioni

    repo = CommandPermissionTokenRepository(pool_provider=lambda: clean_db, chiave_provider=lambda: CHIAVE)
    await repo.salva(GUILD, 77, cp.TokenPermessi("AT", "RT", datetime.now(timezone.utc) + timedelta(hours=1)))
    client = ClientConRotazione()
    await apri_connessioni(clean_db, 3)

    esiti = await asyncio.gather(
        *(cp.applica_ruolo(GUILD, TipoRuolo.MOD, None, 6, repo=repo, client=client, app_id=1, comandi=COMANDI) for _ in range(3))
    )

    assert [e.stato for e in esiti] == [cp.STATO_OK] * 3
    assert client.rinnovi == 1  # gli altri due usano il token appena salvato
    salvato = await repo.get(GUILD)
    assert salvato is not None and salvato.refresh_token == "RT1" and salvato.user_id == 77


@pytest.mark.asyncio
async def test_un_invalid_grant_dopo_la_rotazione_di_un_altro_non_cancella(monkeypatch):
    """Il refresh token e' stato ruotato da un altro processo tra la lettura e il rinnovo."""
    repo = RepoFinto(_token(scade_tra_ore=1))
    nuovo = cp.TokenPermessi("AT-N", "RT-N", datetime.now(timezone.utc) + timedelta(days=7), user_id=77)

    class Client(ClientConRotazione):
        async def rinnova(self, refresh_token):
            repo.token = nuovo  # l'altro processo ha appena salvato il token ruotato
            raise cp.ErroreDiscord(400, "invalid_grant")

    esito = await cp.applica_ruolo(GUILD, TipoRuolo.MOD, None, 6, repo=repo, client=Client(), app_id=1, comandi=COMANDI)

    assert esito.stato == cp.STATO_OK and repo.cancellati == []


def test_una_regola_nega_sul_ruolo_scelto_diventa_consenti():
    esistenti = [{"id": "33", "type": 1, "permission": False}, {"id": "9", "type": 1, "permission": False}]

    regole = cp.unisci_regole(esistenti, None, 33)

    assert {"id": "33", "type": 1, "permission": True} in regole
    assert {"id": "9", "type": 1, "permission": False} in regole  # le altre regole dell'admin non si toccano
    assert len(regole) == 2


def test_lo_state_si_usa_una_volta_sola():
    state = cp.crea_state(GUILD, 77, CHIAVE)

    primo = cp.consuma_state(state, CHIAVE)
    assert primo is not None
    assert cp.consuma_state(state, CHIAVE) is None  # in uso
    cp.rilascia_state(primo, consumato=False)
    secondo = cp.consuma_state(state, CHIAVE)  # un errore temporaneo non brucia il link
    assert secondo is not None
    cp.rilascia_state(secondo, consumato=True)
    assert cp.consuma_state(state, CHIAVE) is None  # bruciato


def test_lo_state_dura_pochi_minuti():
    assert cp.STATE_TTL_SECONDI <= 5 * 60


class ClientDiRitorno:
    def __init__(self, user_id=77, errore=False):
        self.user_id, self.errore = user_id, errore

    async def scambia_codice(self, codice, user_id=None):
        if self.errore:
            raise cp.ErroreDiscord(400, "invalid_grant")
        return cp.TokenPermessi("AT", "RT", datetime.now(timezone.utc) + timedelta(days=7))

    async def utente_corrente(self, token):
        return self.user_id


@pytest.mark.asyncio
async def test_la_callback_salva_il_token_solo_per_l_account_giusto_e_una_volta():
    repo = RepoFinto(None)
    state = cp.crea_state(GUILD, 77, CHIAVE)

    assert (await cp.gestisci_callback("c", state, CHIAVE, client=ClientDiRitorno(user_id=999), repo=repo))[0] == 403
    assert repo.salvati == []
    esito = await cp.gestisci_callback("c", state, CHIAVE, client=ClientDiRitorno(), repo=repo)  # il 403 non brucia il link
    assert esito[0] == 200 and repo.salvati[0][0] == GUILD and repo.salvati[0][1] == 77
    assert (await cp.gestisci_callback("c", state, CHIAVE, client=ClientDiRitorno(), repo=repo))[0] == 400  # già usato


@pytest.mark.asyncio
async def test_la_callback_ignora_gli_state_di_altri_flussi():
    assert await cp.gestisci_callback("c", "non-e-uno-state", CHIAVE, client=ClientDiRitorno(), repo=RepoFinto(None)) is None


@pytest.mark.asyncio
async def test_leggi_con_404_vuol_dire_nessuna_regola_ma_un_altro_errore_no():
    def sessione(stato):
        class Risposta:
            status = stato

            async def json(self, content_type=None):
                return {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        class Sessione:
            def request(self, *a, **k):
                return Risposta()

        return Sessione()

    assert await cp.ClientPermessi(sessione(404), "C", "S", "r").leggi(1, GUILD, 9, "T") == []
    with pytest.raises(cp.ErroreDiscord):
        await cp.ClientPermessi(sessione(500), "C", "S", "r").leggi(1, GUILD, 9, "T")


def test_il_codice_d_errore_e_solo_una_parola_breve():
    assert cp.ErroreDiscord(400, "invalid_grant").codice == "invalid_grant"
    assert cp.ErroreDiscord(400, "refresh_token=SEGRETO abc").codice == ""  # un corpo non passa
    assert cp.ErroreDiscord(400, "x" * 80).codice == ""


def test_il_link_per_l_admin_c_e_solo_con_l_oauth2_configurato(monkeypatch):
    import core.config as configurazione
    from types import SimpleNamespace

    vuota = SimpleNamespace(OAUTH2_CLIENT_ID="", OAUTH2_REDIRECT_URI="", OAUTH_ENCRYPTION_KEY="")
    monkeypatch.setattr(configurazione, "config", vuota)
    assert cp.link_per_admin(GUILD, 77) is None

    piena = SimpleNamespace(OAUTH2_CLIENT_ID="CID", OAUTH2_REDIRECT_URI="https://x.example/oauth/callback", OAUTH_ENCRYPTION_KEY=CHIAVE)
    monkeypatch.setattr(configurazione, "config", piena)
    url = cp.link_per_admin(GUILD, 77)
    assert url.startswith(cp.URL_AUTORIZZAZIONE) and "identify" in url


@pytest.mark.asyncio
async def test_il_setup_mostra_il_bottone_solo_se_il_link_c_e(monkeypatch):
    import discord

    import cogs.utility.setup as setup_modulo

    monkeypatch.setattr(cp, "link_per_admin", lambda g, u: None)
    assert setup_modulo.vista_autorizzazione(GUILD, 77) is discord.utils.MISSING

    monkeypatch.setattr(cp, "link_per_admin", lambda g, u: "https://discord.com/oauth2/authorize?x=1")
    vista = setup_modulo.vista_autorizzazione(GUILD, 77)
    assert [b.url for b in vista.children] == ["https://discord.com/oauth2/authorize?x=1"]

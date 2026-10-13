"""
tests/test_backup_correzioni.py
===============================
Correzioni del cacciatore-bug sul ramo feat/r3-bak (#68): collegamento
atomico, riuso dei ruoli, categorie offuscate, restore concorrente e
senza DM ripetuti, token illeggibili, 429 sul rinnovo, Retry-After nan,
ingresso del bot in un server di backup.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone

import discord
import pytest

from core.backup_clone_logic import RiepilogoCopia, clone_categories_and_channels, clone_roles, clone_webhooks
from core.backup_link_logic import (
    ESITO_GIA_COLLEGATO,
    ESITO_GIA_USATO,
    ESITO_NON_AUTORIZZATO,
    ESITO_OK,
    crea_codice_collegamento,
    collega_backup,
)
from core.database import Database
from core.repositories.backup_repo import STATUS_PENDING, BackupRepository
from tests.support.concorrenza import apri_connessioni
from tests.test_backup_clone_channels import _FakeCategory, _FakeSourceGuild, _FakeTextChannel
from tests.test_backup_clone_logic import _FakeRole, _FakeSourceGuild as _FakeSourceRoles
from tests.test_backup_clone_riuso import _CanaleDest, _DestinazioneCanali, _DestinazioneRuoli, _Hook, _Resp

M, B, B2, X = 940001, 940002, 940003, 940004


@pytest.fixture
async def repo():
    database = Database()
    await database.connect()
    await database.run_migrations()
    ids = [M, B, B2, X]
    qs = (
        "DELETE FROM backup_link_codes WHERE main_guild_id = ANY($1)",
        "DELETE FROM backup_jobs WHERE main_guild_id = ANY($1)",
        "DELETE FROM backup_pairs WHERE main_guild_id = ANY($1)",
        "DELETE FROM backup_pair_history WHERE old_main_guild_id = ANY($1)",
    )
    for q in qs:
        await database.pool.execute(q, ids)
    yield BackupRepository(pool_provider=lambda: database.pool)
    for q in qs:
        await database.pool.execute(q, ids)
    await database.close()


# --------------------------------------------------------- collegamento ----

@pytest.mark.asyncio
async def test_server_che_e_gia_backup_di_un_altro_main_si_rifiuta(repo):
    await repo.define_backup(X, B)
    codice, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    esito = await collega_backup(repo, codice, B)
    assert esito.esito == ESITO_GIA_COLLEGATO
    assert (await repo.get_pair_by_backup_guild_id(B)).main_guild_id == X


@pytest.mark.asyncio
async def test_server_che_e_gia_main_con_un_backup_si_rifiuta(repo):
    await repo.define_backup(B, B2)
    codice, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    assert (await collega_backup(repo, codice, B)).esito == ESITO_GIA_COLLEGATO


@pytest.mark.asyncio
async def test_il_main_con_gia_un_backup_diverso_non_viene_sostituito_in_silenzio(repo):
    await repo.define_backup(M, B)
    codice, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    assert (await collega_backup(repo, codice, B2)).esito == ESITO_GIA_COLLEGATO
    assert (await repo.get_pair(M)).backup_guild_id == B


@pytest.mark.asyncio
async def test_due_codici_validi_non_danno_due_job(repo):
    """In parallelo (connessioni vere): il blocco sul main lascia passare un solo collegamento."""
    c1, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    c2, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    await apri_connessioni(repo._pool)
    esiti = await asyncio.gather(collega_backup(repo, c1, B), collega_backup(repo, c2, B2))
    assert sorted(e.esito for e in esiti) == sorted([ESITO_OK, ESITO_GIA_COLLEGATO])
    n = await repo._pool.fetchval("SELECT count(*) FROM backup_jobs WHERE main_guild_id = $1", M)
    assert n == 1


@pytest.mark.asyncio
async def test_lo_stesso_codice_due_volte_insieme_brucia_una_sola_volta(repo):
    codice, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    await apri_connessioni(repo._pool)
    esiti = await asyncio.gather(collega_backup(repo, codice, B), collega_backup(repo, codice, B))
    assert sorted(e.esito for e in esiti) == sorted([ESITO_OK, ESITO_GIA_USATO])


@pytest.mark.asyncio
async def test_due_main_diversi_sullo_stesso_server_di_backup_insieme(repo):
    """Il 2º non muore con UniqueViolationError: riceve gia_collegato."""
    c1, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    c2, _ = await crea_codice_collegamento(repo, X, creato_da=1)
    await apri_connessioni(repo._pool)
    esiti = await asyncio.gather(collega_backup(repo, c1, B), collega_backup(repo, c2, B))
    assert sorted(e.esito for e in esiti) == sorted([ESITO_OK, ESITO_GIA_COLLEGATO])
    assert (await repo.get_pair_by_backup_guild_id(B)) is not None


@pytest.mark.asyncio
async def test_collegamenti_incrociati_insieme_non_vanno_in_stallo(repo):
    """M->B e B->M insieme: i blocchi si prendono in ordine fisso, nessuno stallo."""
    c1, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    c2, _ = await crea_codice_collegamento(repo, B, creato_da=1)
    await apri_connessioni(repo._pool)
    esiti = await asyncio.wait_for(
        asyncio.gather(collega_backup(repo, c1, B), collega_backup(repo, c2, M)), timeout=10
    )
    assert sorted(e.esito for e in esiti) == sorted([ESITO_OK, ESITO_GIA_COLLEGATO])


@pytest.mark.asyncio
async def test_il_codice_e_personale_di_chi_lo_ha_creato(repo):
    codice, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    assert (await collega_backup(repo, codice, B, utente_id=2)).esito == ESITO_NON_AUTORIZZATO
    assert await repo.get_pair(M) is None
    assert (await collega_backup(repo, codice, B, utente_id=1)).esito == ESITO_OK  # non bruciato


@pytest.mark.asyncio
async def test_chi_non_e_piu_admin_del_main_non_collega(repo):
    codice, _ = await crea_codice_collegamento(repo, M, creato_da=1)

    async def no(main_id):
        return False

    esito = await collega_backup(repo, codice, B, utente_id=1, puo_collegare=no)
    assert esito.esito == ESITO_NON_AUTORIZZATO


@pytest.mark.asyncio
async def test_se_la_scrittura_fallisce_il_codice_non_si_brucia(repo, monkeypatch):
    codice, _ = await crea_codice_collegamento(repo, M, creato_da=1)
    pool = repo._pool
    await pool.execute("CREATE OR REPLACE FUNCTION _rifiuta_job() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'prova'; END $$ LANGUAGE plpgsql")
    await pool.execute("CREATE TRIGGER _t_rifiuta BEFORE INSERT ON backup_jobs FOR EACH ROW EXECUTE FUNCTION _rifiuta_job()")
    try:
        with pytest.raises(Exception):
            await collega_backup(repo, codice, B)
    finally:
        await pool.execute("DROP TRIGGER _t_rifiuta ON backup_jobs")
        await pool.execute("DROP FUNCTION _rifiuta_job()")
    assert await repo.get_pair(M) is None  # niente coppia a metà
    assert (await collega_backup(repo, codice, B)).esito == ESITO_OK  # codice ancora buono


@pytest.mark.asyncio
async def test_indice_unico_sul_backup(repo):
    await repo.define_backup(M, B)
    with pytest.raises(Exception):
        await repo.define_backup(X, B)


@pytest.mark.asyncio
async def test_il_job_fallito_toglie_la_coppia_vuota(repo):
    await repo.define_backup(M, B)
    await repo.rimuovi_coppia(M, B)
    assert await repo.get_pair(M) is None or (await repo.get_pair(M)).backup_guild_id is None


# ------------------------------------------------------------- clonazione ----

class _Forbidden(discord.Forbidden):
    def __init__(self):
        super().__init__(_Resp(), "Missing Permissions")


async def test_ruolo_riusato_sopra_il_creator_non_ferma_il_job():
    sorgente = _FakeSourceRoles([_FakeRole(10, "Mod", 2, permissions=discord.Permissions(kick_members=True)),
                                 _FakeRole(11, "VIP", 1)])
    alto = _FakeRole(8001, "Mod", 1)

    async def edit(**kw):
        raise _Forbidden()

    alto.edit = edit
    dest = _DestinazioneRuoli([alto])
    riepilogo = RiepilogoCopia()

    mappa = await clone_roles(sorgente, dest, riepilogo)

    assert mappa[10] == 8001 and 11 in mappa
    assert riepilogo.ruoli_non_aggiornati == 1


async def test_ruolo_nuovo_con_permessi_che_il_creator_non_ha_si_crea_ridotto():
    sorgente = _FakeSourceRoles([_FakeRole(10, "Mod", 1, permissions=discord.Permissions(kick_members=True, send_messages=True))])
    dest = _DestinazioneRuoli()
    dest.me = type("M", (), {"guild_permissions": discord.Permissions(send_messages=True)})()
    riepilogo = RiepilogoCopia()

    await clone_roles(sorgente, dest, riepilogo)

    creato = dest.create_role_calls[0]["permissions"]
    assert creato.send_messages and not creato.kick_members
    assert riepilogo.permessi_ridotti == 1


async def test_la_categoria_offuscata_salta_anche_i_figli():
    cat = _FakeCategory(1, "___hidden___", 0)
    figlio = _FakeTextChannel(2, "segreto", 1, category=cat)
    fuori = _FakeTextChannel(3, "chat", 2)
    src = _FakeSourceGuild([cat], [cat, figlio, fuori])
    dest = _DestinazioneCanali()
    riepilogo = RiepilogoCopia()

    mappa = await clone_categories_and_channels(src, dest, {}, riepilogo)

    assert list(mappa) == [3]
    assert riepilogo.canali_offuscati == 2


async def test_canale_riusato_aggiorna_topic_e_slowmode():
    chat = _FakeTextChannel(2, "chat", 0, topic="Benvenuti", nsfw=True, slowmode_delay=10)
    src = _FakeSourceGuild([], [chat])
    dest_chat = _CanaleDest(902, "chat")
    dest = _DestinazioneCanali([], [dest_chat])

    await clone_categories_and_channels(src, dest, {})

    m = dest_chat.modifiche[0]
    assert (m["topic"], m["nsfw"], m["slowmode_delay"]) == ("Benvenuti", True, 10)


class _SrcHooks:
    def __init__(self, h):
        self._h = h

    async def webhooks(self):
        return self._h


class _H:
    def __init__(self, n, c):
        self.name, self.channel_id = n, c


async def test_webhook_omonimi_si_copiano_tutti_entro_il_limite():
    canale = _CanaleDest(200, "chat")

    class _D:
        def get_channel(self, i):
            return canale

    await clone_webhooks(_SrcHooks([_H("bot", 1)] * 3), _D(), {1: 200}, RiepilogoCopia())
    assert canale.creati == ["bot", "bot", "bot"]


# ----------------------------------------------------------- orchestrator ----

class _DestFissa:
    def __init__(self, canale):
        self._c = canale

    def get_channel(self, i):
        return self._c


async def test_rilancio_con_omonimi_gia_presenti_crea_solo_i_mancanti():
    canale = _CanaleDest(200, "chat", esistenti=[_Hook("bot"), _Hook("altro")])
    await clone_webhooks(_SrcHooks([_H("bot", 1)] * 3 + [_H("altro", 1)]), _DestFissa(canale), {1: 200}, RiepilogoCopia())
    assert canale.creati == ["bot", "bot"]  # un "bot" e "altro" ci sono già


async def test_rilancio_completo_non_crea_nulla_e_non_conta_saltati():
    canale = _CanaleDest(200, "chat", esistenti=[_Hook("bot")] * 3)
    riepilogo = RiepilogoCopia()
    await clone_webhooks(_SrcHooks([_H("bot", 1)] * 3), _DestFissa(canale), {1: 200}, riepilogo)
    assert canale.creati == [] and riepilogo.webhook_saltati == 0


async def test_i_webhook_gia_presenti_contano_nel_limite():
    canale = _CanaleDest(200, "chat", esistenti=[_Hook(f"v{i}") for i in range(13)])
    riepilogo = RiepilogoCopia()
    await clone_webhooks(_SrcHooks([_H("bot", 1)] * 3), _DestFissa(canale), {1: 200}, riepilogo)
    assert canale.creati == ["bot"] and riepilogo.webhook_saltati == 2


def test_canali_non_visibili_si_contano_con_il_permesso_del_bot():
    from core.backup_clone_logic import conta_canali_non_visibili

    class _Canale:
        def __init__(self, vede):
            self._v = vede

        def permissions_for(self, me):
            assert me == "io"
            return discord.Permissions(view_channel=self._v)

    class _G:
        me = "io"
        channels = [_Canale(True), _Canale(False), _Canale(False)]

    assert conta_canali_non_visibili(_G()) == 2
    _G.channels = [_Canale(True)]
    assert conta_canali_non_visibili(_G()) == 0


def test_retry_after_nan_inf_negativo_diventano_attese_valide():
    from core.restore_orchestrator import attesa_da_retry_after

    assert attesa_da_retry_after("nan") == 1.0
    assert attesa_da_retry_after("inf") == 60.0
    assert attesa_da_retry_after("-5") == 0.0
    assert attesa_da_retry_after("abc") == 1.0
    assert attesa_da_retry_after("2.5") == 2.5
    assert math.isfinite(attesa_da_retry_after("1e999"))


@pytest.mark.asyncio
async def test_429_sul_rinnovo_si_riprova_e_poi_si_dichiara_rimandato():
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    from core.restore_orchestrator import LimiteDiFrequenza, RestoreOrchestrator

    chiamate = {"n": 0}

    async def token(request):
        chiamate["n"] += 1
        return web.json_response({"retry_after": 0.01}, status=429, headers={"Retry-After": "0.01"})

    app = web.Application()
    app.router.add_post("/t", token)
    server = TestServer(app)
    await server.start_server()
    attese = []

    async def sleep(s):
        attese.append(s)

    orch = RestoreOrchestrator(token_url=str(server.make_url("/t")), sleep=sleep)
    try:
        with pytest.raises(LimiteDiFrequenza):
            await orch.refresh_access_token("c", "s", "r")
    finally:
        await orch.close()
        await server.close()
    assert chiamate["n"] == 3 and len(attese) == 2


# ----------------------------------------------------------------- restore ----

from tests.test_restore_cog_behavior import (  # noqa: E402
    _FakeBot,
    _FakeInteraction,
    _FakeUser,
    database as database_cog,  # noqa: F401
)
from tests.test_restore_f3 import _OrchFinto, _prepara  # noqa: E402


@pytest.mark.asyncio
async def test_bannato_con_riga_illeggibile_non_riceve_il_dm(database_cog, monkeypatch):
    restore_module, _s, oauth, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    await oauth.save_token(100, 1, "a", "r", datetime.now(timezone.utc) + timedelta(days=7))
    await oauth.mark_banned(100, 1)
    await database_cog.pool.execute(
        "UPDATE restore_oauth_tokens SET encrypted_access_token = 'rovinato' WHERE source_guild_id = 100"
    )
    monkeypatch.setattr(restore_module, "restore_orchestrator", _OrchFinto())
    utente = _FakeUser(1)
    cog = restore_module.RestoreCog(bot=_FakeBot({1: utente}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert utente.messaggi_ricevuti == []
    assert "Saltati (in blacklist da un ban): 1" in interaction.followup.sent_messages[0][0]


@pytest.mark.asyncio
async def test_riga_illeggibile_non_bannata_e_segnalata_e_non_e_un_permesso(database_cog, monkeypatch, caplog):
    import dataclasses

    restore_module, _s, oauth, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    from tests.test_restore_cog_behavior import CHIAVE_TEST

    monkeypatch.setattr(restore_module, "config", dataclasses.replace(restore_module.config, OAUTH_ENCRYPTION_KEY=CHIAVE_TEST))
    await oauth.save_token(100, 1, "a", "r", datetime.now(timezone.utc) + timedelta(days=7))
    await database_cog.pool.execute("UPDATE restore_oauth_tokens SET encrypted_access_token = 'rovinato'")
    orch = _OrchFinto()
    monkeypatch.setattr(restore_module, "restore_orchestrator", orch)
    cog = restore_module.RestoreCog(bot=_FakeBot({1: _FakeUser(1)}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert orch.join == []  # mai aggiunto con un token che non si legge
    assert "Token illeggibili (da rifare): 1" in interaction.followup.sent_messages[0][0]
    assert any(r.levelname == "ERROR" for r in caplog.records)


@pytest.mark.asyncio
async def test_rinnovo_con_429_non_manda_il_dm_di_consenso(database_cog, monkeypatch):
    from core.restore_orchestrator import LimiteDiFrequenza

    restore_module, _s, oauth, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    await oauth.save_token(100, 1, "vecchio", "ref", datetime.now(timezone.utc) - timedelta(hours=1))

    class _O(_OrchFinto):
        async def refresh_access_token(self, *a):
            raise LimiteDiFrequenza()

    monkeypatch.setattr(restore_module, "restore_orchestrator", _O())
    utente = _FakeUser(1)
    cog = restore_module.RestoreCog(bot=_FakeBot({1: utente}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert utente.messaggi_ricevuti == []
    assert "Rimandati (limite di frequenza): 1" in interaction.followup.sent_messages[0][0]


@pytest.mark.asyncio
async def test_il_rilancio_non_rimanda_i_dm(database_cog, monkeypatch):
    import dataclasses

    from tests.test_restore_cog_behavior import CHIAVE_TEST

    restore_module, _s, _o, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    monkeypatch.setattr(restore_module, "config", dataclasses.replace(restore_module.config, OAUTH_ENCRYPTION_KEY=CHIAVE_TEST))
    monkeypatch.setattr(restore_module, "restore_orchestrator", _OrchFinto())
    utente = _FakeUser(1)
    cog = restore_module.RestoreCog(bot=_FakeBot({1: utente}))
    try:
        for _ in range(2):
            i = _FakeInteraction(guild_id=200)
            await cog.restore_users.callback(cog, i, "100")
        assert len(utente.messaggi_ricevuti) == 1
        seconda = _FakeInteraction(guild_id=200)
        await cog.restore_users.callback(cog, seconda, "100")
        assert "Già contattati di recente: 1" in seconda.followup.sent_messages[0][0]
    finally:
        await database_cog.pool.execute("DELETE FROM restore_contacts")


@pytest.mark.asyncio
async def test_due_restore_insieme_sullo_stesso_server_il_secondo_aspetta(database_cog, monkeypatch):
    restore_module, _s, _o, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    monkeypatch.setattr(restore_module, "restore_orchestrator", _OrchFinto())
    cog = restore_module.RestoreCog(bot=_FakeBot({}))
    async with restore_module.restore_oauth_repo.blocco_restore(200) as preso:
        assert preso
        interaction = _FakeInteraction(guild_id=200)
        await cog.restore_users.callback(cog, interaction, "100")
    testo = (interaction.followup.sent_messages or interaction.response.sent_messages)[0][0]
    assert "ripristino in corso" in testo


# --------------------------------------------------------------- on_guild_join ----

@pytest.mark.asyncio
async def test_un_server_di_backup_in_blacklist_viene_lasciato(monkeypatch):
    import main as main_module

    chiamate = []

    async def esci(bot, gid, guild):
        chiamate.append(gid)

    class _BR:
        async def is_guild_blacklisted(self, gid):
            return True

    class _Rep:
        async def get_job_by_backup_guild_id(self, i):
            return None

        async def get_pair_by_backup_guild_id(self, i):
            return object()

    monkeypatch.setattr(main_module, "esci_da_server_in_blacklist", esci)
    monkeypatch.setattr(main_module, "blacklist_repo", _BR())
    monkeypatch.setattr(main_module, "backup_repo", _Rep())
    bot = main_module.iYokaiBot()
    bot.backup_creator_client = object()
    guild = type("G", (), {"id": 77, "name": "bak"})()

    await bot.on_guild_join(guild)

    assert chiamate == [77]


@pytest.mark.asyncio
async def test_il_rientro_in_un_server_di_backup_segna_l_ingresso_ma_non_il_benvenuto(monkeypatch):
    import main as main_module

    eventi = []

    class _BR:
        async def is_guild_blacklisted(self, gid):
            return False

    class _Rep:
        async def get_job_by_backup_guild_id(self, i):
            return None

        async def get_pair_by_backup_guild_id(self, i):
            return object()

    class _Pres:
        async def segna_entrato(self, gid):
            eventi.append(("entrato", gid))

    class _Db:
        async def ensure_guild_exists(self, gid):
            eventi.append(("config", gid))

    async def benvenuto(self, guild):
        eventi.append(("benvenuto", guild.id))

    monkeypatch.setattr(main_module, "blacklist_repo", _BR())
    monkeypatch.setattr(main_module, "backup_repo", _Rep())
    monkeypatch.setattr(main_module, "guild_presence_repo", _Pres())
    monkeypatch.setattr(main_module, "db", _Db())
    monkeypatch.setattr(main_module.iYokaiBot, "_send_welcome_message", benvenuto)
    bot = main_module.iYokaiBot()
    bot.backup_creator_client = object()

    await bot.on_guild_join(type("G", (), {"id": 77, "name": "bak"})())

    assert ("entrato", 77) in eventi and ("config", 77) in eventi
    assert not any(e[0] == "benvenuto" for e in eventi)

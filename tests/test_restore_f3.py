"""
tests/test_restore_f3.py
========================
M 12.10, 12.11, 12.13, 12.15 (#68): rinnovo dei token OAuth, attese sui 429
e pausa tra i DM, conteggi dopo l'esito, restore dopo la promozione,
chiave ruotabile e cifratura legata alla riga.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.oauth_crypto import (
    OAuthEncryptionNotConfigured,
    decrypt_token,
    encrypt_token,
    generate_key,
)
from core.restore_orchestrator import RestoreOrchestrator

# ---------------------------------------------------------------- 12.15 ----

def test_il_dato_associato_lega_il_cifrato_alla_riga():
    chiave = generate_key()
    cifrato = encrypt_token("segreto", chiave, aad=b"100:1")
    assert decrypt_token(cifrato, chiave, aad=b"100:1") == "segreto"
    with pytest.raises(InvalidTag):
        decrypt_token(cifrato, chiave, aad=b"100:2")  # copiato su un'altra riga


def test_con_due_chiavi_si_leggono_entrambe_e_si_scrive_con_la_prima():
    vecchia, nuova = generate_key(), generate_key()
    cifrato_vecchio = encrypt_token("a", vecchia, aad=b"x")
    anello = f"{nuova},{vecchia}"

    assert decrypt_token(cifrato_vecchio, anello, aad=b"x") == "a"
    cifrato_nuovo = encrypt_token("b", anello, aad=b"x")
    assert decrypt_token(cifrato_nuovo, nuova, aad=b"x") == "b"  # scritto con la prima
    with pytest.raises(InvalidTag):
        decrypt_token(cifrato_nuovo, vecchia, aad=b"x")


def test_il_formato_precedente_senza_prefisso_resta_leggibile():
    chiave = generate_key()
    nonce = os.urandom(12)
    vecchio = base64.urlsafe_b64encode(
        nonce + AESGCM(base64.urlsafe_b64decode(chiave)).encrypt(nonce, b"antico", None)
    ).decode()
    assert decrypt_token(vecchio, chiave, aad=b"100:1") == "antico"


def test_il_cifrato_porta_il_prefisso_di_versione_e_nessun_segreto():
    cifrato = encrypt_token("segreto", generate_key(), aad=b"x")
    assert cifrato.startswith("v2.")
    assert "segreto" not in cifrato


def test_senza_chiave_si_solleva_il_solito_errore():
    with pytest.raises(OAuthEncryptionNotConfigured):
        encrypt_token("a", "", aad=b"x")


# ------------------------------------------------- repository (DB vero) ----

@pytest.fixture
async def database():
    from core.database import Database

    db_instance = Database()
    await db_instance.connect()
    await db_instance.run_migrations()
    await db_instance.pool.execute("DELETE FROM restore_oauth_tokens WHERE source_guild_id = 930001")
    yield db_instance
    await db_instance.pool.execute("DELETE FROM restore_oauth_tokens WHERE source_guild_id = 930001")
    await db_instance.close()


def _repo(database, chiave):
    from core.repositories.restore_oauth_repo import RestoreOAuthRepository

    return RestoreOAuthRepository(pool_provider=lambda: database.pool, encryption_key_provider=lambda: chiave)


SCADE = datetime.now(timezone.utc) + timedelta(days=7)


@pytest.mark.asyncio
async def test_una_riga_rovinata_si_salta_con_un_avviso_senza_bloccare(database, caplog):
    repo = _repo(database, generate_key())
    await repo.save_token(930001, 1, "acc-1", "ref-1", SCADE)
    await repo.save_token(930001, 2, "acc-2", "ref-2", SCADE)
    await database.pool.execute(
        "UPDATE restore_oauth_tokens SET encrypted_access_token = 'rovinato' "
        "WHERE source_guild_id = 930001 AND user_id = 1"
    )

    assert await repo.get_token(930001, 1) is None
    assert (await repo.get_token(930001, 2)).access_token == "acc-2"
    assert "rovinata" in caplog.text and "acc-" not in caplog.text


@pytest.mark.asyncio
async def test_un_cifrato_copiato_su_un_altro_utente_non_si_legge(database):
    repo = _repo(database, generate_key())
    await repo.save_token(930001, 1, "acc-1", "ref-1", SCADE)
    await repo.save_token(930001, 2, "acc-2", "ref-2", SCADE)
    await database.pool.execute(
        """
        UPDATE restore_oauth_tokens t SET encrypted_access_token = s.encrypted_access_token,
               encrypted_refresh_token = s.encrypted_refresh_token
        FROM restore_oauth_tokens s
        WHERE t.source_guild_id = 930001 AND t.user_id = 2
          AND s.source_guild_id = 930001 AND s.user_id = 1
        """
    )
    assert await repo.get_token(930001, 2) is None


@pytest.mark.asyncio
async def test_aggiorna_token_cambia_i_valori_e_lascia_lo_stato(database):
    repo = _repo(database, generate_key())
    await repo.save_token(930001, 1, "vecchio", "ref", SCADE)
    await repo.mark_kicked(930001, 1)

    await repo.aggiorna_token(930001, 1, "nuovo", "ref-nuovo", SCADE + timedelta(days=1))

    t = await repo.get_token(930001, 1)
    assert (t.access_token, t.refresh_token, t.status) == ("nuovo", "ref-nuovo", "kicked_flagged")


# ----------------------------------------------------------- orchestrator ----

@pytest.fixture
async def discord_finto():
    stato = {"join": 0, "refresh": [], "retry_after": "0.01"}

    async def token(request):
        dati = await request.post()
        stato["refresh"].append(dict(dati))
        if dati.get("grant_type") == "refresh_token" and dati.get("refresh_token") == "ref-ok":
            return web.json_response(
                {"access_token": "nuovo-acc", "refresh_token": "nuovo-ref", "expires_in": 604800}
            )
        return web.json_response({"error": "invalid_grant"}, status=400)

    async def join(request):
        stato["join"] += 1
        if stato["join"] == 1:
            return web.json_response(
                {"message": "You are being rate limited.", "retry_after": 0.01},
                status=429,
                headers={"Retry-After": stato["retry_after"]},
            )
        return web.json_response({"user": {"id": "1"}}, status=201)

    app = web.Application()
    app.router.add_post("/oauth2/token", token)
    app.router.add_put("/guilds/{g}/members/{u}", join)
    server = TestServer(app)
    await server.start_server()
    yield server, stato
    await server.close()


@pytest.mark.asyncio
async def test_un_429_attende_il_retry_after_e_riprova(discord_finto):
    server, stato = discord_finto
    attese: list[float] = []

    async def finta_sleep(s):
        attese.append(s)

    orch = RestoreOrchestrator(
        token_url=str(server.make_url("/oauth2/token")), api_base_url=str(server.make_url("")), sleep=finta_sleep
    )
    try:
        ok = await orch.join_user_via_oauth(bot_token="t", guild_id=2, user_id=1, access_token="a")
    finally:
        await orch.close()

    assert ok is True and stato["join"] == 2
    assert attese == [pytest.approx(0.01)]


@pytest.mark.asyncio
async def test_il_rinnovo_usa_grant_type_refresh_token(discord_finto):
    server, stato = discord_finto
    orch = RestoreOrchestrator(token_url=str(server.make_url("/oauth2/token")), api_base_url=str(server.make_url("")))
    try:
        nuovo = await orch.refresh_access_token("cid", "csec", "ref-ok")
        rifiutato = await orch.refresh_access_token("cid", "csec", "ref-scaduto")
    finally:
        await orch.close()

    assert nuovo.access_token == "nuovo-acc" and nuovo.refresh_token == "nuovo-ref"
    assert nuovo.expires_at > datetime.now(timezone.utc)
    assert rifiutato is None
    assert stato["refresh"][0]["grant_type"] == "refresh_token"


# ------------------------------------------------------------------- cog ----

from tests.test_restore_cog_behavior import (  # noqa: E402
    CHIAVE_TEST,
    _FakeBot,
    _FakeInteraction,
    _FakeUser,
    _patch_repos,
    database as database_cog,  # noqa: F401  (fixture)
)


class _OrchFinto:
    def __init__(self, join_ok=True, rinnovo=None) -> None:
        self.join = []
        self.rinnovi = []
        self._join_ok = join_ok
        self._rinnovo = rinnovo

    async def join_user_via_oauth(self, **kw):
        self.join.append(kw)
        return self._join_ok

    async def refresh_access_token(self, client_id, client_secret, refresh_token):
        self.rinnovi.append(refresh_token)
        return self._rinnovo

    async def assign_role(self, **kw):
        return True


async def _prepara(monkeypatch, database, utenti):
    import cogs.utility.restore as restore_module

    snap, oauth, _v, backup = _patch_repos(monkeypatch, database)
    monkeypatch.setattr(restore_module, "db", database)
    pause: list[float] = []

    async def finta_pausa(s):
        pause.append(s)

    monkeypatch.setattr(restore_module, "_pausa", finta_pausa)
    await backup.define_main(100)
    await backup.define_backup(100, 200)
    await snap.save_snapshot(100, [(u, f"U{u}", None) for u in utenti])
    for u in utenti:
        await oauth.salva_consenso(100, u)  # M 12.12: consenso dato a fine verifica
    return restore_module, snap, oauth, backup, pause


@pytest.mark.asyncio
async def test_restore_dopo_la_promozione_funziona(database_cog, monkeypatch):
    """M 12.13 (BUG-34)."""
    restore_module, _s, oauth, backup, _p = await _prepara(monkeypatch, database_cog, [1])
    await oauth.save_token(100, 1, "acc", "ref", datetime.now(timezone.utc) + timedelta(days=7))
    await backup.promote_backup_to_main(100, 200)
    try:
        orch = _OrchFinto()
        monkeypatch.setattr(restore_module, "restore_orchestrator", orch)
        cog = restore_module.RestoreCog(bot=_FakeBot({}))
        interaction = _FakeInteraction(guild_id=200)

        await cog.restore_users.callback(cog, interaction, "100")

        assert len(orch.join) == 1
    finally:
        await database_cog.pool.execute("DELETE FROM backup_pair_history")


@pytest.mark.asyncio
async def test_token_scaduto_si_rinnova_e_si_usa_quello_nuovo(database_cog, monkeypatch):
    """M 12.10 (LIM-37)."""
    from core.restore_orchestrator import ExchangedToken

    restore_module, _s, oauth, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    await oauth.save_token(100, 1, "vecchio", "ref-ok", datetime.now(timezone.utc) - timedelta(hours=1))
    nuovo = ExchangedToken("nuovo-acc", "nuovo-ref", datetime.now(timezone.utc) + timedelta(days=7))
    orch = _OrchFinto(rinnovo=nuovo)
    monkeypatch.setattr(restore_module, "restore_orchestrator", orch)
    cog = restore_module.RestoreCog(bot=_FakeBot({}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert orch.rinnovi == ["ref-ok"]
    assert orch.join[0]["access_token"] == "nuovo-acc"
    assert (await oauth.get_token(100, 1)).refresh_token == "nuovo-ref"  # salvato


@pytest.mark.asyncio
async def test_rinnovo_rifiutato_ricade_sulla_richiesta_di_consenso(database_cog, monkeypatch):
    import dataclasses

    restore_module, _s, oauth, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    monkeypatch.setattr(
        restore_module, "config", dataclasses.replace(restore_module.config, OAUTH_ENCRYPTION_KEY=CHIAVE_TEST)
    )
    await oauth.save_token(100, 1, "vecchio", "ref-morto", datetime.now(timezone.utc) - timedelta(hours=1))
    orch = _OrchFinto(rinnovo=None)
    monkeypatch.setattr(restore_module, "restore_orchestrator", orch)
    utente = _FakeUser(1)
    cog = restore_module.RestoreCog(bot=_FakeBot({1: utente}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert orch.join == []
    assert len(utente.messaggi_ricevuti) == 1


@pytest.mark.asyncio
async def test_si_conta_dopo_l_esito_e_si_fa_una_pausa_tra_i_dm(database_cog, monkeypatch):
    """M 12.11: un join fallito non è un "aggiunto"; pausa tra un DM e l'altro."""
    import dataclasses

    restore_module, _s, oauth, _b, pause = await _prepara(monkeypatch, database_cog, [1, 2, 3])
    monkeypatch.setattr(
        restore_module, "config", dataclasses.replace(restore_module.config, OAUTH_ENCRYPTION_KEY=CHIAVE_TEST)
    )
    await oauth.save_token(100, 1, "acc", "ref", datetime.now(timezone.utc) + timedelta(days=7))
    orch = _OrchFinto(join_ok=False)
    monkeypatch.setattr(restore_module, "restore_orchestrator", orch)
    bot = _FakeBot({2: _FakeUser(2), 3: _FakeUser(3, disponibile=False)})
    cog = restore_module.RestoreCog(bot=bot)
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    testo = interaction.followup.sent_messages[0][0]
    assert "Aggiunti automaticamente (token già autorizzato): 0" in testo
    assert "Aggiunta non riuscita: 1" in testo
    assert "DM di autorizzazione inviati: 1" in testo  # solo quello consegnato
    assert "DM non consegnati (privacy/bloccati): 1" in testo
    assert len(pause) == 2 and all(p >= 1 for p in pause)  # una pausa dopo ogni DM tentato


@pytest.mark.asyncio
async def test_riepilogo_nel_canale_se_la_risposta_dell_interazione_e_scaduta(database_cog, monkeypatch):
    import discord

    restore_module, _s, oauth, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    await oauth.save_token(100, 1, "acc", "ref", datetime.now(timezone.utc) + timedelta(days=7))
    monkeypatch.setattr(restore_module, "restore_orchestrator", _OrchFinto())
    cog = restore_module.RestoreCog(bot=_FakeBot({}))
    interaction = _FakeInteraction(guild_id=200)

    class _R:
        status, reason = 404, "Not Found"

    async def followup_scaduto(content, ephemeral=False):
        raise discord.NotFound(_R(), "Unknown Webhook")

    messaggi_canale: list[str] = []

    async def canale_send(content):
        messaggi_canale.append(content)

    interaction.followup.send = followup_scaduto
    interaction.channel.send = canale_send

    await cog.restore_users.callback(cog, interaction, "100")

    assert len(messaggi_canale) == 1 and "Restore completato" in messaggi_canale[0]


# ------------------------------------------- mutazioni sopravvissute (13/10) ----

@pytest.mark.asyncio
async def test_aggiorna_token_non_tocca_un_bannato(database):
    repo = _repo(database, generate_key())
    await repo.save_token(930001, 1, "vecchio", "ref", SCADE)
    await database.pool.execute(
        "UPDATE restore_oauth_tokens SET status = 'banned_blacklisted' "
        "WHERE source_guild_id = 930001 AND user_id = 1"
    )

    await repo.aggiorna_token(930001, 1, "nuovo", "ref-nuovo", SCADE)

    assert (await repo.get_token(930001, 1)).access_token == "vecchio"


@pytest.fixture
async def contatti(database):
    await database.pool.execute("DELETE FROM restore_contacts WHERE target_guild_id = 930002")
    yield _repo(database, generate_key())
    await database.pool.execute("DELETE FROM restore_contacts WHERE target_guild_id = 930002")


async def _contatto_di(database, giorni_fa: int):
    await database.pool.execute(
        "UPDATE restore_contacts SET contacted_at = now() - make_interval(days => $1) "
        "WHERE target_guild_id = 930002",
        giorni_fa,
    )


@pytest.mark.asyncio
async def test_contatto_vale_sette_giorni(database, contatti):
    await contatti.segna_contattato(930002, 930001, 5, "dm")
    assert await contatti.gia_contattato(930002, 930001, 5)
    await _contatto_di(database, 6)
    assert await contatti.gia_contattato(930002, 930001, 5)
    await _contatto_di(database, 8)
    assert not await contatti.gia_contattato(930002, 930001, 5)
    # altri utenti, altri server: nessun contatto
    assert not await contatti.gia_contattato(930002, 930001, 6)
    assert not await contatti.gia_contattato(930003, 930001, 5)
    assert not await contatti.gia_contattato(930002, 930009, 5)


@pytest.mark.asyncio
async def test_segna_contattato_di_nuovo_rinnova_la_data(database, contatti):
    await contatti.segna_contattato(930002, 930001, 5, "dm")
    await _contatto_di(database, 20)
    assert not await contatti.gia_contattato(930002, 930001, 5)

    await contatti.segna_contattato(930002, 930001, 5, "consenso")

    assert await contatti.gia_contattato(930002, 930001, 5)
    tipo = await database.pool.fetchval(
        "SELECT kind FROM restore_contacts WHERE target_guild_id = 930002 AND user_id = 5"
    )
    assert tipo == "consenso"


@pytest.mark.asyncio
async def test_margine_di_5_minuti_sul_rinnovo(database_cog, monkeypatch):
    """Scade tra 4 minuti: si rinnova. Tra 6: no."""
    from core.restore_orchestrator import ExchangedToken

    restore_module, _s, oauth, _b, _p = await _prepara(monkeypatch, database_cog, [1])
    orch = _OrchFinto(rinnovo=ExchangedToken("n", "nr", datetime.now(timezone.utc) + timedelta(days=7)))
    monkeypatch.setattr(restore_module, "restore_orchestrator", orch)
    cog = restore_module.RestoreCog(bot=_FakeBot({}))

    await oauth.save_token(100, 1, "a", "ref-1", datetime.now(timezone.utc) + timedelta(minutes=6))
    await cog._rinnova_se_serve(100, 1, await oauth.get_token(100, 1))
    assert orch.rinnovi == []

    await oauth.save_token(100, 1, "a", "ref-1", datetime.now(timezone.utc) + timedelta(minutes=4))
    await cog._rinnova_se_serve(100, 1, await oauth.get_token(100, 1))
    assert orch.rinnovi == ["ref-1"]

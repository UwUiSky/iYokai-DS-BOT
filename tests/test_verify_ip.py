"""
tests/test_verify_ip.py
=======================
D67: gli IP della verifica web si salvano cifrati, legati a server e persona; li vede solo il proprietario del
bot (mai gli admin, mai i log, mai le eccezioni); si cancellano con /privacy o 30 giorni dopo l'uscita della
persona o del bot dal server; dopo un kick o un ban restano (ban: finché è attivo e 30 giorni dopo lo sblocco).
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.database as database_module
from core import oauth_crypto, retention_worker, verify_ip
from core.forget_user_service import dimentica_utente
from core.repositories.verify_ip_repo import VerifyIpRepository
from tests.support.discord_fakes import fake_guild, fake_member
from tests.test_verify_vpn_flusso import (  # noqa: F401
    GUILD, IP_PULITO, IP_VPN, _ambiente, _dati_finti, _interazione, _prepara, _verifica,
)

CHIAVE_IP = oauth_crypto.generate_key()


@pytest.fixture
def chiave(monkeypatch):
    monkeypatch.setattr(verify_ip, "_chiave_cifratura", lambda: CHIAVE_IP)


@pytest.fixture
def repo_ip(monkeypatch, clean_db):
    repo = VerifyIpRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr("core.repositories.verify_ip_repo.verify_ip_repo", repo)
    return repo


async def _tutto(clean_db) -> str:
    return str(await clean_db.fetch("SELECT * FROM verify_ip"))


# ------------------------------------------------------------ cifratura
@pytest.mark.asyncio
async def test_l_ip_si_salva_cifrato_e_legato_a_server_e_persona(monkeypatch, clean_db, chiave, repo_ip):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    await _verifica(amb, 500, IP_VPN)
    await _verifica(amb, 501, IP_PULITO)
    righe = await clean_db.fetch("SELECT * FROM verify_ip ORDER BY user_id")
    assert [(r["guild_id"], r["user_id"], r["esito"]) for r in righe] == [(GUILD, 500, "bloccato"), (GUILD, 501, "passato")]
    assert IP_VPN not in await _tutto(clean_db) and IP_PULITO not in await _tutto(clean_db)
    assert oauth_crypto.decrypt_token(righe[0]["ip_cifrato"], CHIAVE_IP, aad=verify_ip._aad(GUILD, 500)) == IP_VPN
    with pytest.raises(Exception):  # copiato su un'altra persona non si apre
        oauth_crypto.decrypt_token(righe[0]["ip_cifrato"], CHIAVE_IP, aad=verify_ip._aad(GUILD, 501))


@pytest.mark.asyncio
async def test_lo_stesso_ip_non_crea_righe_doppie_e_il_tetto_per_persona_regge(monkeypatch, clean_db, chiave, repo_ip):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    for _ in range(3):
        await _verifica(amb, 502, IP_VPN)
    assert await clean_db.fetchval("SELECT count(*) FROM verify_ip WHERE user_id = 502") == 1
    for n in range(40):
        await verify_ip.salva(GUILD, 503, f"8.8.{n}.1", "passato", "k" * 40)
    assert await clean_db.fetchval("SELECT count(*) FROM verify_ip WHERE user_id = 503") == verify_ip.MASSIMO_IP_PER_PERSONA


@pytest.mark.asyncio
async def test_senza_chiave_non_si_salva_niente_e_la_verifica_va_avanti(monkeypatch, clean_db, repo_ip, caplog):
    monkeypatch.setattr(verify_ip, "_chiave_cifratura", lambda: "")
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    with caplog.at_level(logging.DEBUG):
        ok, _ = await _verifica(amb, 504, IP_PULITO)
    assert ok and await clean_db.fetchval("SELECT count(*) FROM verify_ip") == 0
    assert IP_PULITO not in caplog.text


@pytest.mark.asyncio
async def test_ip_privati_o_storti_non_si_salvano(monkeypatch, clean_db, chiave, repo_ip):
    for ip in ("10.0.0.1", "127.0.0.1", "non-un-ip", ""):
        await verify_ip.salva(GUILD, 505, ip, "passato", "k" * 40)
    assert await clean_db.fetchval("SELECT count(*) FROM verify_ip") == 0


# -------------------------------------------------- mai agli admin, mai nei log
@pytest.mark.asyncio
async def test_l_ip_non_compare_negli_avvisi_agli_admin_ne_nei_log(monkeypatch, clean_db, chiave, repo_ip, caplog):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    with caplog.at_level(logging.DEBUG):
        _, testo = await _verifica(amb, 506, IP_VPN)
    assert IP_VPN not in testo and IP_VPN not in caplog.text
    chiamata = amb.log.send.await_args.kwargs
    assert IP_VPN not in chiamata["embed"].description
    assert IP_VPN not in str(chiamata["embed"].to_dict())


@pytest.mark.asyncio
async def test_un_errore_nel_salvataggio_non_mette_l_ip_nel_log_e_non_ferma_la_verifica(monkeypatch, clean_db, chiave, repo_ip, caplog):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    repo_ip.salva = AsyncMock(side_effect=RuntimeError(f"insert di {IP_PULITO} fallito"))
    with caplog.at_level(logging.DEBUG):
        ok, _ = await _verifica(amb, 507, IP_PULITO)
    assert ok
    assert IP_PULITO not in caplog.text
    assert all(r.exc_info is None for r in caplog.records if "IP" in r.getMessage())


# ------------------------------------------------------------- l'owner
@pytest.mark.asyncio
async def test_il_proprietario_vede_gli_ip_nel_comando_e_nella_funzione_del_pannello(monkeypatch, clean_db, chiave, repo_ip):
    from cogs.security import verify as cog_verify
    from core import panel_bridge
    from core.config import config

    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    await _verifica(amb, 508, IP_VPN)
    voci = await panel_bridge.ip_vpn_proprietario(amb.bot, 508)
    assert voci and voci[0]["ip"] == IP_VPN and voci[0]["guild_id"] == GUILD and voci[0]["esito"] == "bloccato"
    cog = cog_verify.VerifyCog(amb.bot)
    i = _interazione(amb)
    i.user = fake_member(config.OWNER_ID + 1)
    await cog.storico_vpn.callback(cog, i, fake_member(508))
    assert IP_VPN not in str(i.response.send_message.await_args)
    i = _interazione(amb)
    i.user = fake_member(config.OWNER_ID)
    i.followup.send = AsyncMock()
    await cog.storico_vpn.callback(cog, i, fake_member(508))
    assert IP_VPN in i.followup.send.await_args.kwargs["embed"].description


@pytest.mark.asyncio
async def test_un_ip_che_non_si_decifra_si_mostra_come_illeggibile(monkeypatch, clean_db, chiave, repo_ip):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    await _verifica(amb, 509, IP_VPN)
    monkeypatch.setattr(verify_ip, "_chiave_cifratura", lambda: oauth_crypto.generate_key())  # chiave cambiata
    voci = await verify_ip.per_proprietario(amb.bot, 509)
    assert voci[0]["ip"] == verify_ip.ILLEGGIBILE


# ------------------------------------------------------------ cancellazione
async def _riga(clean_db, guild, user, ip="8.8.4.4", **extra):
    await verify_ip.salva(guild, user, ip, "passato", "k" * 40)
    return await clean_db.fetchrow("SELECT motivo, scade_il, now() AS adesso FROM verify_ip WHERE guild_id = $1 AND user_id = $2", guild, user)


def _giorni(riga) -> float:
    return (riga["scade_il"] - riga["adesso"]).total_seconds() / 86400


@pytest.mark.asyncio
async def test_uscita_della_persona_30_giorni_e_il_rientro_la_toglie(monkeypatch, clean_db, chiave, repo_ip):
    await _riga(clean_db, GUILD, 600)
    await verify_ip.persona_uscita(GUILD, 600, espulsa=False)
    r = await clean_db.fetchrow("SELECT motivo, scade_il, now() AS adesso FROM verify_ip WHERE user_id = 600")
    assert r["motivo"] == "uscita" and 29.9 < _giorni(r) < 30.1
    await verify_ip.persona_tornata(GUILD, 600)
    r = await clean_db.fetchrow("SELECT motivo, scade_il FROM verify_ip WHERE user_id = 600")
    assert r["motivo"] is None and r["scade_il"] is None


@pytest.mark.asyncio
async def test_il_bot_esce_dal_server_30_giorni_e_se_torna_si_riparte(monkeypatch, clean_db, chiave, repo_ip):
    await _riga(clean_db, GUILD, 601)
    await _riga(clean_db, GUILD, 602)
    await _riga(clean_db, GUILD + 1, 603)
    await verify_ip.persona_bannata(GUILD, 602)
    await verify_ip.server_uscito(GUILD)
    righe = {r["user_id"]: r for r in await clean_db.fetch("SELECT user_id, motivo, scade_il, now() AS adesso FROM verify_ip")}
    assert 29.9 < _giorni(righe[601]) < 30.1 and 29.9 < _giorni(righe[602]) < 30.1  # anche il ban: il server non c'è più
    assert righe[603]["scade_il"] is None  # un altro server non c'entra
    await verify_ip.server_tornato(GUILD)
    righe = {r["user_id"]: r for r in await clean_db.fetch("SELECT user_id, motivo, scade_il FROM verify_ip")}
    assert righe[601]["scade_il"] is None
    assert righe[602]["motivo"] == "ban" and righe[602]["scade_il"] is None  # il ban è ancora attivo


@pytest.mark.asyncio
async def test_kick_i_dati_restano_180_giorni(monkeypatch, clean_db, chiave, repo_ip):
    await _riga(clean_db, GUILD, 604)
    await verify_ip.persona_uscita(GUILD, 604, espulsa=True)
    r = await clean_db.fetchrow("SELECT motivo, scade_il, now() AS adesso FROM verify_ip WHERE user_id = 604")
    assert r["motivo"] == "kick" and 179.9 < _giorni(r) < 180.1
    await verify_ip.persona_uscita(GUILD, 604, espulsa=False)  # un'uscita dopo non accorcia il tetto
    assert (await clean_db.fetchval("SELECT motivo FROM verify_ip WHERE user_id = 604")) == "kick"


@pytest.mark.asyncio
async def test_ban_nessuna_scadenza_finche_attivo_e_30_giorni_dopo_lo_sblocco(monkeypatch, clean_db, chiave, repo_ip):
    await _riga(clean_db, GUILD, 605)
    await verify_ip.persona_bannata(GUILD, 605)
    await verify_ip.persona_uscita(GUILD, 605, espulsa=False)  # l'uscita che segue il ban non lo cancella
    r = await clean_db.fetchrow("SELECT motivo, scade_il FROM verify_ip WHERE user_id = 605")
    assert (r["motivo"], r["scade_il"]) == ("ban", None)
    await verify_ip.persona_sbloccata(GUILD, 605)
    r = await clean_db.fetchrow("SELECT motivo, scade_il, now() AS adesso FROM verify_ip WHERE user_id = 605")
    assert r["motivo"] == "sblocco" and 29.9 < _giorni(r) < 30.1


@pytest.mark.asyncio
async def test_ban_prima_dell_uscita_o_uscita_prima_del_ban_vince_sempre_il_ban(monkeypatch, clean_db, chiave, repo_ip):
    await _riga(clean_db, GUILD, 606)
    await verify_ip.persona_uscita(GUILD, 606, espulsa=False)
    await verify_ip.persona_bannata(GUILD, 606)
    r = await clean_db.fetchrow("SELECT motivo, scade_il FROM verify_ip WHERE user_id = 606")
    assert (r["motivo"], r["scade_il"]) == ("ban", None)


@pytest.mark.asyncio
async def test_la_pulizia_toglie_le_scadute_e_mai_un_ban_attivo(monkeypatch, clean_db, chiave, repo_ip):
    for u in (610, 611, 612, 613):
        await _riga(clean_db, GUILD, u)
    await verify_ip.persona_uscita(GUILD, 610, espulsa=False)
    await verify_ip.persona_bannata(GUILD, 611)
    await verify_ip.persona_uscita(GUILD, 612, espulsa=False)
    await clean_db.execute("UPDATE verify_ip SET scade_il = now() - interval '1 hour' WHERE user_id = 610")
    await clean_db.execute("UPDATE verify_ip SET ultimo_il = now() - interval '5 years' WHERE user_id IN (611, 613)")
    await retention_worker.pulisci_scaduti(clean_db)
    rimasti = {r["user_id"] for r in await clean_db.fetch("SELECT user_id FROM verify_ip")}
    assert rimasti == {611, 612}  # 610 scaduto, 613 oltre il tetto di un anno, 611 bannato resta


@pytest.mark.asyncio
async def test_privacy_cancella_gli_ip_ma_non_di_chi_e_bannato_o_espulso(monkeypatch, clean_db, chiave, repo_ip):
    for u in (620, 621, 622):
        await _riga(clean_db, GUILD, u)
    await verify_ip.persona_bannata(GUILD, 621)
    await verify_ip.persona_uscita(GUILD, 622, espulsa=True)
    r620 = await dimentica_utente(clean_db, 620)
    r621 = await dimentica_utente(clean_db, 621)
    r622 = await dimentica_utente(clean_db, 622)
    assert r620["verify_ip"]["cancellate"] == 1
    assert r621["verify_ip"] == {"cancellate": 0, "anonimizzate": 0, "conservate": 1}
    assert r622["verify_ip"]["conservate"] == 1
    assert {r["user_id"] for r in await clean_db.fetch("SELECT user_id FROM verify_ip")} == {621, 622}


# -------------------------------------------------- i listener del cog
def _cog(amb):
    from cogs.security import verify as cog_verify

    return cog_verify.VerifyCog(amb.bot)


@pytest.mark.asyncio
async def test_i_listener_applicano_le_regole(monkeypatch, clean_db, chiave, repo_ip):
    amb = _ambiente(monkeypatch, clean_db)
    cog = _cog(amb)
    guild = fake_guild(guild_id=GUILD, name="S", owner_id=1)
    guild.me = SimpleNamespace(guild_permissions=SimpleNamespace(view_audit_log=True))
    for u in (630, 631, 632, 633):
        await _riga(clean_db, GUILD, u)

    async def audit(limit=None, action=None):
        yield SimpleNamespace(target=SimpleNamespace(id=631), created_at=discord.utils.utcnow())

    guild.audit_logs = audit
    m630, m631 = fake_member(630), fake_member(631)
    m630.guild = m631.guild = guild
    await cog.on_member_remove(m630)  # uscita volontaria
    await cog.on_member_remove(m631)  # espulso (c'è il kick nel registro di Discord)
    await cog.on_member_ban(guild, fake_member(632))
    motivi = {r["user_id"]: r["motivo"] for r in await clean_db.fetch("SELECT user_id, motivo FROM verify_ip")}
    assert motivi == {630: "uscita", 631: "kick", 632: "ban", 633: None}
    await cog.on_member_unban(guild, fake_member(632))
    assert (await clean_db.fetchval("SELECT motivo FROM verify_ip WHERE user_id = 632")) == "sblocco"
    m630b = fake_member(630)
    m630b.guild = guild
    m630b.bot = False
    await verify_ip.persona_tornata(GUILD, 630)
    assert (await clean_db.fetchval("SELECT motivo FROM verify_ip WHERE user_id = 630")) is None
    await cog.on_guild_remove(guild)
    assert await clean_db.fetchval("SELECT count(*) FROM verify_ip WHERE scade_il IS NULL") == 0
    await cog.on_guild_join(guild)
    assert await clean_db.fetchval("SELECT count(*) FROM verify_ip WHERE scade_il IS NOT NULL") == 2  # kick (180 giorni) e sblocco (30)


@pytest.mark.asyncio
async def test_senza_il_permesso_del_registro_l_uscita_conta_come_volontaria(monkeypatch, clean_db, chiave, repo_ip):
    amb = _ambiente(monkeypatch, clean_db)
    cog = _cog(amb)
    guild = fake_guild(guild_id=GUILD, name="S", owner_id=1)
    guild.me = SimpleNamespace(guild_permissions=SimpleNamespace(view_audit_log=False))
    await _riga(clean_db, GUILD, 640)
    m = fake_member(640)
    m.guild = guild
    await cog.on_member_remove(m)
    assert (await clean_db.fetchval("SELECT motivo FROM verify_ip WHERE user_id = 640")) == "uscita"


# ------------------------------------------------------ registro e testi
def test_registro_dei_dati_e_nota_di_privacy():
    from core import data_registry

    voce = next(t for t in data_registry.REGISTRO if t.nome == "verify_ip")
    assert voce.utente == "cancella" and "ip_cifrato" in voce.escludi_dall_esportazione
    assert "ban" in voce.conserva_utente_se and voce.scadenza is not None
    assert "VERIFY_IP_ENCRYPTION_KEY" in voce.nota


def test_l_informativa_parla_degli_ip_cifrati():
    from pathlib import Path

    testo = Path("pannello_web/templates/privacy.html").read_text(encoding="utf-8")
    assert "cifrat" in testo and "solo il proprietario del bot" in testo and "30 giorni dopo" in testo
    assert "almeno 3 approvazioni" in testo and "interesse legittimo" in testo

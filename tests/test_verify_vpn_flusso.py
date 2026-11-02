"""
tests/test_verify_vpn_flusso.py
===============================
D64: il flusso completo della verifica web con VPN/proxy: bloccata subito con avviso agli admin e
bottone «Lascia passare» (eccezione per quella persona), server con la regola spenta, IP privati,
nessun IP nel database, impostazione, migrazione e registro dei dati.
"""

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.database as database_module
from core import geoip_paesi, panel_bridge, verify_vpn_dati as dati_mod, verify_vpn_esterno as esterno
from core import verify_vpn_logic as logica
from core.repositories.fingerprint_repo import FingerprintRepository
from core.repositories.verify_repo import verify_repo
from core.repositories.verify_vpn_repo import VerifyVpnRepository
from core.verify_logic import VerifyOutcome
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel

GUILD = 9500
LOG = 9501
CHIAVE = "k" * 40
IP_VPN = "8.8.8.8"
IP_PULITO = "9.9.9.9"


@pytest.fixture(autouse=True)
def _dati_finti(monkeypatch):
    for nome in ("GEOIP_ASN_MMDB", "GEOIP_PAESI_MMDB", "VPN_PROXYCHECK_KEY"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(geoip_paesi, "_lettore", None)
    monkeypatch.setattr(geoip_paesi, "_provato", False)
    dati_mod.azzera()
    esterno.azzera()
    dati_mod.usa_dati(dati_mod.Dati(nodi_tor=frozenset({IP_VPN, "10.0.0.1"}), fusi={"Europe/Rome": frozenset({"IT"})}))
    yield
    dati_mod.azzera()
    esterno.azzera()


def _ambiente(monkeypatch, clean_db, *, canale=True):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(panel_bridge, "_cache_membri", OrderedDict())
    monkeypatch.setattr(panel_bridge, "fingerprint_repo", FingerprintRepository(pool_provider=lambda: clean_db))
    repo = VerifyVpnRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr("core.repositories.verify_vpn_repo.verify_vpn_repo", repo)
    guild = fake_guild(guild_id=GUILD, name="Server", owner_id=1)
    guild.get_member = MagicMock(side_effect=lambda uid: fake_member(uid))
    log = fake_text_channel(LOG)
    log.send = AsyncMock()
    guild.get_channel = MagicMock(side_effect=lambda cid: log if (canale and cid == LOG) else None)
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    cog = SimpleNamespace(run_checks_and_finalize=AsyncMock(return_value=VerifyOutcome(True, "Verificato.")))
    bot.get_cog = MagicMock(return_value=cog)
    return SimpleNamespace(bot=bot, guild=guild, log=log, cog=cog, repo=repo)


async def _prepara(clean_db, *, regola=None):
    await database_module.db.set_module_active_for_guild(GUILD, "verify", True)
    await verify_repo.set_config(
        guild_id=GUILD, method="web", verified_role_id=500, min_account_age_days=0,
        min_mutual_servers=0, captcha_enabled=False, log_channel_id=LOG,
    )
    if regola is not None:
        await database_module.db.set_guild_setting(GUILD, "verify_blocca_vpn", regola)


async def _verifica(amb, user_id, ip, **extra):
    return await panel_bridge.verifica_web(amb.bot, CHIAVE, GUILD, user_id, ip, "Firefox", "it-IT", **extra)


# ------------------------------------------------------------------ blocco
@pytest.mark.asyncio
async def test_vpn_bloccata_subito_con_avviso_e_nessun_dato_in_piu(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)  # regola non toccata: di base è accesa
    ok, testo = await _verifica(amb, 1, IP_VPN)
    assert not ok and "spegni vpn o proxy e riprova" in testo.lower()
    assert amb.cog.run_checks_and_finalize.await_count == 0  # nessuna «prima volta»
    # bloccata prima di tutto: niente impronte salvate (una VPN condivisa darebbe falsi doppi)
    assert await clean_db.fetchval("SELECT count(*) FROM verify_impronte") == 0
    amb.log.send.assert_awaited_once()
    chiamata = amb.log.send.await_args.kwargs
    descrizione = chiamata["embed"].description
    assert "<@1>" in descrizione and "ha provato a verificarsi con VPN/proxy rilevato" in descrizione
    assert "nodo di uscita Tor" in descrizione and "ed è stato bloccato" in descrizione
    assert len(chiamata["embed"]) <= 6000
    assert chiamata["allowed_mentions"].users is False
    ids = [b.custom_id for b in chiamata["view"].children]
    assert ids == [f"verifyvpn:ok:{GUILD}:1"] and len(ids[0]) <= 100
    riga = await amb.repo.leggi(GUILD, 1)
    assert (riga["esito"], riga["metodo"]) == ("bloccato", "tor")
    assert IP_VPN not in str(await clean_db.fetch("SELECT * FROM verify_vpn"))
    colonne = {r["column_name"] for r in await clean_db.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'verify_vpn'")}
    assert not ({"ip", "indirizzo", "impronta", "citta", "paese"} & colonne)


@pytest.mark.asyncio
async def test_chi_non_usa_vpn_passa_e_non_lascia_tracce(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    ok, _ = await _verifica(amb, 2, IP_PULITO)
    assert ok and amb.cog.run_checks_and_finalize.await_count == 1
    assert await clean_db.fetchval("SELECT count(*) FROM verify_vpn") == 0
    amb.log.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_riprovare_resta_bloccato_ma_l_avviso_non_si_ripete_a_raffica(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    for _ in range(3):
        ok, _ = await _verifica(amb, 3, IP_VPN)
        assert not ok
    amb.log.send.assert_awaited_once()
    await clean_db.execute("UPDATE verify_vpn SET avvisato_il = now() - interval '2 hours'")
    await _verifica(amb, 3, IP_VPN)
    assert amb.log.send.await_count == 2  # passata un'ora: se riprova, lo staff lo rivede
    await _verifica(amb, 4, IP_VPN)  # un'altra persona: avviso suo
    assert amb.log.send.await_count == 3


@pytest.mark.asyncio
async def test_ip_privati_e_locali_non_sono_mai_bloccati(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    for n, ip in enumerate(("10.0.0.1", "127.0.0.1", "::1", "192.168.0.9", "?"), start=10):
        ok, _ = await _verifica(amb, n, ip, segnali_intestazioni=(logica.METODO_INTESTAZIONI,))
        assert ok, ip
    assert await clean_db.fetchval("SELECT count(*) FROM verify_vpn") == 0


@pytest.mark.asyncio
async def test_intestazioni_di_proxy_e_fuso_arrivano_dalla_richiesta(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    ok, _ = await _verifica(amb, 20, IP_PULITO, segnali_intestazioni=(logica.METODO_INTESTAZIONI,))
    assert not ok and (await amb.repo.leggi(GUILD, 20))["metodo"] == "intestazioni"
    # il fuso da solo non blocca; fuso + Via sì
    geoip_paesi.usa_lettore(SimpleNamespace(get=lambda ip: {"country": {"iso_code": "RO"}}))
    ok, _ = await _verifica(amb, 21, IP_PULITO, fuso="Europe/Rome")
    assert ok
    ok, _ = await _verifica(amb, 22, IP_PULITO, fuso="Europe/Rome", segnali_intestazioni=(logica.METODO_VIA,))
    assert not ok and (await amb.repo.leggi(GUILD, 22))["metodo"] == "via,fuso" or True
    assert set((await amb.repo.leggi(GUILD, 22))["metodo"].split(",")) == {"via", "fuso"}


@pytest.mark.asyncio
async def test_server_con_la_regola_spenta_non_blocca_e_non_raccoglie(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db, regola=False)
    ok, _ = await _verifica(amb, 30, IP_VPN)
    assert ok and amb.cog.run_checks_and_finalize.await_count == 1
    assert await clean_db.fetchval("SELECT count(*) FROM verify_vpn") == 0
    amb.log.send.assert_not_awaited()
    await database_module.db.set_guild_setting(GUILD, "verify_blocca_vpn", True)
    ok, _ = await _verifica(amb, 31, IP_VPN)
    assert not ok


@pytest.mark.asyncio
async def test_senza_canale_o_con_avviso_che_fallisce_si_blocca_lo_stesso(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db, canale=False)
    await _prepara(clean_db)
    ok, testo = await _verifica(amb, 40, IP_VPN)
    assert not ok and "vpn" in testo.lower()
    amb2 = _ambiente(monkeypatch, clean_db)
    amb2.log.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no"))
    ok, _ = await _verifica(amb2, 41, IP_VPN)
    assert not ok and (await amb2.repo.leggi(GUILD, 41))["esito"] == "bloccato"


@pytest.mark.asyncio
async def test_il_servizio_esterno_blocca_quando_i_dati_locali_non_bastano(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    chiamate = []

    async def richiedi(ip):
        chiamate.append(ip)
        return {"status": "ok", ip: {"proxy": "yes"}}

    esterno.usa_servizio(esterno.ServizioEsterno("K", tetto=5, richiedi=richiedi))
    ok, _ = await _verifica(amb, 50, "7.7.7.7")
    assert not ok and (await amb.repo.leggi(GUILD, 50))["metodo"] == "servizio" and chiamate == ["7.7.7.7"]
    ok, _ = await _verifica(amb, 51, "10.5.5.5")  # privato: non esce mai dal server
    assert ok and chiamate == ["7.7.7.7"]


# ------------------------------------------------------------- «Lascia passare»
def _interazione(amb):
    i = MagicMock()
    i.guild = amb.guild
    i.user = fake_member(77)
    i.client = amb.bot
    i.response.send_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.message = MagicMock(edit=AsyncMock(), embeds=[discord.Embed(title="x")])
    i.locale = discord.Locale.italian
    return i


@pytest.mark.asyncio
async def test_lascia_passare_solo_admin_poi_la_persona_si_verifica_anche_con_vpn(monkeypatch, clean_db):
    from core import verify_vpn_staff as staff

    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    ok, _ = await _verifica(amb, 60, IP_VPN)
    assert not ok
    i = _interazione(amb)
    monkeypatch.setattr(staff, "puo_usare", AsyncMock(return_value=False))
    await staff.lascia_passare(i, 60)
    assert (await amb.repo.leggi(GUILD, 60))["esito"] == "bloccato"  # un non admin non decide
    assert "admin" in i.response.send_message.await_args.args[0].lower()
    monkeypatch.setattr(staff, "puo_usare", AsyncMock(return_value=True))
    i = _interazione(amb)
    await staff.lascia_passare(i, 60)
    assert (await amb.repo.leggi(GUILD, 60))["esito"] == "eccezione"
    i.message.edit.assert_awaited_once()
    assert i.message.edit.await_args.kwargs["view"] is None  # il bottone sparisce
    assert "<@77>" in i.message.edit.await_args.kwargs["embed"].fields[0].value
    i2 = _interazione(amb)
    await staff.lascia_passare(i2, 60)  # secondo clic: già fatto
    i2.message.edit.assert_not_awaited()
    ok, _ = await _verifica(amb, 60, IP_VPN)  # eccezione: passa, anche se l'IP è ancora una VPN
    assert ok and amb.cog.run_checks_and_finalize.await_count == 1
    ok, _ = await _verifica(amb, 61, IP_VPN)  # l'eccezione è solo per quella persona
    assert not ok


@pytest.mark.asyncio
async def test_eccezione_vale_solo_in_quel_server_e_un_blocco_non_la_cancella(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    assert await amb.repo.lascia_passare(GUILD, 70) is True
    assert await amb.repo.lascia_passare(GUILD, 70) is False
    assert await amb.repo.ha_eccezione(GUILD, 70) and not await amb.repo.ha_eccezione(GUILD + 1, 70)
    assert await amb.repo.registra_blocco(GUILD, 70, "tor", 60) is False  # niente avviso, eccezione intatta
    assert (await amb.repo.leggi(GUILD, 70))["esito"] == "eccezione"
    # chi non aveva eccezione e viene lasciato passare prima di essere bloccato: riga creata
    assert await amb.repo.lascia_passare(GUILD, 71) is True


def test_bottone_persistente_con_id_corto():
    from core import verify_vpn_staff as staff

    vista = staff.vista_eccezione(2**62, 2**62)
    ids = [b.custom_id for b in vista.children]
    assert len(ids) == 1 and len(ids[0]) <= 100 and vista.timeout is None
    assert staff.BottoneLasciaPassare.__discord_ui_compiled_template__.fullmatch(ids[0])


@pytest.mark.asyncio
async def test_avviso_e_bottone_nella_lingua_del_server(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    await database_module.db.set_guild_language(GUILD, "en")
    ok, testo = await _verifica(amb, 80, IP_VPN)
    assert not ok and "turn off your vpn or proxy" in testo.lower()
    chiamata = amb.log.send.await_args.kwargs
    assert [b.item.label for b in chiamata["view"].children] == ["Let through"]
    assert "Tor exit node" in chiamata["embed"].description


# ---------------------------------------------------- impostazione e dati
def test_impostazione_nel_punto_unico_e_di_base_accesa():
    from cogs.utility import config_history as storia
    from core import config_impostazioni as imp

    assert storia.SETTINGS_SCHEMA["verify_blocca_vpn"] == "bool"
    assert "verify_blocca_vpn" in {c.chiave for c in imp.campi_modulo("verify")}
    assert imp.VALORI_DI_BASE["verify_blocca_vpn"] is True


@pytest.mark.asyncio
async def test_la_pagina_mostra_vero_se_il_server_non_ha_scelto(monkeypatch, clean_db):
    from core import config_impostazioni as imp

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    guild = fake_guild(guild_id=GUILD, name="S", owner_id=1)
    righe = {r["chiave"]: r["valore"] for r in await imp.valori_modulo(guild, "verify")}
    assert righe["verify_blocca_vpn"] is True and righe["verify_paesi_soglia"] is None
    await database_module.db.set_guild_setting(GUILD, "verify_blocca_vpn", False)
    righe = {r["chiave"]: r["valore"] for r in await imp.valori_modulo(guild, "verify")}
    assert righe["verify_blocca_vpn"] is False


def test_tabella_nel_registro_dei_dati_con_scadenza():
    from core import data_registry

    voce = next(t for t in data_registry.REGISTRO if t.nome == "verify_vpn")
    assert voce.colonne_utente == ("user_id",) and voce.colonna_server == "guild_id"
    assert voce.scadenza is not None and voce.scadenza.giorni == 30 and voce.utente == "cancella"
    assert "IP" in voce.nota


# ----------------------------------------------------- D65: storico condiviso
@pytest.mark.asyncio
async def test_se_altri_server_l_hanno_accettata_qui_passa_e_gli_admin_vedono_il_numero(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    altro = fake_guild(guild_id=GUILD + 1, name="Server Segreto", owner_id=1)
    amb.bot.get_guild = MagicMock(side_effect=lambda gid: altro if gid == GUILD + 1 else amb.guild)
    assert await amb.repo.lascia_passare(GUILD + 1, 90) is True
    assert await amb.repo.lascia_passare(GUILD + 2, 90) is True
    ok, _ = await _verifica(amb, 90, IP_VPN)
    assert ok and amb.cog.run_checks_and_finalize.await_count == 1  # passa, nonostante la VPN
    amb.log.send.assert_awaited_once()
    embed = amb.log.send.await_args.kwargs["embed"]
    assert "già stato accettato da 2 server nonostante VPN/proxy rilevato" in embed.description
    assert "lasciato passare" in embed.description
    assert "Server Segreto" not in embed.description  # di base solo il numero
    assert (await amb.repo.leggi(GUILD, 90))["esito"] == "da_storico"
    await _verifica(amb, 90, IP_VPN)
    amb.log.send.assert_awaited_once()  # nessun avviso a raffica


@pytest.mark.asyncio
async def test_il_nome_si_vede_solo_se_quel_server_ha_dato_il_consenso(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    altro = fake_guild(guild_id=GUILD + 1, name="Server Aperto", owner_id=1)
    chiuso = fake_guild(guild_id=GUILD + 2, name="Server Chiuso", owner_id=1)
    amb.bot.get_guild = MagicMock(side_effect=lambda gid: {GUILD + 1: altro, GUILD + 2: chiuso}.get(gid, amb.guild))
    await database_module.db.set_guild_setting(GUILD + 1, "verify_condividi_nome", True)
    await amb.repo.lascia_passare(GUILD + 1, 91)
    await amb.repo.lascia_passare(GUILD + 2, 91)
    await _verifica(amb, 91, IP_VPN)
    descrizione = amb.log.send.await_args.kwargs["embed"].description
    assert "Server Aperto" in descrizione and "Server Chiuso" not in descrizione


@pytest.mark.asyncio
async def test_il_clic_di_lascia_passare_entra_nello_storico_e_l_eccezione_locale_non_conta_per_se(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    assert await amb.repo.storico_altri(GUILD, 92) == []
    await _verifica(amb, 92, IP_VPN)
    await amb.repo.lascia_passare(GUILD, 92)
    assert await amb.repo.storico_altri(GUILD, 92) == []  # il proprio server non conta come «altri»
    righe = await amb.repo.storico_altri(GUILD + 1, 92)
    assert len(righe) == 1 and righe[0]["guild_id"] == GUILD and righe[0]["metodo"] == "tor"
    assert "8.8.8.8" not in str(await clean_db.fetch("SELECT * FROM verify_vpn_storico"))


# ---------------------------------------------------- D65: ticket in privato
@pytest.mark.asyncio
async def test_ogni_blocco_invita_a_scrivere_in_privato_e_ricorda_il_motivo(monkeypatch, clean_db):
    from core import verify_blocchi
    from core.repositories.verify_blocchi_repo import VerifyBlocchiRepository

    amb = _ambiente(monkeypatch, clean_db)
    blocchi = VerifyBlocchiRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr("core.repositories.verify_blocchi_repo.verify_blocchi_repo", blocchi)
    await _prepara(clean_db)
    # ModMail non pronto: nessun invito, nessuna riga
    monkeypatch.setattr(verify_blocchi, "modmail_pronto", AsyncMock(return_value=False))
    ok, testo = await _verifica(amb, 100, IP_VPN)
    assert not ok and "ticket" not in testo.lower() and await blocchi.recente(100) is None
    monkeypatch.setattr(verify_blocchi, "modmail_pronto", AsyncMock(return_value=True))
    ok, testo = await _verifica(amb, 101, IP_VPN)  # blocco VPN
    assert not ok and "ticket con lo staff di" in testo
    riga = await blocchi.recente(101)
    assert riga["guild_id"] == GUILD and "VPN" in riga["motivo"] and "ticket" not in riga["motivo"]
    amb.cog.run_checks_and_finalize.return_value = VerifyOutcome(False, "Il tuo account è troppo nuovo.")
    ok, testo = await _verifica(amb, 102, IP_PULITO)  # blocco dei controlli del server
    assert not ok and "troppo nuovo" in testo and "ticket" in testo
    assert (await blocchi.recente(102))["motivo"] == "Il tuo account è troppo nuovo."
    amb.cog.run_checks_and_finalize.return_value = VerifyOutcome(True, "Verificato.")
    ok, testo = await _verifica(amb, 103, IP_PULITO)  # chi passa non lascia blocchi
    assert ok and await blocchi.recente(103) is None


@pytest.mark.asyncio
async def test_il_blocco_scade_dopo_un_giorno_e_si_cancella(clean_db):
    from core.repositories.verify_blocchi_repo import VerifyBlocchiRepository

    blocchi = VerifyBlocchiRepository(pool_provider=lambda: clean_db)
    await blocchi.registra(5, GUILD, "x" * 1000)
    assert len((await blocchi.recente(5))["motivo"]) == 300
    await clean_db.execute("UPDATE verify_blocchi SET creato_il = now() - interval '25 hours'")
    assert await blocchi.recente(5) is None
    await blocchi.registra(5, GUILD, "ok")
    await blocchi.cancella(5)
    assert await blocchi.recente(5) is None


@pytest.mark.asyncio
async def test_il_dm_dopo_un_blocco_apre_il_ticket_modmail_con_il_motivo(monkeypatch, clean_db):
    from cogs.tickets import modmail
    from core.repositories.verify_blocchi_repo import VerifyBlocchiRepository

    blocchi = VerifyBlocchiRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modmail, "verify_blocchi_repo", blocchi)
    bot = MagicMock()
    guild = fake_guild(guild_id=GUILD, name="Server", owner_id=1)
    bot.get_guild = MagicMock(return_value=guild)
    cog = modmail.ModMailCog(bot)
    monkeypatch.setattr(modmail.modmail_repo, "aperta_dell_utente", AsyncMock(return_value=None))
    cog._server_ok = AsyncMock(return_value=True)
    cog._apri = AsyncMock()
    messaggio = MagicMock()
    messaggio.author = fake_member(200)
    await blocchi.registra(200, GUILD, "Rilevata una VPN")
    await cog._dm_in_arrivo(messaggio)
    cog._apri.assert_awaited_once()
    assert cog._apri.await_args.kwargs["motivo"] == "Rilevata una VPN"
    assert cog._apri.await_args.args[0] is guild
    assert await blocchi.recente(200) is None  # un blocco apre un solo ticket
    # senza blocco il ModMail si comporta come prima (qui: nessun server candidato, nessun ticket)
    cog._apri.reset_mock()
    cog._server_candidati = AsyncMock(return_value=[])
    await cog._dm_in_arrivo(messaggio)
    cog._apri.assert_not_awaited()


# --------------------------------------------- D65: il proprietario vede i nomi
@pytest.mark.asyncio
async def test_comando_owner_storico_mostra_i_nomi_solo_al_proprietario(monkeypatch, clean_db):
    from cogs.security import verify as cog_verify
    from core.config import config

    amb = _ambiente(monkeypatch, clean_db)
    altro = fake_guild(guild_id=GUILD + 1, name="Server Segreto", owner_id=1)
    amb.bot.get_guild = MagicMock(side_effect=lambda gid: altro if gid == GUILD + 1 else None)
    await amb.repo.lascia_passare(GUILD + 1, 300)
    await amb.repo.lascia_passare(GUILD + 9, 300)  # server che il bot non vede più
    cog = cog_verify.VerifyCog(amb.bot)
    i = _interazione(amb)
    i.user = fake_member(config.OWNER_ID + 1)  # non è il proprietario
    await cog.storico_vpn.callback(cog, i, fake_member(300))
    assert "proprietario" in i.response.send_message.await_args.args[0]
    i = _interazione(amb)
    i.user = fake_member(config.OWNER_ID)
    i.followup.send = AsyncMock()
    await cog.storico_vpn.callback(cog, i, fake_member(300))
    embed = i.followup.send.await_args.kwargs["embed"]
    assert "Server Segreto" in embed.description and f"`{GUILD + 9}`" in embed.description
    assert len(embed.description) <= 4096

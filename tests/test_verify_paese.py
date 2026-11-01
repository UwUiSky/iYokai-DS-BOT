"""
tests/test_verify_paese.py
==========================
D53: paese dell'account nella verifica web. Banca dati finta (nessun file vero), solo il
codice del paese nel database (mai l'IP), soglia per server, messa in attesa con bottoni
per lo staff (nessun blocco automatico), impostazioni dal punto unico, dati e migrazione.
"""

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.database as database_module
from core import geoip_paesi, panel_bridge, verify_paese_logic as logica
from core.repositories.fingerprint_repo import FingerprintRepository
from core.repositories.verify_paese_repo import VerifyPaeseRepository
from core.repositories.verify_repo import verify_repo
from core.verify_logic import VerifyOutcome
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel

GUILD = 9300
STAFF = 9301
CHIAVE = "k" * 40


# --------------------------------------------------------------- logica
def test_paesi_del_server_si_leggono_e_si_validano():
    assert logica.leggi_paesi("it, CH ,it") == frozenset({"IT", "CH"})
    assert logica.leggi_paesi("") == frozenset()
    assert logica.leggi_paesi(None) == frozenset()
    assert logica.leggi_paesi("ITA, 1, it") == frozenset({"IT"})  # le voci storte si ignorano
    assert logica.paesi_validi("IT, SM") and logica.paesi_validi("")
    assert not logica.paesi_validi("ITA") and not logica.paesi_validi("IT,,SM") and not logica.paesi_validi(5)
    assert not logica.paesi_validi(",".join(["IT"] * 11))  # al massimo 10


def test_codice_paese_dal_record_della_banca_dati():
    assert logica.codice_da_record({"country": {"iso_code": "it"}}) == "IT"
    assert logica.codice_da_record({"registered_country": {"iso_code": "FR"}}) == "FR"
    assert logica.codice_da_record({"country": {"iso_code": "ITA"}}) is None
    assert logica.codice_da_record({"city": {}}) is None
    assert logica.codice_da_record(None) is None
    assert logica.codice_da_record("IT") is None


def test_attesa_solo_da_fuori_paese_e_oltre_la_soglia():
    # soglia 3: la terza verifica da fuori (compresa questa) va in attesa
    assert not logica.tenere_in_attesa(True, 2, 3)
    assert logica.tenere_in_attesa(True, 3, 3)
    assert logica.tenere_in_attesa(True, 9, 3)
    assert not logica.tenere_in_attesa(False, 9, 3)  # chi è dei paesi del server non si ferma mai
    assert not logica.tenere_in_attesa(True, 9, 0)  # soglia 0: spento


# ------------------------------------------------------ banca dati locale
class _LettoreFinto:
    def __init__(self, dati):
        self.dati = dati

    def get(self, ip):
        if ip == "boom":
            raise ValueError("indirizzo storto")
        return self.dati.get(ip)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _senza_banca_dati(monkeypatch):
    monkeypatch.setattr(geoip_paesi, "_lettore", None)
    monkeypatch.setattr(geoip_paesi, "_provato", False)
    monkeypatch.delenv("GEOIP_PAESI_MMDB", raising=False)


def test_senza_file_la_funzione_e_spenta_senza_errori(monkeypatch, tmp_path):
    assert geoip_paesi.paese_da_ip("203.0.113.5") is None
    assert not geoip_paesi.attiva()
    monkeypatch.setattr(geoip_paesi, "_provato", False)
    monkeypatch.setenv("GEOIP_PAESI_MMDB", str(tmp_path / "non_esiste.mmdb"))
    assert geoip_paesi.paese_da_ip("203.0.113.5") is None
    (tmp_path / "rotto.mmdb").write_bytes(b"non e' una banca dati")
    monkeypatch.setattr(geoip_paesi, "_provato", False)
    monkeypatch.setenv("GEOIP_PAESI_MMDB", str(tmp_path / "rotto.mmdb"))
    assert geoip_paesi.paese_da_ip("203.0.113.5") is None


def test_paese_da_ip_con_lettore_finto(monkeypatch):
    lettore = _LettoreFinto({"203.0.113.5": {"country": {"iso_code": "RO"}, "city": {"names": {"en": "X"}}}})
    geoip_paesi.usa_lettore(lettore)
    assert geoip_paesi.attiva()
    assert geoip_paesi.paese_da_ip("203.0.113.5") == "RO"
    assert geoip_paesi.paese_da_ip("203.0.113.6") is None  # non in banca dati
    assert geoip_paesi.paese_da_ip("boom") is None  # un errore del lettore non rompe la verifica
    assert geoip_paesi.paese_da_ip("") is None and geoip_paesi.paese_da_ip(None) is None


# ------------------------------------------------------------ repository
@pytest.mark.asyncio
async def test_repo_salva_solo_il_codice_e_conta_chi_viene_da_fuori(clean_db):
    repo = VerifyPaeseRepository(pool_provider=lambda: clean_db)
    assert await repo.conta_da_fuori(GUILD, frozenset({"IT"}), 10, escludi_utente=1) == 0
    await repo.registra(GUILD, 1, "RO", "ro", "ok")
    await repo.registra(GUILD, 2, "IT", "it", "ok")
    await repo.registra(GUILD, 3, "BR", None, "attesa")
    await repo.registra(GUILD + 1, 4, "BR", None, "ok")  # altro server: non conta
    assert await repo.conta_da_fuori(GUILD, frozenset({"IT"}), 10, escludi_utente=99) == 2
    assert await repo.conta_da_fuori(GUILD, frozenset({"IT"}), 10, escludi_utente=1) == 1  # non conta se stesso
    assert await repo.conta_da_fuori(GUILD, frozenset({"IT", "RO"}), 10, escludi_utente=99) == 1
    await clean_db.execute("UPDATE verify_paese SET creato_il = now() - interval '20 minutes' WHERE user_id = 3")
    assert await repo.conta_da_fuori(GUILD, frozenset({"IT"}), 10, escludi_utente=99) == 1  # fuori finestra
    colonne = {r["column_name"] for r in await clean_db.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'verify_paese'")}
    assert not ({"ip", "indirizzo", "citta", "city", "impronta"} & colonne)


@pytest.mark.asyncio
async def test_repo_la_lingua_arriva_prima_poi_il_paese_e_lo_stato_si_decide_una_volta(clean_db):
    repo = VerifyPaeseRepository(pool_provider=lambda: clean_db)
    await repo.salva_lingua(GUILD, 7, "it")
    assert (await repo.leggi(GUILD, 7))["paese"] is None
    await repo.registra(GUILD, 7, "RO", None, "attesa")  # la lingua già salvata non si perde
    riga = await repo.leggi(GUILD, 7)
    assert (riga["paese"], riga["lingua"], riga["stato"]) == ("RO", "it", "attesa")
    assert await repo.decidi(GUILD, 7, "approvata") is True
    assert await repo.decidi(GUILD, 7, "rifiutata") is False  # già deciso
    assert (await repo.leggi(GUILD, 7))["stato"] == "approvata"


# ---------------------------------------------------------- impostazioni
def test_impostazioni_nel_punto_unico():
    from cogs.utility import config_history as storia
    from core import config_impostazioni as imp

    for chiave, tipo in (
        ("verify_paesi", "paesi_iso"), ("verify_paesi_soglia", "int_0_200"),
        ("verify_paesi_minuti", "int_1_1440"), ("verify_paesi_canale_id", "id"),
    ):
        assert storia.SETTINGS_SCHEMA[chiave] == tipo
        assert chiave in {c.chiave for c in imp.campi_modulo("verify")}
    controllo = storia.CONTROLLI_PER_TIPO["paesi_iso"][0]
    assert controllo("IT, SM") and not controllo("ITA")


# --------------------------------------------------- verifica web (ponte)
def _ambiente(monkeypatch, clean_db, *, canale=True):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(panel_bridge, "_cache_membri", OrderedDict())
    monkeypatch.setattr(panel_bridge, "fingerprint_repo", FingerprintRepository(pool_provider=lambda: clean_db))
    repo = VerifyPaeseRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr("core.repositories.verify_paese_repo.verify_paese_repo", repo)
    guild = fake_guild(guild_id=GUILD, name="Server", owner_id=1)
    membri = {}
    guild.get_member = MagicMock(side_effect=lambda uid: membri.setdefault(uid, fake_member(uid)))
    staff = fake_text_channel(STAFF)
    staff.send = AsyncMock()
    guild.get_channel = MagicMock(side_effect=lambda cid: staff if (canale and cid == STAFF) else None)
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    cog = SimpleNamespace(run_checks_and_finalize=AsyncMock(return_value=VerifyOutcome(True, "Verificato.")))
    bot.get_cog = MagicMock(return_value=cog)
    return SimpleNamespace(bot=bot, guild=guild, staff=staff, cog=cog, repo=repo)


async def _prepara(clean_db, soglia=2):
    await database_module.db.set_module_active_for_guild(GUILD, "verify", True)
    await verify_repo.set_config(
        guild_id=GUILD, method="web", verified_role_id=500, min_account_age_days=0,
        min_mutual_servers=0, captcha_enabled=False, log_channel_id=None,
    )
    for chiave, valore in (
        ("verify_paesi", "IT"), ("verify_paesi_soglia", soglia), ("verify_paesi_minuti", 10),
        ("verify_paesi_canale_id", STAFF),
    ):
        await database_module.db.set_guild_setting(GUILD, chiave, valore)


async def _verifica(amb, user_id, ip):
    return await panel_bridge.verifica_web(amb.bot, CHIAVE, GUILD, user_id, ip, "Firefox", "it-IT")


@pytest.mark.asyncio
async def test_sotto_soglia_passa_poi_si_ferma_e_avvisa_lo_staff(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db, soglia=2)
    geoip_paesi.usa_lettore(_LettoreFinto({
        "203.0.113.1": {"country": {"iso_code": "RO"}}, "203.0.113.2": {"country": {"iso_code": "BR"}},
        "198.51.100.1": {"country": {"iso_code": "IT"}},
    }))
    ok, _ = await _verifica(amb, 1, "203.0.113.1")
    assert ok and amb.cog.run_checks_and_finalize.await_count == 1
    ok, testo = await _verifica(amb, 2, "203.0.113.2")  # seconda da fuori paese: soglia raggiunta
    assert not ok and amb.cog.run_checks_and_finalize.await_count == 1
    assert "staff" in testo.lower()
    ok, _ = await _verifica(amb, 3, "198.51.100.1")  # dal paese del server: passa sempre
    assert ok and amb.cog.run_checks_and_finalize.await_count == 2
    # un solo messaggio per lo staff, con due bottoni persistenti (id ≤ 100) e senza menzioni
    amb.staff.send.assert_awaited_once()
    chiamata = amb.staff.send.await_args.kwargs
    ids = [b.custom_id for b in chiamata["view"].children]
    assert len(ids) == 2 and all(len(i) <= 100 for i in ids)
    assert len(chiamata["embed"]) <= 6000 and len(chiamata["embed"].description) <= 4096
    righe = {r["user_id"]: (r["paese"], r["stato"]) for r in await clean_db.fetch("SELECT * FROM verify_paese")}
    assert righe == {1: ("RO", "ok"), 2: ("BR", "attesa"), 3: ("IT", "ok")}
    assert "203.0.113" not in str(await clean_db.fetch("SELECT * FROM verify_paese"))


@pytest.mark.asyncio
async def test_senza_banca_dati_o_senza_paesi_o_senza_canale_non_si_ferma_nessuno(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db, soglia=1)
    ok, _ = await _verifica(amb, 1, "203.0.113.1")  # banca dati assente: funzione spenta
    assert ok and await clean_db.fetchval("SELECT count(*) FROM verify_paese") == 0
    geoip_paesi.usa_lettore(_LettoreFinto({"203.0.113.1": {"country": {"iso_code": "RO"}}}))
    await database_module.db.set_guild_setting(GUILD, "verify_paesi", "")
    ok, _ = await _verifica(amb, 2, "203.0.113.1")  # nessun paese dichiarato: non si raccoglie niente
    assert ok and await clean_db.fetchval("SELECT count(*) FROM verify_paese") == 0
    await database_module.db.set_guild_setting(GUILD, "verify_paesi", "IT")
    amb2 = _ambiente(monkeypatch, clean_db, canale=False)
    ok, _ = await _verifica(amb2, 3, "203.0.113.1")  # nessuno a cui avvisare: mai fermare in silenzio
    assert ok
    assert await clean_db.fetchval("SELECT stato FROM verify_paese WHERE user_id = 3") == "ok"


@pytest.mark.asyncio
async def test_il_paese_di_chi_ha_gia_passato_non_si_rivaluta_e_la_lingua_e_un_dato_in_piu(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db, soglia=1)
    geoip_paesi.usa_lettore(_LettoreFinto({"203.0.113.1": {"country": {"iso_code": "RO"}}}))
    await amb.repo.salva_lingua(GUILD, 5, "ro")
    ok, _ = await _verifica(amb, 5, "203.0.113.1")
    assert not ok
    riga = await amb.repo.leggi(GUILD, 5)
    assert (riga["paese"], riga["lingua"], riga["stato"]) == ("RO", "ro", "attesa")
    embed = amb.staff.send.await_args.kwargs["embed"]
    assert "RO" in embed.description and "ro" in embed.description


# ---------------------------------------------------------------- bottoni
def _interazione(amb, *, admin=True):
    i = MagicMock()
    i.guild = amb.guild
    i.user = fake_member(50)
    i.client = amb.bot
    i.response.send_message = AsyncMock()
    i.response.edit_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    i.message = MagicMock(edit=AsyncMock(), embeds=[discord.Embed(title="x")])
    i.locale = discord.Locale.italian
    return i


@pytest.mark.asyncio
async def test_bottoni_approva_e_rifiuta(monkeypatch, clean_db):
    from core import verify_paese_staff as staff

    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    await amb.repo.registra(GUILD, 8, "BR", None, "attesa")
    await amb.repo.registra(GUILD, 9, "BR", None, "attesa")
    amb.guild.get_member = MagicMock(side_effect=lambda uid: fake_member(uid))
    # chi non è admin non decide
    monkeypatch.setattr(staff, "puo_usare", AsyncMock(return_value=False))
    i = _interazione(amb)
    await staff.decidi(i, 8, True)
    assert (await amb.repo.leggi(GUILD, 8))["stato"] == "attesa"
    assert amb.cog.run_checks_and_finalize.await_count == 0
    # admin: approva = stessi controlli e ruoli della verifica
    monkeypatch.setattr(staff, "puo_usare", AsyncMock(return_value=True))
    await staff.decidi(i, 8, True)
    assert (await amb.repo.leggi(GUILD, 8))["stato"] == "approvata"
    assert amb.cog.run_checks_and_finalize.await_count == 1
    await staff.decidi(i, 8, True)  # secondo clic: già deciso, niente di nuovo
    assert amb.cog.run_checks_and_finalize.await_count == 1
    # rifiuta: resta non verificato, nessun ban/kick da solo
    await staff.decidi(i, 9, False)
    assert (await amb.repo.leggi(GUILD, 9))["stato"] == "rifiutata"
    assert amb.cog.run_checks_and_finalize.await_count == 1


def test_bottoni_persistenti_con_id_corti():
    from core import verify_paese_staff as staff

    vista = staff.vista_decisione(2**62, 2**62)
    ids = [b.custom_id for b in vista.children]
    assert len(ids) == 2 and all(len(i) <= 100 for i in ids) and vista.timeout is None
    for item in vista.children:
        assert staff.BottoneDecisione.__discord_ui_compiled_template__.fullmatch(item.custom_id)


@pytest.mark.asyncio
async def test_chi_e_in_attesa_o_rifiutato_non_passa_da_un_ip_senza_paese(monkeypatch, clean_db):
    # Un IP che la banca dati non conosce (rete privata, VPN, IPv6 nuovo) non deve aprire la porta
    # a chi lo staff deve ancora decidere o ha già rifiutato.
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    geoip_paesi.usa_lettore(_LettoreFinto({}))
    await amb.repo.registra(GUILD, 6, "BR", None, "attesa")
    await amb.repo.registra(GUILD, 7, "BR", None, "rifiutata")
    for user_id, ip in ((6, "10.0.0.1"), (7, "::1"), (6, "2001:db8::1")):
        ok, testo = await _verifica(amb, user_id, ip)
        assert not ok and "staff" in testo.lower()
    assert amb.cog.run_checks_and_finalize.await_count == 0


@pytest.mark.asyncio
async def test_due_verifiche_insieme_da_fuori_non_passano_entrambe_sotto_soglia(monkeypatch, clean_db):
    import asyncio

    from tests.support.concorrenza import apri_connessioni

    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db, soglia=2)
    geoip_paesi.usa_lettore(_LettoreFinto({"203.0.113.1": {"country": {"iso_code": "RO"}},
                                           "203.0.113.2": {"country": {"iso_code": "BR"}}}))
    await apri_connessioni(clean_db)
    esiti = await asyncio.gather(_verifica(amb, 11, "203.0.113.1"), _verifica(amb, 12, "203.0.113.2"))
    # In fila la seconda si fermerebbe: insieme, almeno una deve restare in attesa.
    assert [ok for ok, _ in esiti].count(False) >= 1
    assert await clean_db.fetchval("SELECT count(*) FROM verify_paese WHERE stato = 'attesa'") >= 1


@pytest.mark.asyncio
async def test_i_bottoni_dello_staff_parlano_la_lingua_del_server(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db, soglia=1)
    await database_module.db.set_guild_language(GUILD, "en")
    geoip_paesi.usa_lettore(_LettoreFinto({"203.0.113.1": {"country": {"iso_code": "RO"}}}))
    ok, _ = await _verifica(amb, 21, "203.0.113.1")
    assert not ok
    etichette = [b.item.label for b in amb.staff.send.await_args.kwargs["view"].children]
    assert etichette == ["Approve", "Reject"]

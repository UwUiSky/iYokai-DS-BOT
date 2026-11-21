"""
tests/test_panel_pubblico.py
============================
Statistiche pubbliche (STA-012, con l'anonimato di STA-028), classifica web con indirizzo breve (LIV-062) e API con
chiave per server (STA-061): pagine pubbliche, indirizzo validato e unico, chiave mostrata una volta sola e salvata
come impronta, limiti di richieste, risposte uguali per «non esiste» e «non puoi».
"""

import hashlib
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import web_panel_pubblico as pubblico
from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo
from tests.test_panel_accesso import ADMIN, GUILD, LETTORE, SCRITTORE, ambiente, _come, _imposta  # noqa: F401
from tests.test_web_panel_server import _client, _csrf

UTENTE_A, UTENTE_ANONIMO = 9001, 9002


def _canale(nome, pubblico_=True):
    return SimpleNamespace(
        id=hash(nome) % 10**6, name=nome, permissions_for=lambda ruolo: SimpleNamespace(view_channel=pubblico_)
    )


@pytest.fixture
async def dati(ambiente):
    g = ambiente.guild
    g.member_count = 321
    canali = {1: _canale("generale"), 2: _canale("segreto", False), 3: _canale("<b>x</b>")}
    g.get_channel = MagicMock(side_effect=lambda cid: canali.get(cid))
    nomi = {UTENTE_A: "Aiko", UTENTE_ANONIMO: "Nome Segreto"}
    g.get_member = MagicMock(side_effect=lambda uid: ambiente.membri.get(uid) or (
        SimpleNamespace(id=uid, display_name=nomi[uid], roles=[]) if uid in nomi else None))
    oggi = date.today()
    await activity_stats_repo.flush(
        {(GUILD, oggi, 1): (50, 0), (GUILD, oggi, 2): (900, 0), (GUILD, oggi, 3): (5, 0)},
        {(GUILD, oggi, UTENTE_A): (30, 0), (GUILD, oggi, UTENTE_ANONIMO): (40, 0)}, {},
    )
    await activity_stats_repo.set_anonymous(UTENTE_ANONIMO, True)
    for nome in ("server_stats", "leveling"):
        registry.register(PremiumModule(nome, nome, "prova", category="utility"))
        await db.set_module_active_for_guild(GUILD, nome, True, changed_by=ADMIN)
    await db.pool.execute(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total) VALUES ($1, $2, 500), ($1, $3, 900)",
        GUILD, UTENTE_A, UTENTE_ANONIMO,
    )
    return ambiente


@pytest.mark.asyncio
async def test_statistiche_spente_o_inesistenti_rispondono_uguale(dati):
    client = await _client(dati.app)
    try:
        spenta = await client.get(f"/stats/{GUILD}")
        inesistente = await client.get("/stats/424242")
        assert spenta.status == inesistente.status == 404
        assert await spenta.text() == await inesistente.text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_statistiche_pubbliche_senza_canali_privati_e_con_anonimato(dati):
    await pubblico.imposta_statistiche(GUILD, True, True, ADMIN)
    client = await _client(dati.app)
    try:
        r = await client.get(f"/stats/{GUILD}")
        testo = await r.text()
        assert r.status == 200 and "321 membri" in testo
        assert "#generale" in testo
        assert "segreto" not in testo  # canale che @everyone non vede
        assert "&lt;b&gt;x&lt;/b&gt;" in testo and "<b>x</b>" not in testo
        assert "utente anonimo" in testo and "Nome Segreto" not in testo and "Aiko" in testo
        await pubblico.imposta_statistiche(GUILD, True, False, ADMIN)  # membri spenti
        senza = await (await client.get(f"/stats/{GUILD}")).text()
        assert "Aiko" not in senza and "utente anonimo" not in senza
        await db.set_module_active_for_guild(GUILD, "server_stats", False, changed_by=ADMIN)
        assert (await client.get(f"/stats/{GUILD}")).status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_solo_gli_admin_cambiano_cosa_e_pubblico(dati):
    await _imposta(dati, "lettura", [7001])
    await _imposta(dati, "scrittura", [7002])
    for utente in (LETTORE, SCRITTORE):
        client = await _come(dati, utente)
        try:
            for percorso in ("statistiche", "classifica", "api"):
                assert (await client.get(f"/server/{GUILD}/{percorso}")).status == 403
            csrf = await _csrf(client, f"/server/{GUILD}")
            r = await client.post(
                f"/server/{GUILD}/statistiche", data={"csrf": csrf, "pubbliche": "1", "membri": "1"}, allow_redirects=False
            )
            assert r.status == 403
            r = await client.post(f"/server/{GUILD}/api", data={"csrf": csrf, "azione": "crea"}, allow_redirects=False)
            assert r.status == 403
        finally:
            await client.close()
    assert (await web_panel_pubblico_repo.leggi(GUILD)).stat_pubbliche is False
    assert (await web_panel_pubblico_repo.leggi(GUILD)).api_prefisso is None


@pytest.mark.asyncio
async def test_l_admin_accende_le_statistiche_dal_pannello(dati):
    client = await _come(dati, ADMIN)
    try:
        csrf = await _csrf(client, f"/server/{GUILD}/statistiche")
        r = await client.post(f"/server/{GUILD}/statistiche", data={"csrf": csrf, "pubbliche": "1", "membri": "0"}, allow_redirects=False)
        assert "esito=salvato" in r.headers["Location"]
        assert (await web_panel_pubblico_repo.leggi(GUILD)).stat_pubbliche is True
        storto = await client.post(f"/server/{GUILD}/statistiche", data={"csrf": csrf, "pubbliche": "si", "membri": "0"}, allow_redirects=False)
        assert "esito=non_valido" in storto.headers["Location"]
        senza_csrf = await client.post(f"/server/{GUILD}/statistiche", data={"pubbliche": "0", "membri": "0"}, allow_redirects=False)
        assert senza_csrf.status == 403
    finally:
        await client.close()


@pytest.mark.parametrize("testo", [
    "ab", "a" * 33, "-ciao", "ciao-", "ci--ao", "ciao ciao", "ciao/..", "càsa", "admin", "API", "iyokai-bot", "discord-it",
    "12345", "static", "", "ciao_ciao",
])
def test_indirizzi_non_validi(testo):
    if testo == "":
        pytest.skip("il vuoto non è un indirizzo: toglie la pubblicazione")
    with pytest.raises(ImpostazioneNonValida):
        pubblico.valida_slug(testo)


def test_indirizzo_valido_va_in_minuscolo():
    assert pubblico.valida_slug("  Mio-Server-9 ") == "mio-server-9"


@pytest.mark.asyncio
async def test_indirizzo_unico_e_classifica_pubblica(dati):
    assert await pubblico.imposta_slug(GUILD, "Il-Mio-Server", ADMIN) == "il-mio-server"
    with pytest.raises(ImpostazioneNonValida):  # un altro server non lo prende, nemmeno cambiando le maiuscole
        await pubblico.imposta_slug(GUILD + 1, "IL-MIO-SERVER", ADMIN)
    client = await _client(dati.app)
    try:
        r = await client.get("/c/il-mio-server")
        testo = await r.text()
        assert r.status == 200 and "Aiko" in testo and "utente anonimo" in testo and "Nome Segreto" not in testo
        assert testo.index("utente anonimo") < testo.index("Aiko")  # 900 XP davanti a 500
        assert (await client.get("/c/non-esiste-qui")).status == 404
        await db.set_module_active_for_guild(GUILD, "leveling", False, changed_by=ADMIN)
        assert (await client.get("/c/il-mio-server")).status == 404
        await pubblico.imposta_slug(GUILD, "", ADMIN)  # non più pubblica
        await db.set_module_active_for_guild(GUILD, "leveling", True, changed_by=ADMIN)
        assert (await client.get("/c/il-mio-server")).status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chiave_api_una_sola_volta_e_solo_l_impronta(dati):
    await pubblico.imposta_statistiche(GUILD, False, True, ADMIN)
    client = await _come(dati, ADMIN)
    try:
        csrf = await _csrf(client, f"/server/{GUILD}/api")
        r = await client.post(f"/server/{GUILD}/api", data={"csrf": csrf, "azione": "crea"})
        testo = await r.text()
        chiave = testo.split("<code>iyk_")[1].split("</code>")[0]
        chiave = "iyk_" + chiave
        assert r.status == 200 and "non si potrà più vedere" in testo
        riga = await dati.pool.fetchrow("SELECT * FROM web_panel_pubblico WHERE guild_id = $1", GUILD)
        assert riga["api_impronta"] == hashlib.sha256(chiave.encode()).hexdigest()
        assert chiave not in "".join(str(v) for v in riga.values())
        assert chiave not in await (await client.get(f"/server/{GUILD}/api")).text()

        senza = await client.get("/api/v1/stats")
        sbagliata = await client.get("/api/v1/stats", headers={"Authorization": "Bearer iyk_" + "x" * 43})
        assert senza.status == sbagliata.status == 401 and await senza.text() == await sbagliata.text()
        buona = await client.get("/api/v1/stats", headers={"Authorization": f"Bearer {chiave}"})
        corpo = await buona.json()
        assert buona.status == 200 and corpo["membri"] == 321
        assert [c["nome"] for c in corpo["canali"]] == ["generale", "<b>x</b>"]
        nomi = {m["nome"]: m for m in corpo["membri_piu_attivi"]}
        assert nomi["Aiko"]["id"] == str(UTENTE_A) and "id" not in nomi["utente anonimo"]

        nuova = await client.post(f"/server/{GUILD}/api", data={"csrf": csrf, "azione": "crea"})
        chiave2 = "iyk_" + (await nuova.text()).split("<code>iyk_")[1].split("</code>")[0]
        vecchia = await client.get("/api/v1/stats", headers={"Authorization": f"Bearer {chiave}"})
        assert vecchia.status == 401
        assert (await client.get("/api/v1/stats", headers={"Authorization": f"Bearer {chiave2}"})).status == 200
        await client.post(f"/server/{GUILD}/api", data={"csrf": csrf, "azione": "revoca"}, allow_redirects=False)
        assert (await client.get("/api/v1/stats", headers={"Authorization": f"Bearer {chiave2}"})).status == 401
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_api_solo_lettura_e_con_limite(dati):
    chiave = await pubblico.crea_chiave(GUILD, ADMIN)
    client = await _client(dati.app)
    try:
        intest = {"Authorization": f"Bearer {chiave}"}
        for metodo in (client.post, client.put, client.delete):
            assert (await metodo("/api/v1/stats", headers=intest)).status == 405
        stati = [(await client.get("/api/v1/stats", headers=intest)).status for _ in range(32)]
        assert stati[:30] == [200] * 30 and stati[30:] == [429, 429]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_senza_membri_l_api_non_li_da(dati):
    chiave = await pubblico.crea_chiave(GUILD, ADMIN)
    client = await _client(dati.app)
    try:
        corpo = await (await client.get("/api/v1/stats", headers={"Authorization": f"Bearer {chiave}"})).json()
        assert corpo["membri_piu_attivi"] == []
    finally:
        await client.close()

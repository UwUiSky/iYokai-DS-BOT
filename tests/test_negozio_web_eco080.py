"""
tests/test_negozio_web_eco080.py
================================
ECO-080 (D121): il negozio del server sfogliabile dal sito. Pagina pubblica in sola lettura `/n/{id}`, spenta di base,
accesa dallo staff (`/admin-economia limiti negozio_web:sì`); testi con escape, al massimo 50 oggetti, mai dati interni
(ruolo richiesto, messaggio di acquisto, azione). Stesso 404 per «non esiste» e «spento».
"""

import pytest

from core import web_panel_pubblico as pubblico
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.shop_repo import shop_repo
from tests.test_panel_accesso import ADMIN, GUILD, ambiente  # noqa: F401
from tests.test_web_panel_server import _client


@pytest.fixture
async def negozio(ambiente):
    if registry.get("leveling") is None:
        registry.register(PremiumModule("leveling", "leveling", "prova", category="utility"))
    await db.set_module_active_for_guild(GUILD, "leveling", True, changed_by=ADMIN)
    return ambiente


async def _oggetto(nome, prezzo=100, **kw):
    return await shop_repo.add_item(GUILD, nome, prezzo, None, kw.pop("descrizione", None), **kw)


async def test_spento_o_inesistente_rispondono_uguale(negozio):
    client = await _client(negozio.app)
    try:
        spento = await client.get(f"/n/{GUILD}")
        inesistente = await client.get("/n/424242")
        assert spento.status == inesistente.status == 404
        assert await spento.text() == await inesistente.text()
    finally:
        await client.close()


async def test_acceso_mostra_nome_prezzo_e_non_i_dati_interni(negozio):
    await _oggetto("<b>Spada</b>", 250, descrizione="Una <i>spada</i> & basta")
    await db.set_guild_setting(GUILD, pubblico.SETTING_NEGOZIO_WEB, True)
    client = await _client(negozio.app)
    try:
        r = await client.get(f"/n/{GUILD}")
        testo = await r.text()
        assert r.status == 200 and "250" in testo
        assert "<b>Spada</b>" not in testo and "&lt;b&gt;Spada&lt;/b&gt;" in testo  # escape
        assert "<i>spada</i>" not in testo
    finally:
        await client.close()


async def test_al_massimo_50_oggetti_e_modulo_spento_nasconde():
    voci = await pubblico.dati_negozio_da_oggetti([type("O", (), {"name": f"o{i}", "price": i, "description": None, "category": None,
                                                                  "stock": None, "a_rotazione": False})() for i in range(80)])
    assert len(voci) == pubblico.RIGHE_NEGOZIO_WEB == 50


async def test_modulo_livelli_spento_e_404(negozio):
    await _oggetto("Mela")
    await db.set_guild_setting(GUILD, pubblico.SETTING_NEGOZIO_WEB, True)
    await db.set_module_active_for_guild(GUILD, "leveling", False, changed_by=ADMIN)
    client = await _client(negozio.app)
    try:
        assert (await client.get(f"/n/{GUILD}")).status == 404
    finally:
        await client.close()


async def test_scorte_esaurite_si_dicono_e_i_dati_interni_non_escono():
    voci = await pubblico.dati_negozio_da_oggetti([type("O", (), {"name": "Pozione", "price": 5, "description": "x" * 900, "category": "Cura",
                                                                  "stock": 0, "a_rotazione": False, "reply_text": "SEGRETO", "required_role_id": 7,
                                                                  "azione_valore": 99})()])
    assert voci[0]["esaurito"] is True and len(voci[0]["descrizione"]) <= 300
    assert "SEGRETO" not in str(voci) and "99" not in str(voci)

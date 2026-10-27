"""
tests/test_panel_proprietario.py
================================
Pagine legali pubbliche (privacy e termini, §24.6 e C.5) e pagina del proprietario
del bot (C.4): moduli premium, server, AI in manutenzione. Stessi punti unici dei comandi.
"""

import pytest

from core import panel_bridge
from core.premium import registry
from core.repositories.ai_repo import AiRepository
from core.web_panel_logic import voci_privacy
from core.data_registry import REGISTRO
from tests.test_web_panel_server import ADMIN, ESTRANEO, _client, _csrf, _entra, ambiente  # noqa: F401


def _proprietario(monkeypatch, user_id):
    """`OWNER_ID` è congelato: si sostituisce il controllo del ponte."""
    monkeypatch.setattr(panel_bridge, "e_proprietario", lambda uid: uid == user_id)


@pytest.fixture
def owner(monkeypatch):
    _proprietario(monkeypatch, ADMIN)


@pytest.mark.asyncio
async def test_privacy_e_termini_sono_pubbliche(ambiente):  # noqa: F811
    client = await _client(ambiente.app)
    try:
        r = await client.get("/privacy")
        testo = await r.text()
        assert r.status == 200 and "non addestra modelli" in testo and "I miei dati" in testo
        # l'elenco viene dal registro dei dati: una tabella con dati dell'utente c'è
        assert "Casi di moderazione" in testo
        t = await client.get("/termini")
        assert t.status == 200 and "informativa sulla privacy" in await t.text()
        assert "/privacy" in await (await client.get("/")).text()
    finally:
        await client.close()


def test_voci_privacy_solo_dati_di_persone_e_dichiarano_la_cancellazione():
    voci = voci_privacy(REGISTRO, 90)
    assert voci and all(v["se_chiedi"] and v["durata"] for v in voci)
    assert len(voci) < len(REGISTRO)  # le impostazioni dei server non sono dati personali


@pytest.mark.asyncio
async def test_privacy_elenca_i_fornitori_ai(ambiente, monkeypatch):  # noqa: F811
    monkeypatch.setattr(panel_bridge, "info_legali", lambda: {
        "voci": [], "giorni_dopo_uscita": 90, "fornitori_ai": ["alfa", "beta"], "supporto": "https://discord.gg/x",
    })
    client = await _client(ambiente.app)
    try:
        testo = await (await client.get("/privacy")).text()
        assert "alfa, beta" in testo and "https://discord.gg/x" in testo
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_proprietario_solo_per_l_owner(ambiente, owner, monkeypatch):  # noqa: F811
    client = await _client(ambiente.app)
    try:
        r = await client.get("/proprietario", allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "/accedi"
        _proprietario(monkeypatch, ESTRANEO)
        await _entra(client)
        assert (await client.get("/proprietario")).status == 403
        csrf = await _csrf(client, "/")
        r = await client.post("/proprietario/premium", data={"csrf": csrf, "nome": "modulo_web", "attivo": "1"})
        assert r.status == 403 and not registry.is_module_premium("modulo_web")
        assert "/proprietario" not in await (await client.get("/")).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_proprietario_cambia_il_premium_come_il_comando(ambiente, owner):  # noqa: F811
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        pagina = await (await client.get("/proprietario")).text()
        assert "modulo_web" in pagina and "Server di prova" not in pagina and "Nessun server" not in pagina
        csrf = await _csrf(client, "/proprietario")
        senza = await client.post("/proprietario/premium", data={"nome": "modulo_web", "attivo": "1"})
        assert senza.status == 403
        r = await client.post(
            "/proprietario/premium", data={"csrf": csrf, "nome": "modulo_web", "attivo": "1"}, allow_redirects=False
        )
        assert r.headers["Location"].endswith("esito=salvato")
        assert registry.is_module_premium("modulo_web")
        stato = await ambiente.pool.fetchrow("SELECT is_active, updated_by FROM premium_module_flags WHERE module_name = 'modulo_web'")
        assert (stato["is_active"], stato["updated_by"]) == (True, ADMIN)
        assert await ambiente.pool.fetchval("SELECT count(*) FROM premium_toggle_history WHERE module_name = 'modulo_web'") == 1
        # un modulo che non esiste e un valore strano non cambiano niente
        for dati in ({"nome": "inesistente", "attivo": "1"}, {"nome": "modulo_web", "attivo": "forse"}):
            r = await client.post("/proprietario/premium", data={"csrf": csrf, **dati}, allow_redirects=False)
            assert r.headers["Location"].endswith("esito=non_valido")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_proprietario_mette_l_ai_in_manutenzione(ambiente, owner, monkeypatch):  # noqa: F811
    from core.ai_servizio import imposta_servizio_ai
    from tests.support.ai_finto import servizio_finto

    repo = AiRepository(lambda: ambiente.pool)
    servizio, _ = servizio_finto(repo)
    imposta_servizio_ai(servizio)
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, "/proprietario")
        r = await client.post(
            "/proprietario/ai", data={"csrf": csrf, "attivo": "1", "messaggio": "Torno alle 18"}, allow_redirects=False
        )
        assert r.headers["Location"].endswith("esito=salvato")
        assert await repo.manutenzione() == "Torno alle 18"
        assert "Torno alle 18" in await (await client.get("/proprietario")).text()
        await client.post("/proprietario/ai", data={"csrf": csrf, "attivo": "0"}, allow_redirects=False)
        assert await repo.manutenzione() is None
    finally:
        imposta_servizio_ai(None)
        await client.close()


def test_e_proprietario_confronta_con_owner_id():
    from core.config import config as cfg

    assert panel_bridge.e_proprietario(cfg.OWNER_ID) and not panel_bridge.e_proprietario(cfg.OWNER_ID + 1)
    assert not panel_bridge.e_proprietario(None)

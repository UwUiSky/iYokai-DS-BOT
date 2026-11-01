"""
tests/test_web_panel_ai.py
==========================
Pagine AI del pannello (§25.91, §25.92, §25.93): altre scelte (lore, limiti, parole vietate, canali spenti), ultimo
riepilogo e «Uso dell'AI». Sessioni e database veri, Discord finto.
"""

import pytest

from core import ai_impostazioni as impostazioni
from core.ai_pannello_logic import numeri, righe_uso
from core.repositories.ai_repo import ai_repo
from core.repositories.ai_riepilogo_repo import ai_riepilogo_repo
from tests.support.discord_fakes import fake_text_channel
from tests.test_web_panel_server import GUILD, _client, _csrf, _entra, ambiente  # noqa: F401


@pytest.fixture
def ai(ambiente, clean_db, monkeypatch):
    for r in (ai_repo, ai_riepilogo_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    guild = ambiente.bot.guilds[0]
    canale = fake_text_channel(7701, "generale")
    guild.text_channels = [canale]
    guild.get_channel = lambda i: canale if i == 7701 else None
    return ambiente


def test_pulizia_parole_vietate():
    assert impostazioni.pulisci_parole_vietate("Politica\n  politica \nx\nbanana, mela") == ("politica", "banana", "mela")
    assert len(impostazioni.pulisci_parole_vietate("\n".join(f"parola{i}" for i in range(80)))) == 50
    assert numeri(["12", "x", "-3", "9" * 30]) == [12]


def test_uso_elenca_solo_tabelle_ai_con_conservazione():
    righe = righe_uso()
    assert righe and all(r.nome.startswith("ai_") for r in righe)
    assert any(r.nome == "ai_vocali" and r.quanto == "90 giorni" for r in righe)


@pytest.mark.asyncio
async def test_salva_lore_limiti_vietate_e_canali(ai):
    client = await _client(ai.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/server/{GUILD}/ai/altro")
        base = f"/server/{GUILD}/ai/altro"
        senza = await client.post(base, data={"azione": "vietate", "parole": "x"})
        assert senza.status == 403
        await client.post(base, data={"csrf": csrf, "azione": "vietate", "parole": "politica\nsoldi"})
        await client.post(base, data={"csrf": csrf, "azione": "lore", "tema": "pirati", "testo": "Siamo pirati"})
        await client.post(base, data={
            "csrf": csrf, "azione": "limiti", "tetto_mensile_cent": "500", "quota_utente_giorno": "7",
            "quota_utente_30g": "50", "quota_funzione_giorno": "100", "quota_immagini_settimana": "2",
        })
        await client.post(base, data=[("csrf", csrf), ("azione", "canali"), ("spenti", "7701"), ("spenti", "999")])
        cfg = await ai_repo.get_config(GUILD)
        assert cfg.parole_vietate == ("politica", "soldi") and cfg.lore_tema == "pirati"
        assert (cfg.tetto_mensile_cent, cfg.quota_utente_giorno) == (500, 7)
        assert cfg.canali_spenti == (7701,)  # il canale 999 non è del server
        sbagliato = await client.post(base, data={"csrf": csrf, "azione": "limiti", "tetto_mensile_cent": "x"}, allow_redirects=False)
        assert sbagliato.headers["Location"].endswith("esito=non_valido")
        pagina = await (await client.get(base)).text()
        assert "politica" in pagina and "Siamo pirati" in pagina
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_riepilogo_e_uso_si_leggono(ai):
    await ai_riepilogo_repo.imposta(GUILD, attivo=True, canale_id=7701)
    await ai_riepilogo_repo.salva_testo(GUILD, "Oggi 120 messaggi <script>")
    client = await _client(ai.app)
    try:
        await _entra(client)
        r = await (await client.get(f"/server/{GUILD}/ai/riepilogo")).text()
        assert "Oggi 120 messaggi" in r and "<script>" not in r and "generale" in r
        u = await (await client.get(f"/server/{GUILD}/ai/uso")).text()
        assert "Cosa conserva l&#39;AI" in u or "Cosa conserva l'AI" in u
        assert "90 giorni" in u
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_estraneo_non_vede_le_pagine_ai(ai):
    from tests.test_web_panel_server import ESTRANEO

    ai.oauth.utente_id = ESTRANEO
    client = await _client(ai.app)
    try:
        await _entra(client)
        for p in ("altro", "riepilogo", "uso"):
            assert (await client.get(f"/server/{GUILD}/ai/{p}")).status == 403
    finally:
        await client.close()

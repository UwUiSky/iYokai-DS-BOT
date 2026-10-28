"""
tests/test_panel_ai.py
======================
Pagina AI del server nel pannello (SPEC §24.2): consenso letto prima di accendere,
spegnimento, privacy, lunghezza e memoria dagli stessi punti dei comandi `/ai`.
"""

import pytest

from core.ai_impostazioni import ImpostazioneNonValida, valida_scelte
from core.repositories.ai_repo import AiRepository
from tests.test_web_panel_server import ADMIN, GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

PAGINA = f"/server/{GUILD}/ai"


def test_valida_scelte_rifiuta_valori_fuori_limite():
    assert valida_scelte({"privacy": "senza_messaggi", "conservazione_minuti": 0})
    for male in ({"privacy": "boh"}, {"lunghezza": "enorme"}, {"conservazione_minuti": 5000},
                 {"conservazione_minuti": True}, {"altro": 1}, {}):
        with pytest.raises(ImpostazioneNonValida):
            valida_scelte(male)


@pytest.mark.asyncio
async def test_accende_solo_col_consenso_e_poi_cambia_le_scelte(ambiente):  # noqa: F811
    repo = AiRepository(lambda: ambiente.pool)
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        pagina = await (await client.get(PAGINA)).text()
        assert "non addestrare" in pagina and "**" not in pagina and "Accendi l'AI" in pagina
        csrf = await _csrf(client, PAGINA)
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "accendi"}, allow_redirects=False)
        assert r.headers["Location"].endswith("esito=ai_consenso")
        assert not (await repo.get_config(GUILD)).attivo
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "accendi", "consenso": "1"}, allow_redirects=False)
        assert r.headers["Location"].endswith("esito=salvato")
        cfg = await repo.get_config(GUILD)
        assert cfg.attivo and cfg.consenso_da == ADMIN

        r = await client.post(PAGINA, data={
            "csrf": csrf, "azione": "scelte", "privacy": "senza_messaggi", "lunghezza": "corta", "conservazione_minuti": "5",
        }, allow_redirects=False)
        assert r.headers["Location"].endswith("esito=salvato")
        cfg = await repo.get_config(GUILD)
        assert (cfg.privacy, cfg.lunghezza, cfg.conservazione_minuti) == ("senza_messaggi", "corta", 5)

        for dati in ({"azione": "scelte", "privacy": "boh", "lunghezza": "corta", "conservazione_minuti": "5"},
                     {"azione": "scelte", "privacy": "completa", "lunghezza": "corta", "conservazione_minuti": "x"},
                     {"azione": "scelte", "privacy": "completa", "lunghezza": "corta", "conservazione_minuti": "99999"},
                     {"azione": "boh"}):
            r = await client.post(PAGINA, data={"csrf": csrf, **dati}, allow_redirects=False)
            assert r.headers["Location"].endswith("esito=non_valido"), dati
        assert (await repo.get_config(GUILD)).privacy == "senza_messaggi"

        await client.post(PAGINA, data={"csrf": csrf, "azione": "spegni"}, allow_redirects=False)
        assert not (await repo.get_config(GUILD)).attivo
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_serve_l_accesso_e_il_csrf(ambiente):  # noqa: F811
    client = await _client(ambiente.app)
    try:
        r = await client.get(PAGINA, allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "/accedi"
        await _entra(client)
        assert (await client.post(PAGINA, data={"azione": "spegni"})).status == 403
    finally:
        await client.close()

"""
tests/test_panel_dati.py
========================
Pagina «I miei dati» del pannello (#46, parte web): copia dei dati e
richiesta di cancellazione, con le stesse funzioni di `/utility privacy`.
Solo per chi è entrato, CSRF, una copia al minuto, e il testo di una
richiesta solo al suo autore.
"""

import json

import pytest

from core.repositories.data_deletion_request_repo import data_deletion_request_repo
from tests.test_web_panel_server import ADMIN, _client, _csrf, _entra, ambiente  # noqa: F401

PAGINA = "/miei-dati"


@pytest.mark.asyncio
async def test_serve_l_accesso(ambiente):  # noqa: F811
    client = await _client(ambiente.app)
    try:
        r = await client.get(PAGINA, allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "/accedi"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_copia_dei_dati_una_al_minuto(ambiente):  # noqa: F811
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        assert "I miei dati" in await (await client.get("/")).text()
        csrf = await _csrf(client, PAGINA)
        senza = await client.post(PAGINA, data={"azione": "esporta"}, allow_redirects=False)
        assert senza.status == 403
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "esporta"}, allow_redirects=False)
        assert r.status == 200
        assert f"iyokai-dati-{ADMIN}.json" in r.headers["Content-Disposition"]
        assert r.headers["Cache-Control"] == "no-store"
        assert isinstance(json.loads(await r.read()), dict)
        di_nuovo = await client.post(PAGINA, data={"csrf": csrf, "azione": "esporta"}, allow_redirects=False)
        assert di_nuovo.headers["Location"].endswith("esito=dati_attendi")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_richiesta_di_cancellazione(ambiente):  # noqa: F811
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, PAGINA)
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "cancella", "motivo": " basta "}, allow_redirects=False)
        numero = int(r.headers["Location"].split("richiesta=")[1])
        richiesta = await data_deletion_request_repo.get(numero)
        assert richiesta["user_id"] == ADMIN and richiesta["motivo"] == "basta"
        pagina = await (await client.get(r.headers["Location"])).text()
        assert f"Richiesta ricevuta (numero {numero})" in pagina and "Cosa resta" in pagina

        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "cancella"}, allow_redirects=False)
        assert r.headers["Location"].endswith(f"richiesta={numero}")

        altra, _ = await data_deletion_request_repo.crea(ADMIN + 1, None)
        pagina = await (await client.get(f"{PAGINA}?richiesta={altra}")).text()
        assert "Richiesta ricevuta" not in pagina
        assert (await client.get(f"{PAGINA}?richiesta=99999999999")).status == 200
    finally:
        await client.close()

"""
tests/test_web_panel_editor.py
==============================
SPEC §24.5 (#91): editor dell'embed e del messaggio di benvenuto nel pannello. Stessi controlli e stesso
archivio dei comandi, anteprima senza aprire indirizzi esterni, CSRF.
"""

from types import SimpleNamespace

import pytest

from core import web_editor as editor
from core.repositories.greetings_repo import greetings_repo
from core.repositories.saved_embed_repo import saved_embed_repo
from tests.test_web_panel_server import GUILD, _client, _csrf, _entra, ambiente  # noqa: F401


@pytest.fixture
def mondo(ambiente, monkeypatch):  # noqa: F811
    guild = ambiente.bot.guilds[0]
    guild.text_channels = [SimpleNamespace(id=77, name="benvenuto")]
    guild.get_channel = lambda i: guild.text_channels[0] if i == 77 else None
    guild.member_count = 10

    async def sicuro(url):
        return "interno" not in url

    monkeypatch.setattr(editor, "url_e_sicuro", sicuro)
    return ambiente


async def _post(client, percorso, csrf, **campi):
    return await client.post(percorso, data={"csrf": csrf, **campi})


@pytest.mark.asyncio
async def test_embed_anteprima_salva_aggiorna_elimina(mondo):
    client = await _client(mondo.app)
    try:
        await _entra(client)
        p = f"/server/{GUILD}/editor/embed"
        csrf = await _csrf(client, p)
        senza = await client.post(p, data={"azione": "salva", "nome": "uno", "titolo": "T"})
        assert senza.status == 403 and await saved_embed_repo.get(GUILD, "uno") is None

        anteprima = await _post(client, p, csrf, azione="anteprima", titolo="Ciao <b>", colore="#ff8800", immagine="https://x.example/a.png")
        corpo = await anteprima.text()
        assert anteprima.status == 200 and "Ciao &lt;b&gt;" in corpo and "#ff8800" in corpo and "<b>" not in corpo.split("Anteprima")[-1]
        assert "<img" not in corpo  # il pannello non apre l'indirizzo dell'immagine
        assert await saved_embed_repo.get(GUILD, "uno") is None  # l'anteprima non salva

        ok = await _post(client, p, csrf, azione="salva", nome="uno", titolo="Titolo", descrizione="Testo", campo1_nome="A", campo1_valore="B", campo1_inline="1")
        assert ok.status == 200 and "Embed creato" in await ok.text()
        salvato = await saved_embed_repo.get(GUILD, "uno")
        assert salvato.data["title"] == "Titolo" and salvato.data["fields"] == [["A", "B", True]]
        again = await _post(client, p, csrf, azione="salva", nome="UNO", titolo="Nuovo")
        assert "Embed aggiornato" in await again.text()
        assert (await saved_embed_repo.get(GUILD, "uno")).data["title"] == "Nuovo"
        assert "modifica=uno" in await (await client.get(p)).text()
        assert 'value="Nuovo"' in await (await client.get(p + "?modifica=uno")).text()

        gone = await _post(client, p, csrf, azione="elimina", nome="uno")
        assert "Embed eliminato" in await gone.text() and await saved_embed_repo.get(GUILD, "uno") is None
        assert "Non trovo" in await (await _post(client, p, csrf, azione="elimina", nome="uno")).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_embed_rifiuta_gli_errori_del_comando(mondo):
    client = await _client(mondo.app)
    try:
        await _entra(client)
        p = f"/server/{GUILD}/editor/embed"
        csrf = await _csrf(client, p)
        casi = [
            ({"nome": "ok", "titolo": "x" * 257}, "Il titolo supera"),
            ({"nome": "ok"}, "è vuoto"),
            ({"nome": "ok", "titolo": "T", "colore": "rosso"}, "#RRGGBB"),
            ({"nome": "ok", "titolo": "T", "immagine": "ftp://x"}, "http://"),
            ({"nome": "ok", "titolo": "T", "immagine": "https://interno.example/a"}, "non è ammesso"),
            ({"nome": "Nome Storto", "titolo": "T"}, "solo lettere minuscole"),
            ({"nome": "ok", "titolo": "T", "campo2_nome": "solo nome"}, "vuoto"),
        ]
        for campi, atteso in casi:
            r = await _post(client, p, csrf, azione="salva", **campi)
            assert r.status == 400 and atteso in await r.text(), campi
        assert await saved_embed_repo.list(GUILD) == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_benvenuto_anteprima_e_salvataggio(mondo):
    client = await _client(mondo.app)
    try:
        await _entra(client)
        p = f"/server/{GUILD}/editor/benvenuto"
        csrf = await _csrf(client, p)
        r = await _post(client, p, csrf, azione="anteprima", messaggio="Ciao {user} su {server}, siamo {membercount}", canale="77")
        corpo = await r.text()
        assert r.status == 200 and "Ciao @Nuovo su Server &lt;b&gt;di&lt;/b&gt; prova, siamo 10" in corpo
        assert not (await greetings_repo.get_config(GUILD)).welcome_enabled

        r = await _post(client, p, csrf, azione="salva", messaggio="Benvenuto {user}!", canale="77", attivo="1", dm="1")
        assert r.status == 200 and "Salvato." in await r.text()
        c = await greetings_repo.get_config(GUILD)
        assert (c.welcome_enabled, c.welcome_channel_id, c.welcome_message, c.welcome_dm, c.welcome_ping_ruoli) == (True, 77, "Benvenuto {user}!", True, False)
        assert "Benvenuto {user}!" in await (await client.get(p)).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_benvenuto_rifiuta_troppo_lungo_vuoto_e_acceso_senza_canale(mondo):
    client = await _client(mondo.app)
    try:
        await _entra(client)
        p = f"/server/{GUILD}/editor/benvenuto"
        csrf = await _csrf(client, p)
        for campi, atteso in (
            ({"messaggio": "{user}" * 100}, "Accorcialo"),
            ({"messaggio": "  "}, "Scrivi il messaggio"),
            ({"messaggio": "Ciao", "attivo": "1", "canale": "999"}, "Scegli il canale"),
        ):
            r = await _post(client, p, csrf, azione="salva", **campi)
            assert r.status == 400 and atteso in await r.text(), campi
        assert (await greetings_repo.get_config(GUILD)).welcome_message != "Ciao"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_anonimo_e_estraneo_non_entrano(ambiente):
    anonimo = await _client(ambiente.app)
    try:
        for percorso in ("/editor/embed", "/editor/benvenuto"):
            r = await anonimo.get(f"/server/{GUILD}{percorso}", allow_redirects=False)
            assert r.status in (302, 401, 403)
    finally:
        await anonimo.close()

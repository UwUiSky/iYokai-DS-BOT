"""
tests/test_panel_aspetto.py
===========================
Pagina «Aspetto del bot» del pannello (CFG-021, CFG-030, #122): nome e
descrizione, caricamento di avatar e banner letto a parti (il resto del
pannello accetta 8 KB), CSRF anche sul caricamento, dimensione massima.
"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from PIL import Image

import core.premium as premium_module
from core import bot_aspetto
from core.web_panel_logic import LimiteFrequenza
from tests.test_web_panel_server import GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

PAGINA = f"/server/{GUILD}/aspetto"


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def aspetto(ambiente, monkeypatch):  # noqa: F811
    async def _accesso(guild_id, modulo, bot=None):
        return True

    monkeypatch.setattr(premium_module, "guild_has_premium_access", _accesso)
    monkeypatch.setattr(bot_aspetto, "_limite_immagini", LimiteFrequenza(4, 600))
    me = SimpleNamespace(
        edit=AsyncMock(), nick="Vecchio", guild_avatar=SimpleNamespace(url="https://cdn.discordapp.com/a.png"),
        guild_banner=None,
    )
    ambiente.bot.get_guild(GUILD).me = me
    return SimpleNamespace(ambiente=ambiente, me=me)


def _modulo(csrf, tipo="avatar", dati=None):
    form = aiohttp.FormData()
    if csrf is not None:
        form.add_field("csrf", csrf)
    form.add_field("tipo", tipo)
    form.add_field("immagine", dati if dati is not None else _png(), filename="a.png", content_type="image/png")
    return form


def _esito(risposta):
    assert risposta.status == 302
    return risposta.headers["Location"].split("esito=")[1]


@pytest.mark.asyncio
async def test_nome_descrizione_e_togli(aspetto):
    client = await _client(aspetto.ambiente.app)
    try:
        await _entra(client)
        pagina = await (await client.get(PAGINA)).text()
        assert 'value="Vecchio"' in pagina and "https://cdn.discordapp.com/a.png" in pagina
        csrf = await _csrf(client, PAGINA)
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "nick", "valore": " Nuovo "}, allow_redirects=False)
        assert _esito(r) == "asp_ok"
        assert aspetto.me.edit.call_args.kwargs["nick"] == "Nuovo"
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "bio", "valore": ""}, allow_redirects=False)
        assert _esito(r) == "asp_ok" and aspetto.me.edit.call_args.kwargs["bio"] is None
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "togli_avatar"}, allow_redirects=False)
        assert _esito(r) == "asp_ok" and aspetto.me.edit.call_args.kwargs["avatar"] is None
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "altro"}, allow_redirects=False)
        assert _esito(r) == "non_valido"
        assert "Fatto: l&#39;aspetto" in await (await client.get(PAGINA + "?esito=asp_ok")).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_caricamento_immagine(aspetto):
    client = await _client(aspetto.ambiente.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, PAGINA)
        r = await client.post(PAGINA + "/immagine", data=_modulo(csrf, "banner"), allow_redirects=False)
        assert _esito(r) == "asp_ok"
        assert aspetto.me.edit.call_args.kwargs["banner"] == _png()

        r = await client.post(PAGINA + "/immagine", data=_modulo(csrf, dati=b"testo"), allow_redirects=False)
        assert _esito(r) == "asp_immagine_non_valida"
        r = await client.post(PAGINA + "/immagine", data=_modulo(csrf, tipo="icona"), allow_redirects=False)
        assert _esito(r) == "non_valido"

        aspetto.me.edit.reset_mock()
        r = await client.post(PAGINA + "/immagine", data=_modulo(None), allow_redirects=False)
        assert r.status == 403
        r = await client.post(PAGINA + "/immagine", data=_modulo("sbagliato"), allow_redirects=False)
        assert r.status == 403
        grande = b"\0" * (bot_aspetto.MAX_IMMAGINE + 128 * 1024)
        r = await client.post(PAGINA + "/immagine", data=_modulo(csrf, dati=grande), allow_redirects=False)
        assert r.status == 413
        aspetto.me.edit.assert_not_awaited()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_il_resto_del_pannello_resta_a_8_kb(aspetto):
    client = await _client(aspetto.ambiente.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, PAGINA)
        r = await client.post(PAGINA, data={"csrf": csrf, "azione": "bio", "valore": "x" * 20_000}, allow_redirects=False)
        assert r.status == 413
    finally:
        await client.close()

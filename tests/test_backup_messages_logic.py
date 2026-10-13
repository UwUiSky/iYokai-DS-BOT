"""
tests/test_backup_messages_logic.py
===================================
D8 / M 12.17 (#68): copia degli ultimi N messaggi per canale nel server di
backup, con il webhook del canale, uno alla volta e in ordine cronologico.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest

import core.backup_messages_logic as modulo
from core.backup_clone_logic import RiepilogoCopia
from core.backup_messages_logic import MESSAGGI_PER_CANALE, copia_messaggi

URL_A = "https://discord.com/api/webhooks/1/a"
URL_B = "https://discord.com/api/webhooks/2/b"


class _Resp:
    status = 400
    reason = "x"


def _http(cls=discord.HTTPException):
    return cls(_Resp(), "errore")


def _msg(testo, nome="Mario", allegati=(), tipo=discord.MessageType.default):
    return SimpleNamespace(
        content=testo,
        type=tipo,
        attachments=[SimpleNamespace(url=u) for u in allegati],
        author=SimpleNamespace(
            display_name=nome, display_avatar=SimpleNamespace(url=f"https://cdn/{nome}.png")
        ),
    )


class _Sorgente(discord.TextChannel):
    def __init__(self, cid, messaggi, errore=None):
        self.id = cid
        self._messaggi = messaggi  # dal più nuovo al più vecchio, come history()
        self._errore = errore
        self.limite_chiesto = None

    def history(self, limit=None, **kw):
        self.limite_chiesto = limit
        errore, messaggi = self._errore, self._messaggi

        async def _gen():
            if errore:
                raise errore
            for m in messaggi[:limit]:
                yield m

        return _gen()


class _Destinazione(discord.TextChannel):
    def __init__(self, cid, gia_scritto=False, errore=None):
        self.id = cid
        self._gia = gia_scritto
        self._errore = errore

    def history(self, limit=None, **kw):
        errore, gia = self._errore, self._gia

        async def _gen():
            if errore:
                raise errore
            if gia:
                yield object()

        return _gen()


class _Guild:
    def __init__(self, *canali):
        self._c = {c.id: c for c in canali}

    def get_channel(self, cid):
        return self._c.get(cid)


class _Hook:
    def __init__(self, registro, errori=None):
        self.registro = registro
        self.errori = list(errori or [])
        self.in_volo = 0
        self.max_in_volo = 0

    async def send(self, **kw):
        self.in_volo += 1
        self.max_in_volo = max(self.max_in_volo, self.in_volo)
        await asyncio.sleep(0)  # un invio parallelo si intreccerebbe qui
        self.in_volo -= 1
        if self.errori:
            e = self.errori.pop(0)
            if e is not None:
                raise e
        self.registro.append(kw)


@pytest.fixture
def hooks(monkeypatch):
    stato = {"inviati": [], "hook": {}, "errori": {}}

    def finto(url, sessione):
        return stato["hook"].setdefault(url, _Hook(stato["inviati"], stato["errori"].get(url)))

    monkeypatch.setattr(modulo, "_webhook", finto)
    return stato


async def _copia(main, backup, mappa, urls, riepilogo=None, **kw):
    riepilogo = riepilogo or RiepilogoCopia()
    await copia_messaggi(main, backup, mappa, urls, riepilogo, sessione=object(), **kw)
    return riepilogo


@pytest.mark.asyncio
async def test_si_copia_in_ordine_cronologico_uno_alla_volta(hooks):
    src = _Sorgente(1, [_msg("tre"), _msg("due"), _msg("uno")])
    r = await _copia(_Guild(src), _Guild(_Destinazione(11)), {1: 11}, {1: URL_A})

    assert [i["content"] for i in hooks["inviati"]] == ["uno", "due", "tre"]
    assert hooks["hook"][URL_A].max_in_volo == 1
    assert r.messaggi_copiati == 3


@pytest.mark.asyncio
async def test_canali_in_serie_e_ognuno_col_suo_webhook(hooks):
    a = _Sorgente(1, [_msg("a")])
    b = _Sorgente(2, [_msg("b")])
    await _copia(
        _Guild(a, b), _Guild(_Destinazione(11), _Destinazione(12)), {1: 11, 2: 12}, {1: URL_A, 2: URL_B}
    )
    assert hooks["hook"][URL_A] is not hooks["hook"][URL_B]
    assert [i["content"] for i in hooks["inviati"]] == ["a", "b"]


@pytest.mark.asyncio
async def test_ultimi_n_messaggi_e_tetto_predefinito(hooks):
    src = _Sorgente(1, [_msg(str(i)) for i in range(200)])
    await _copia(_Guild(src), _Guild(_Destinazione(11)), {1: 11}, {1: URL_A})
    assert src.limite_chiesto == MESSAGGI_PER_CANALE
    assert len(hooks["inviati"]) == MESSAGGI_PER_CANALE

    hooks["inviati"].clear()
    await _copia(_Guild(src), _Guild(_Destinazione(11)), {1: 11}, {1: URL_A}, limite=3)
    assert [i["content"] for i in hooks["inviati"]] == ["2", "1", "0"]


@pytest.mark.asyncio
async def test_invio_con_autore_senza_menzioni_e_con_allegati(hooks):
    lungo = "x" * 1990
    src = _Sorgente(1, [_msg("ciao @everyone", nome="Discord Bot Clyde", allegati=["https://cdn/f.png"]), _msg(lungo, allegati=["https://cdn/g.png"])])
    await _copia(_Guild(src), _Guild(_Destinazione(11)), {1: 11}, {1: URL_A})

    primo, secondo = hooks["inviati"]  # cronologico: prima il lungo
    assert primo["content"].startswith("x" * 1990) and len(primo["content"]) <= 2000
    assert secondo["content"] == "ciao @everyone\nhttps://cdn/f.png"
    assert secondo["username"] == "disc0rd Bot cl1de"
    assert secondo["avatar_url"].endswith("Discord Bot Clyde.png")
    assert secondo["allowed_mentions"].everyone is False and secondo["allowed_mentions"].users is False
    assert secondo["wait"] is True


@pytest.mark.asyncio
async def test_messaggi_di_sistema_e_vuoti_si_saltano(hooks):
    src = _Sorgente(1, [_msg("ok"), _msg("sistema", tipo=discord.MessageType.new_member), _msg(""), _msg("reply", tipo=discord.MessageType.reply)])
    r = await _copia(_Guild(src), _Guild(_Destinazione(11)), {1: 11}, {1: URL_A})
    assert [i["content"] for i in hooks["inviati"]] == ["reply", "ok"]
    assert r.messaggi_saltati == 2


@pytest.mark.asyncio
async def test_canale_di_backup_gia_con_messaggi_non_si_ricopia(hooks):
    src = _Sorgente(1, [_msg("a")])
    r = await _copia(_Guild(src), _Guild(_Destinazione(11, gia_scritto=True)), {1: 11}, {1: URL_A})
    assert hooks["inviati"] == []
    assert r.canali_messaggi_saltati == 1


@pytest.mark.asyncio
async def test_se_non_si_puo_controllare_la_destinazione_non_si_scrive(hooks):
    src = _Sorgente(1, [_msg("a")])
    dest = _Destinazione(11, errore=_http(discord.Forbidden))
    r = await _copia(_Guild(src), _Guild(dest), {1: 11}, {1: URL_A})
    assert hooks["inviati"] == [] and r.canali_messaggi_saltati == 1


@pytest.mark.asyncio
async def test_canale_senza_webhook_di_mirror_o_non_di_testo_si_salta(hooks):
    src = _Sorgente(1, [_msg("a")])
    voce = SimpleNamespace(id=2)  # non è un TextChannel
    r = await _copia(_Guild(src, voce), _Guild(_Destinazione(11), _Destinazione(12)), {1: 11, 2: 12}, {2: URL_B})
    assert hooks["inviati"] == []
    assert r.canali_messaggi_saltati == 1  # il canale di voce non conta


@pytest.mark.asyncio
async def test_canale_che_il_bot_non_legge_si_salta_e_gli_altri_vanno_avanti(hooks):
    chiuso = _Sorgente(1, [], errore=_http(discord.Forbidden))
    aperto = _Sorgente(2, [_msg("b")])
    r = await _copia(
        _Guild(chiuso, aperto), _Guild(_Destinazione(11), _Destinazione(12)), {1: 11, 2: 12}, {1: URL_A, 2: URL_B}
    )
    assert [i["content"] for i in hooks["inviati"]] == ["b"]
    assert r.canali_messaggi_saltati == 1


@pytest.mark.asyncio
async def test_webhook_sparito_ferma_il_canale_altro_errore_salta_solo_il_messaggio(hooks):
    hooks["errori"][URL_A] = [None, _http(discord.NotFound)]  # il 2º invio trova il webhook cancellato
    hooks["errori"][URL_B] = [_http()]  # il 1º messaggio rifiutato, il resto passa
    a = _Sorgente(1, [_msg("a3"), _msg("a2"), _msg("a1")])
    b = _Sorgente(2, [_msg("b2"), _msg("b1")])
    r = await _copia(
        _Guild(a, b), _Guild(_Destinazione(11), _Destinazione(12)), {1: 11, 2: 12}, {1: URL_A, 2: URL_B}
    )
    assert [i["content"] for i in hooks["inviati"]] == ["a1", "b2"]
    assert r.messaggi_falliti == 1  # solo il rifiuto di B; il webhook sparito di A conta come canale
    assert r.canali_messaggi_saltati == 1  # A abbandonato


@pytest.mark.asyncio
async def test_riassunto_dice_cosa_non_e_stato_copiato():
    from core.backup_orchestrator import riassunto_copia

    assert riassunto_copia(RiepilogoCopia(messaggi_copiati=50)) == ""
    testo = riassunto_copia(RiepilogoCopia(canali_messaggi_saltati=2, messaggi_falliti=3, messaggi_interrotti=True))
    assert "2 canali" in testo and "3 messaggi" in testo and "interrott" in testo


@pytest.mark.asyncio
async def test_popola_copia_i_messaggi_dopo_il_mirror_e_un_errore_non_ferma_il_job(monkeypatch):
    import core.backup_orchestrator as orch

    ordine = []

    async def ok(*a, **k):
        ordine.append("x")
        return {}

    async def mirror(*a, **k):
        ordine.append("mirror")
        return {1: URL_A}

    async def messaggi(main, backup, mappa_canali, urls, riepilogo, **k):
        ordine.append(("messaggi", urls))
        raise RuntimeError("boom")

    for nome in ("clone_roles", "clone_categories_and_channels", "clone_emoji", "clone_stickers", "clone_soundboard", "clone_webhooks"):
        monkeypatch.setattr(orch, nome, ok)
    monkeypatch.setattr(orch, "conta_canali_non_visibili", lambda g: 0)
    monkeypatch.setattr(orch, "create_mirror_webhooks", mirror)
    monkeypatch.setattr(orch, "copia_messaggi", messaggi)

    mappa, riepilogo = await orch.popola_server_backup(SimpleNamespace(id=1), object())

    assert mappa == {1: URL_A}
    assert ordine[-1] == ("messaggi", {1: URL_A}) and "mirror" in ordine
    assert riepilogo.messaggi_interrotti is True

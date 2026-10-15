"""
tests/test_backup_chat.py
=========================
Chat salvate (BKP-026/027): lettura fino a 1000 messaggi, ricarica in ordine
via webhook, allegati come file finché il link vale (BKP-013), messaggi fissati
rifissati (BKP-016), annullo e webhook sparito; anche nella copia iniziale.
Funzioni coperte: BKP-013, BKP-016, BKP-026, BKP-027
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import discord

from core import backup_messages_logic as bm
from core.backup_clone_logic import RiepilogoCopia


class _Resp:
    status = 404
    reason = "x"


def _msg(testo, *, pinned=False, allegati=(), tipo=discord.MessageType.default):
    return SimpleNamespace(
        content=testo, type=tipo, pinned=pinned,
        attachments=list(allegati),
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        author=SimpleNamespace(display_name="Mario", display_avatar=SimpleNamespace(url="https://cdn/a.png")),
    )


class _Canale:
    def __init__(self, messaggi=(), hooks=()):
        self._messaggi = list(messaggi)
        self.hooks = list(hooks)
        self.fissati = []
        self.limite = None

    def history(self, limit=None):
        self.limite = limit
        messaggi = self._messaggi

        async def gen():
            for m in messaggi[:limit]:
                yield m

        return gen()

    def get_partial_message(self, mid):
        fissati = self.fissati

        async def pin():
            fissati.append(mid)

        return SimpleNamespace(pin=pin)

    async def webhooks(self):
        return self.hooks

    async def create_webhook(self, name, reason=None):
        hook = SimpleNamespace(name=name, token="t")
        self.hooks.append(hook)
        return hook


class _Hook:
    def __init__(self, errore_al=None):
        self.inviati = []
        self.errore_al = errore_al

    async def send(self, **kw):
        if self.errore_al is not None and len(self.inviati) == self.errore_al:
            raise discord.NotFound(_Resp(), "webhook sparito")
        self.inviati.append(kw)
        return SimpleNamespace(id=len(self.inviati))


async def _mai(_p, _f, _t):
    return False


async def test_lettura_dal_piu_vecchio_senza_messaggi_di_sistema_e_tetto_1000():
    allegato = SimpleNamespace(filename="f.png", url="https://cdn.discordapp.com/f.png", size=10)
    canale = _Canale([_msg("nuovo", pinned=True), _msg("sistema", tipo=discord.MessageType.new_member),
                      _msg("vecchio", allegati=[allegato])])
    righe = await bm.leggi_chat(canale, 5000)
    assert canale.limite == 1000
    assert [r["contenuto"] for r in righe] == ["vecchio", "nuovo"]
    assert righe[0]["allegati"] == [{"nome": "f.png", "url": "https://cdn.discordapp.com/f.png", "size": 10}]
    assert righe[1]["fissato"] is True


async def test_ricarica_in_ordine_con_file_link_e_fissati():
    scaricati = []

    async def scarica(url, massimo):
        scaricati.append((url, massimo))
        return b"x" if url.endswith("vivo.png") else None  # l'altro link è scaduto

    messaggi = [
        {"autore": "Discord Fan", "contenuto": "uno", "allegati": [
            {"nome": "vivo.png", "url": "https://cdn.discordapp.com/vivo.png", "size": 1},
            {"nome": "morto.png", "url": "https://cdn.discordapp.com/morto.png", "size": 1}]},
        {"autore": "B", "contenuto": "", "allegati": []},
        {"autore": "C", "contenuto": "tre", "fissato": True},
    ]
    hook, canale = _Hook(), _Canale()
    r = await bm.ricarica_chat(messaggi, hook, canale, _mai, scarica)

    assert [i["content"] for i in hook.inviati] == ["uno\nhttps://cdn.discordapp.com/morto.png", "tre"]
    assert hook.inviati[0]["username"] == "disc0rd Fan"  # LIM-27
    assert len(hook.inviati[0]["files"]) == 1 and "files" not in hook.inviati[1]
    assert all(i["wait"] is True for i in hook.inviati)
    assert canale.fissati == [2]
    assert (r.copiati, r.saltati, r.allegati_come_link) == (2, 1, 1)


async def test_annullo_e_webhook_sparito_si_fermano():
    messaggi = [{"autore": "A", "contenuto": str(i)} for i in range(5)]

    async def dopo_due(_p, fatti, _t):
        return fatti > 2

    hook = _Hook()
    r = await bm.ricarica_chat(messaggi, hook, _Canale(), dopo_due, None)
    assert r.annullato and r.copiati == 2

    hook = _Hook(errore_al=1)
    r = await bm.ricarica_chat(messaggi, hook, _Canale(), _mai, None)
    assert (r.copiati, r.falliti) == (1, 4)


async def test_webhook_della_chat_riusato_e_tetto_di_15():
    vecchio = SimpleNamespace(name=bm.NOME_WEBHOOK_CHAT, token="t")
    assert await bm.webhook_chat(_Canale(hooks=[vecchio])) is vecchio
    pieno = _Canale(hooks=[SimpleNamespace(name=f"h{i}", token="t") for i in range(15)])
    assert await bm.webhook_chat(pieno) is None
    nuovo = await bm.webhook_chat(_Canale())
    assert nuovo.name == bm.NOME_WEBHOOK_CHAT


async def test_copia_iniziale_allegati_come_file_e_fissati():
    class _Allegato:
        def __init__(self, url, size):
            self.url, self.size = url, size

        async def to_file(self):
            return f"file:{self.url}"

    piccolo, enorme = _Allegato("https://cdn/p.png", 10), _Allegato("https://cdn/e.zip", 11 * 1024 * 1024)
    assert bm.allegati_come_file([piccolo, enorme]) == [piccolo]
    sorgente = _Canale([_msg("", pinned=True, allegati=[piccolo, enorme])])
    destinazione = _Canale()
    hook = _Hook()
    riepilogo = RiepilogoCopia()
    await bm._copia_canale(sorgente, hook, 10, riepilogo, destinazione)
    assert hook.inviati[0]["files"] == ["file:https://cdn/p.png"]
    assert hook.inviati[0]["content"] == "https://cdn/e.zip"
    assert destinazione.fissati == [1] and riepilogo.messaggi_copiati == 1

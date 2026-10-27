"""
tests/test_backup_mirror_dispatch.py
========================================
Test di BackupMirrorDispatcher (SPEC.md §11.9). Le decisioni (cosa
inoltrare) si provano con _send() sostituita da una finta che registra
le chiamate; l'invio vero (SEC-22) contro un server aiohttp locale che
imita l'endpoint webhook di Discord.
"""

import asyncio

import discord
import pytest

from core.backup_mirror_dispatch import BackupMirrorDispatcher
from core.backup_mirror_logic import MirrorRateLimiter


class _FakeAuthor:
    def __init__(self, bot: bool = False) -> None:
        self.bot = bot
        self.display_name = "Utente Finto"


class _FakeGuild:
    id = 100


class _FakeMessage:
    def __init__(self, channel_id: int, author=None, guild=_FakeGuild(), content: str = "ciao"):
        self.channel = type("_Canale", (), {"id": channel_id})()
        self.author = author or _FakeAuthor()
        self.guild = guild
        self.content = content
        self.attachments = []
        self.type = discord.MessageType.default


class _FakeMirrorRepo:
    def __init__(self, mapping: dict[int, str]) -> None:
        self._mapping = mapping

    async def get_webhook_url(self, channel_id: int) -> str | None:
        return self._mapping.get(channel_id)


class _DispatcherRegistraChiamate(BackupMirrorDispatcher):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.chiamate_send: list[tuple] = []

    async def _send(self, webhook_url: str, message) -> None:
        self.chiamate_send.append((webhook_url, message))


@pytest.mark.asyncio
async def test_messaggio_su_canale_mappato_viene_inoltrato():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)

    inoltrato = await dispatcher.handle_message(_FakeMessage(channel_id=10))
    await dispatcher.svuota()

    assert inoltrato is True
    assert dispatcher.chiamate_send[0][0] == "https://discord.com/api/webhooks/abc"


@pytest.mark.asyncio
async def test_canale_non_mappato_non_viene_inoltrato():
    repo = _FakeMirrorRepo({})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)

    inoltrato = await dispatcher.handle_message(_FakeMessage(channel_id=999))

    assert inoltrato is False
    assert dispatcher.chiamate_send == []


@pytest.mark.asyncio
async def test_messaggio_di_un_bot_non_viene_inoltrato():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)

    messaggio = _FakeMessage(channel_id=10, author=_FakeAuthor(bot=True))
    inoltrato = await dispatcher.handle_message(messaggio)

    assert inoltrato is False


@pytest.mark.asyncio
async def test_messaggio_in_dm_non_viene_inoltrato():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)

    messaggio = _FakeMessage(channel_id=10, guild=None)
    inoltrato = await dispatcher.handle_message(messaggio)

    assert inoltrato is False


@pytest.mark.asyncio
async def test_sui_picchi_si_aspetta_e_si_invia_tutto_in_ordine(monkeypatch):
    import core.backup_mirror_dispatch as modulo

    monkeypatch.setattr(modulo, "PAUSA_RATE_LIMIT", 0.01)
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    limiter = MirrorRateLimiter(max_messages=5, window_seconds=0.15)
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo, rate_limiter=limiter)

    messaggi = [_FakeMessage(channel_id=10, content=str(i)) for i in range(7)]
    risultati = [await dispatcher.handle_message(m) for m in messaggi]
    await asyncio.sleep(0.05)
    assert len(dispatcher.chiamate_send) == 5  # i primi 5 subito
    await dispatcher.svuota()

    assert all(risultati)
    assert [m.content for _, m in dispatcher.chiamate_send] == [str(i) for i in range(7)]


@pytest.mark.asyncio
async def test_un_solo_invio_alla_volta_per_canale():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    in_volo = {"adesso": 0, "massimo": 0}

    class _Lento(BackupMirrorDispatcher):
        async def _send(self, url, message):
            in_volo["adesso"] += 1
            in_volo["massimo"] = max(in_volo["massimo"], in_volo["adesso"])
            await asyncio.sleep(0.01)
            in_volo["adesso"] -= 1

    dispatcher = _Lento(mirror_repo=repo)
    for _ in range(4):
        await dispatcher.handle_message(_FakeMessage(channel_id=10))
    await dispatcher.svuota()
    assert in_volo["massimo"] == 1


@pytest.mark.asyncio
async def test_messaggi_di_sistema_non_si_copiano():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)
    messaggio = _FakeMessage(channel_id=10)
    messaggio.type = discord.MessageType.new_member
    assert await dispatcher.handle_message(messaggio) is False
    assert dispatcher.chiamate_send == []


@pytest.mark.asyncio
async def test_coda_piena_scarta_i_nuovi(monkeypatch):
    import core.backup_mirror_dispatch as modulo

    monkeypatch.setattr(modulo, "MAX_CODA_PER_CANALE", 2)
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)
    risultati = [await dispatcher.handle_message(_FakeMessage(channel_id=10)) for _ in range(3)]
    await dispatcher.svuota()
    assert risultati == [True, True, False]


# ---------------------------------------------------------------------
# SEC-22: l'invio vero (_send non sostituito) contro un server locale
# che imita l'endpoint webhook di Discord e registra ciò che riceve.
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_il_mirror_non_trasforma_everyone_in_un_ping_vero(monkeypatch):
    import discord
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from discord.webhook.async_ import Route

    from tests.support.discord_fakes import fake_message

    ricevuti: list[dict] = []

    async def handler(request):
        ricevuti.append(await request.json())
        return web.Response(status=204)

    app = web.Application()
    app.router.add_post("/api/v10/webhooks/{webhook_id}/{token}", handler)
    server = TestServer(app)
    await server.start_server()
    # discord.py manda sempre a discord.com: per il test la base punta al server locale.
    monkeypatch.setattr(Route, "BASE", str(server.make_url("/api/v10")))

    messaggio = fake_message(content="@everyone guardate qui <@&123456789012345678>")
    messaggio.channel.id = 10
    messaggio.author.bot = False
    messaggio.author.display_name = "Utente"
    messaggio.author.display_avatar.url = "https://cdn.discordapp.com/embed/avatars/0.png"
    messaggio.attachments = []
    messaggio.type = discord.MessageType.default
    # discord.py accetta solo token di almeno 60 caratteri: questo è finto.
    url_webhook = "https://discord.com/api/webhooks/123456789012345678/" + "token-finto-" * 6
    repo = _FakeMirrorRepo({10: url_webhook})
    dispatcher = BackupMirrorDispatcher(mirror_repo=repo)
    try:
        assert await dispatcher.handle_message(messaggio) is True
        await dispatcher.svuota()
    finally:
        await dispatcher.close()
        await server.close()

    assert len(ricevuti) == 1
    assert "@everyone" in ricevuti[0]["content"]  # il testo resta, ma...
    # ...nessuna menzione viene risolta: né @everyone/@here, né ruoli, né utenti.
    assert ricevuti[0]["allowed_mentions"] == discord.AllowedMentions.none().to_dict()
    assert ricevuti[0]["allowed_mentions"] == {"parse": []}


@pytest.mark.asyncio
async def test_il_mirror_copia_il_messaggio_di_un_utente_con_discord_nel_nome(monkeypatch):
    """M 12.7 (LIM-27): il nome mittente non contiene "discord" né "clyde"."""
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from discord.webhook.async_ import Route

    from tests.support.discord_fakes import fake_message

    ricevuti: list[dict] = []

    async def handler(request):
        ricevuti.append(await request.json())
        return web.Response(status=204)

    app = web.Application()
    app.router.add_post("/api/v10/webhooks/{webhook_id}/{token}", handler)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(Route, "BASE", str(server.make_url("/api/v10")))

    messaggio = fake_message(content="ciao")
    messaggio.channel.id = 10
    messaggio.author.bot = False
    messaggio.author.display_name = "Discord Fan"
    messaggio.author.display_avatar.url = "https://cdn.discordapp.com/embed/avatars/0.png"
    messaggio.attachments = []
    messaggio.type = discord.MessageType.default
    url_webhook = "https://discord.com/api/webhooks/123456789012345678/" + "token-finto-" * 6
    dispatcher = BackupMirrorDispatcher(mirror_repo=_FakeMirrorRepo({10: url_webhook}))
    try:
        assert await dispatcher.handle_message(messaggio) is True
        await dispatcher.svuota()
    finally:
        await dispatcher.close()
        await server.close()

    assert len(ricevuti) == 1
    assert "discord" not in ricevuti[0]["username"].lower()


@pytest.mark.asyncio
async def test_gli_allegati_vanno_come_file_entro_10_mib(monkeypatch):
    import core.backup_mirror_dispatch as modulo

    class _Allegato:
        def __init__(self, nome, size):
            self.filename, self.size, self.url = nome, size, f"https://cdn.discordapp.com/{nome}"

        async def to_file(self):
            return discord.File(__import__("io").BytesIO(b"x"), filename=self.filename)

    inviati = []

    class _Hook:
        async def send(self, **kw):
            inviati.append(kw)

    monkeypatch.setattr(modulo.discord.Webhook, "from_url", staticmethod(lambda url, session: _Hook()))
    messaggio = _FakeMessage(channel_id=10, content="guarda")
    messaggio.author.display_avatar = type("_A", (), {"url": "https://cdn.discordapp.com/a.png"})()
    messaggio.attachments = [_Allegato("piccolo.png", 1000), _Allegato("enorme.zip", 11 * 1024 * 1024)]
    dispatcher = BackupMirrorDispatcher(mirror_repo=_FakeMirrorRepo({10: "https://x/y"}))
    try:
        await dispatcher.handle_message(messaggio)
        await dispatcher.svuota()
    finally:
        await dispatcher.close()

    assert [f.filename for f in inviati[0]["files"]] == ["piccolo.png"]
    assert "enorme.zip" in inviati[0]["content"]  # il troppo grande resta come link

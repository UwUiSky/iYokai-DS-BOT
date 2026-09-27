"""
tests/test_entertainment_image_commands.py
================================================
Test del comportamento REALE di /fun grayscale|invert|blur|pixelate|
meme (SPEC.md §16.2/§16.3) — priorità allegato > utente menzionato >
autore, e validazione di tipo/dimensione dell'allegato.
"""

import io

import discord
import pytest
from PIL import Image

from cogs.fun.entertainment import EntertainmentCog, MODULE_FUN
from core.database import Database


def _bytes_immagine_valida() -> bytes:
    img = Image.new("RGB", (50, 50), (10, 20, 30))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_files: list = []

    async def send_message(self, content: str = None, file=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if file is not None:
            self.sent_files.append(file)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeAvatarAsset:
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def read(self) -> bytes:
        return self._content


class _FakeMember:
    def __init__(self, avatar_content: bytes) -> None:
        self.display_avatar = _FakeAvatarAsset(avatar_content)


class _FakeAttachment:
    def __init__(self, content: bytes, content_type: str = "image/png", size: int | None = None) -> None:
        self._content = content
        self.content_type = content_type
        self.size = size if size is not None else len(content)

    async def read(self) -> bytes:
        return self._content


class _FakeInteraction:
    def __init__(self, guild_id: int | None, avatar_content: bytes = b"avatar-autore") -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.response = _FakeResponse()
        self.user = _FakeMember(avatar_content)


@pytest.mark.asyncio
async def test_grayscale_modulo_disattivato_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000001
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.grayscale.callback(cog, interaction, image=None, utente=None)

        assert "non è attivo" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000001")
        await database.close()


@pytest.mark.asyncio
async def test_grayscale_senza_allegato_usa_avatar_autore(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000002
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id, avatar_content=_bytes_immagine_valida())

        await cog.grayscale.callback(cog, interaction, image=None, utente=None)

        assert len(interaction.response.sent_files) == 1
        assert interaction.response.sent_files[0].filename == "grayscale.png"
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000002")
        await database.close()


@pytest.mark.asyncio
async def test_grayscale_con_allegato_usa_l_allegato_non_l_avatar(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000003
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        # Avatar "non valido" apposta: se venisse usato per errore,
        # apply_grayscale restituirebbe None e il test lo scoprirebbe.
        interaction = _FakeInteraction(guild_id, avatar_content=b"non e' un'immagine")
        allegato = _FakeAttachment(_bytes_immagine_valida())

        await cog.grayscale.callback(cog, interaction, image=allegato, utente=None)

        assert len(interaction.response.sent_files) == 1
        assert interaction.response.sent_messages == []
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000003")
        await database.close()


@pytest.mark.asyncio
async def test_grayscale_con_utente_menzionato_usa_il_suo_avatar(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000004
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id, avatar_content=b"non e' un'immagine")
        altro_utente = _FakeMember(_bytes_immagine_valida())

        await cog.grayscale.callback(cog, interaction, image=None, utente=altro_utente)

        assert len(interaction.response.sent_files) == 1
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000004")
        await database.close()


@pytest.mark.asyncio
async def test_allegato_non_immagine_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000005
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)
        allegato = _FakeAttachment(b"pdf-finto", content_type="application/pdf")

        await cog.grayscale.callback(cog, interaction, image=allegato, utente=None)

        assert "non è un'immagine" in interaction.response.sent_messages[0]
        assert interaction.response.sent_files == []
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000005")
        await database.close()


@pytest.mark.asyncio
async def test_allegato_troppo_grande_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000006
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)
        allegato = _FakeAttachment(b"x", content_type="image/png", size=999_999_999)

        await cog.grayscale.callback(cog, interaction, image=allegato, utente=None)

        assert "troppo grande" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000006")
        await database.close()


@pytest.mark.asyncio
async def test_invert_funziona(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000007
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id, avatar_content=_bytes_immagine_valida())

        await cog.invert.callback(cog, interaction, image=None, utente=None)

        assert len(interaction.response.sent_files) == 1
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000007")
        await database.close()


@pytest.mark.asyncio
async def test_blur_funziona(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000008
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id, avatar_content=_bytes_immagine_valida())

        await cog.blur.callback(cog, interaction, image=None, utente=None, raggio=5)

        assert len(interaction.response.sent_files) == 1
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000008")
        await database.close()


@pytest.mark.asyncio
async def test_pixelate_funziona(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000009
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id, avatar_content=_bytes_immagine_valida())

        await cog.pixelate.callback(cog, interaction, image=None, utente=None, dimensione_blocco=8)

        assert len(interaction.response.sent_files) == 1
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000009")
        await database.close()


@pytest.mark.asyncio
async def test_meme_senza_testo_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000010
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.meme.callback(
            cog, interaction, top_text="", bottom_text="", image=None, utente=None
        )

        assert "almeno un testo" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000010")
        await database.close()


@pytest.mark.asyncio
async def test_meme_con_testo_funziona(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 830000011
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id, avatar_content=_bytes_immagine_valida())

        await cog.meme.callback(
            cog, interaction, top_text="Ciao", bottom_text="Mondo", image=None, utente=None
        )

        assert len(interaction.response.sent_files) == 1
        assert interaction.response.sent_files[0].filename == "meme.png"
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 830000011")
        await database.close()


@pytest.mark.asyncio
async def test_grayscale_fuori_da_un_server_rifiuta():
    cog = EntertainmentCog(bot=None)
    interaction = _FakeInteraction(guild_id=None)

    await cog.grayscale.callback(cog, interaction, image=None, utente=None)

    assert "solo dentro un server" in interaction.response.sent_messages[0]

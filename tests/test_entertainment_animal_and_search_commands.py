"""
tests/test_entertainment_animal_and_search_commands.py
=============================================================
Test del comportamento REALE di /fun animal (§16.4) e
/fun search-image (§16.9) — fetcher HTTP sostituiti con fake
in-memory (nessuna rete coinvolta), stesso schema di monkeypatch di
tests/test_feed_alerts_behavior.py per il config env-gated.
"""

import random

import pytest

from cogs.fun.entertainment import EntertainmentCog, MODULE_FUN
from core.database import Database


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list = []

    async def send_message(self, content: str = None, embed=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeInteraction:
    def __init__(self, guild_id: int | None) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.response = _FakeResponse()


class _FakeChoice:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


class _FakeAnimalFetcher:
    def __init__(self, url: str | None) -> None:
        self._url = url
        self.specie_richiesta = None

    async def fetch_image_url(self, species: str) -> str | None:
        self.specie_richiesta = species
        return self._url


class _FakeImageSearchFetcher:
    def __init__(self, url: str | None) -> None:
        self._url = url
        self.ultima_chiave = None
        self.ultima_query = None

    async def fetch_image_url(self, api_key: str, query: str, rng: random.Random) -> str | None:
        self.ultima_chiave = api_key
        self.ultima_query = query
        return self._url


class _ConfigConChiave:
    PIXABAY_API_KEY = "chiave-finta"


class _ConfigSenzaChiave:
    PIXABAY_API_KEY = ""


@pytest.mark.asyncio
async def test_animal_modulo_disattivato_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 840000001
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

        import cogs.fun.entertainment as modulo

        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.animal.callback(cog, interaction, specie=_FakeChoice("Cane", "dog"))

        assert "non è attivo" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 840000001")
        await database.close()


@pytest.mark.asyncio
async def test_animal_con_url_valido_manda_un_embed(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 840000002
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo

        monkeypatch.setattr(modulo, "db", database)
        fetcher_finto = _FakeAnimalFetcher("https://images.dog.ceo/x.jpg")
        monkeypatch.setattr(modulo, "animal_fetcher", fetcher_finto)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.animal.callback(cog, interaction, specie=_FakeChoice("Cane", "dog"))

        assert fetcher_finto.specie_richiesta == "dog"
        assert len(interaction.response.sent_embeds) == 1
        assert interaction.response.sent_embeds[0].image.url == "https://images.dog.ceo/x.jpg"
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 840000002")
        await database.close()


@pytest.mark.asyncio
async def test_animal_senza_url_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 840000003
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo

        monkeypatch.setattr(modulo, "db", database)
        monkeypatch.setattr(modulo, "animal_fetcher", _FakeAnimalFetcher(None))

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.animal.callback(cog, interaction, specie=_FakeChoice("Volpe", "fox"))

        assert "Non sono riuscito" in interaction.response.sent_messages[0]
        assert interaction.response.sent_embeds == []
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 840000003")
        await database.close()


@pytest.mark.asyncio
async def test_search_image_modulo_disattivato_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 840000004
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

        import cogs.fun.entertainment as modulo

        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.search_image.callback(cog, interaction, query="gatto")

        assert "non è attivo" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 840000004")
        await database.close()


@pytest.mark.asyncio
async def test_search_image_senza_chiave_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 840000005
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo

        monkeypatch.setattr(modulo, "db", database)
        monkeypatch.setattr(modulo, "config", _ConfigSenzaChiave())
        fetcher_finto = _FakeImageSearchFetcher("https://pixabay.com/a.jpg")
        monkeypatch.setattr(modulo, "image_search_fetcher", fetcher_finto)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.search_image.callback(cog, interaction, query="gatto")

        assert "PIXABAY_API_KEY" in interaction.response.sent_messages[0]
        assert fetcher_finto.ultima_query is None
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 840000005")
        await database.close()


@pytest.mark.asyncio
async def test_search_image_con_chiave_e_risultato_manda_un_embed(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 840000006
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo

        monkeypatch.setattr(modulo, "db", database)
        monkeypatch.setattr(modulo, "config", _ConfigConChiave())
        fetcher_finto = _FakeImageSearchFetcher("https://pixabay.com/a.jpg")
        monkeypatch.setattr(modulo, "image_search_fetcher", fetcher_finto)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.search_image.callback(cog, interaction, query="gatto")

        assert fetcher_finto.ultima_chiave == "chiave-finta"
        assert fetcher_finto.ultima_query == "gatto"
        assert len(interaction.response.sent_embeds) == 1
        assert interaction.response.sent_embeds[0].image.url == "https://pixabay.com/a.jpg"
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 840000006")
        await database.close()


@pytest.mark.asyncio
async def test_search_image_con_chiave_ma_senza_risultati_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 840000007
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo

        monkeypatch.setattr(modulo, "db", database)
        monkeypatch.setattr(modulo, "config", _ConfigConChiave())
        monkeypatch.setattr(modulo, "image_search_fetcher", _FakeImageSearchFetcher(None))

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.search_image.callback(cog, interaction, query="xyzxyz-inesistente")

        assert "Nessun risultato" in interaction.response.sent_messages[0]
        assert interaction.response.sent_embeds == []
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 840000007")
        await database.close()


@pytest.mark.asyncio
async def test_animal_fuori_da_un_server_rifiuta():
    cog = EntertainmentCog(bot=None)
    interaction = _FakeInteraction(guild_id=None)

    await cog.animal.callback(cog, interaction, specie=_FakeChoice("Cane", "dog"))

    assert "solo dentro un server" in interaction.response.sent_messages[0]

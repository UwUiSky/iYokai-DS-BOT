"""
tests/test_entertainment_cog_behavior.py
=============================================
Test del comportamento REALE di /fun coinflip|dice|rps|8ball|joke|
quote|fact — stesso schema di tests/test_ship_rate_behavior.py.
"""

import pytest

from cogs.fun.entertainment import EntertainmentCog, MODULE_FUN
from core.classic_entertainment_logic import FACTS, JOKES, QUOTES
from core.database import Database
from core.minigames_logic import EIGHT_BALL_ANSWERS


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
    def __init__(self, value: str) -> None:
        self.value = value


@pytest.mark.asyncio
async def test_coinflip_modulo_disattivato_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000001
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.coinflip.callback(cog, interaction)

        assert "non è attivo" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000001")
        await database.close()


@pytest.mark.asyncio
async def test_coinflip_modulo_attivo_risponde_testa_o_croce(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000002
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.coinflip.callback(cog, interaction)

        messaggio = interaction.response.sent_messages[0]
        assert "TESTA" in messaggio or "CROCE" in messaggio
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000002")
        await database.close()


@pytest.mark.asyncio
async def test_dice_fuori_range_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000003
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.dice.callback(cog, interaction, sides=1)

        assert "tra 2 e 1000" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000003")
        await database.close()


@pytest.mark.asyncio
async def test_dice_valore_valido_dentro_i_limiti(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000004
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.dice.callback(cog, interaction, sides=20)

        messaggio = interaction.response.sent_messages[0]
        assert "d20" in messaggio
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000004")
        await database.close()


@pytest.mark.asyncio
async def test_rps_risponde_con_esito_valido(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000005
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.rps.callback(cog, interaction, scelta=_FakeChoice("sasso"))

        messaggio = interaction.response.sent_messages[0]
        assert "vinto" in messaggio or "perso" in messaggio or "Pareggio" in messaggio
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000005")
        await database.close()


@pytest.mark.asyncio
async def test_8ball_risponde_con_embed(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000006
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.eight_ball.callback(cog, interaction, domanda="Sarà una bella giornata?")

        assert len(interaction.response.sent_embeds) == 1
        descrizione = interaction.response.sent_embeds[0].description
        assert "Sarà una bella giornata?" in descrizione
        assert any(risposta in descrizione for risposta in EIGHT_BALL_ANSWERS)
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000006")
        await database.close()


@pytest.mark.asyncio
async def test_joke_risponde_con_una_barzelletta_valida(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000007
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.joke.callback(cog, interaction)

        messaggio = interaction.response.sent_messages[0]
        assert any(barzelletta in messaggio for barzelletta in JOKES)
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000007")
        await database.close()


@pytest.mark.asyncio
async def test_quote_risponde_con_una_citazione_valida(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000008
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.quote.callback(cog, interaction)

        messaggio = interaction.response.sent_messages[0]
        assert any(citazione in messaggio for citazione in QUOTES)
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000008")
        await database.close()


@pytest.mark.asyncio
async def test_fact_risponde_con_una_curiosita_valida(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 810000009
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.entertainment as modulo
        monkeypatch.setattr(modulo, "db", database)

        cog = EntertainmentCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.fact.callback(cog, interaction)

        messaggio = interaction.response.sent_messages[0]
        assert any(curiosita in messaggio for curiosita in FACTS)
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 810000009")
        await database.close()


@pytest.mark.asyncio
async def test_coinflip_fuori_da_un_server_rifiuta():
    cog = EntertainmentCog(bot=None)
    interaction = _FakeInteraction(guild_id=None)

    await cog.coinflip.callback(cog, interaction)

    assert "solo dentro un server" in interaction.response.sent_messages[0]

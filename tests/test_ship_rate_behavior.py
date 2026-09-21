"""
tests/test_ship_rate_behavior.py
====================================
Test del comportamento REALE di /ship e /rate — non solo che il cog
carica, contro PostgreSQL reale per il controllo del modulo attivo.
"""

import re

import discord
import pytest

from cogs.fun.ship_rate import MODULE_FUN, ShipRateCog
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


class _FakeMember:
    def __init__(self, user_id: int, display_name: str) -> None:
        self.id = user_id
        self.display_name = display_name


class _FakeInteraction:
    def __init__(self, guild_id: int | None) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.response = _FakeResponse()


@pytest.mark.asyncio
async def test_ship_modulo_disattivato_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 800000001
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

        import cogs.fun.ship_rate as ship_rate_module
        monkeypatch.setattr(ship_rate_module, "db", database)

        cog = ShipRateCog(bot=None)
        interaction = _FakeInteraction(guild_id)
        utente1 = _FakeMember(1, "Mario")
        utente2 = _FakeMember(2, "Luigi")

        await cog.ship.callback(cog, interaction, user1=utente1, user2=utente2)

        assert "non è attivo" in interaction.response.sent_messages[0]
        assert interaction.response.sent_embeds == []
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 800000001")
        await database.close()


@pytest.mark.asyncio
async def test_ship_modulo_attivo_mostra_percentuale_reale(monkeypatch):
    from core.fun_logic import compute_ship_percentage

    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 800000002
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.ship_rate as ship_rate_module
        monkeypatch.setattr(ship_rate_module, "db", database)

        cog = ShipRateCog(bot=None)
        interaction = _FakeInteraction(guild_id)
        utente1 = _FakeMember(100, "Mario")
        utente2 = _FakeMember(200, "Luigi")

        await cog.ship.callback(cog, interaction, user1=utente1, user2=utente2)

        assert len(interaction.response.sent_embeds) == 1
        embed = interaction.response.sent_embeds[0]
        percentuale_attesa = compute_ship_percentage(100, 200)
        assert f"{percentuale_attesa}%" in embed.description
        assert "Mario" in embed.description and "Luigi" in embed.description
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 800000002")
        await database.close()


@pytest.mark.asyncio
async def test_ship_stesso_risultato_indipendentemente_dall_ordine(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 800000003
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.ship_rate as ship_rate_module
        monkeypatch.setattr(ship_rate_module, "db", database)

        cog = ShipRateCog(bot=None)
        utente1 = _FakeMember(100, "Mario")
        utente2 = _FakeMember(200, "Luigi")

        interazione_a = _FakeInteraction(guild_id)
        await cog.ship.callback(cog, interazione_a, user1=utente1, user2=utente2)

        interazione_b = _FakeInteraction(guild_id)
        await cog.ship.callback(cog, interazione_b, user1=utente2, user2=utente1)

        descrizione_a = interazione_a.response.sent_embeds[0].description
        descrizione_b = interazione_b.response.sent_embeds[0].description
        # Stessa percentuale in entrambi i versi (anche se il nome
        # mostrato per primo cambia, il numero deve essere identico).
        p_a = re.search(r"(\d+)%", descrizione_a).group(1)
        p_b = re.search(r"(\d+)%", descrizione_b).group(1)
        assert p_a == p_b
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 800000003")
        await database.close()


@pytest.mark.asyncio
async def test_rate_modulo_attivo_mostra_punteggio_reale(monkeypatch):
    from core.fun_logic import compute_rate_score

    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 800000004
        await database.set_module_active_for_guild(guild_id, MODULE_FUN, True)

        import cogs.fun.ship_rate as ship_rate_module
        monkeypatch.setattr(ship_rate_module, "db", database)

        cog = ShipRateCog(bot=None)
        interaction = _FakeInteraction(guild_id)

        await cog.rate.callback(cog, interaction, thing="la pizza con l'ananas")

        assert len(interaction.response.sent_embeds) == 1
        embed = interaction.response.sent_embeds[0]
        punteggio_atteso = compute_rate_score("la pizza con l'ananas")
        assert f"{punteggio_atteso}/10" in embed.description
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 800000004")
        await database.close()


@pytest.mark.asyncio
async def test_rate_fuori_da_un_server_rifiuta():
    cog = ShipRateCog(bot=None)
    interaction = _FakeInteraction(guild_id=None)

    await cog.rate.callback(cog, interaction, thing="qualcosa")

    assert "solo dentro un server" in interaction.response.sent_messages[0]

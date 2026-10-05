"""
tests/test_leveling_limiti.py
=============================
LIM-18, M 9.12: i testi liberi dei comandi di economia e clan hanno una
lunghezza massima, e le liste che crescono con i dati (negozio, ruoli
premio, membri di una gilda) si sfogliano a pagine senza mai superare
i limiti di un embed. Database vero.
Funzioni coperte: SPEC §15.4, §15.5, §15.13, §15.14
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import LevelingCog
from core.repositories.guild_clan_repo import guild_clan_repo
from core.repositories.level_reward_repo import level_reward_repo
from core.repositories.shop_repo import shop_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

GUILD_ID = 100
LIMITE_DESCRIZIONE_EMBED = 4096
LIMITE_TITOLO_EMBED = 256


@pytest.fixture
async def cog(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    c = LevelingCog(bot=None)
    c.cog_unload()
    return c


def _interazione(user_id: int = 1):
    return fake_interaction(guild=fake_guild(GUILD_ID), user=fake_member(user_id))


def _inviato(interazione) -> dict:
    """Gli argomenti con nome della (sola) risposta mandata."""
    return interazione.response.send_message.await_args.kwargs


# ----------------------------------------------------------------------
# Testi liberi: lunghezza massima dichiarata a Discord
# ----------------------------------------------------------------------
LUNGHEZZE_ATTESE = {
    ("clan crea", "name"): 64,
    ("clan crea", "tag"): 5,
    ("clan info", "tag"): 5,
    ("clan membri", "tag"): 5,
    ("clan compra-canale", "nome"): 100,
    ("clan tesoreria trasferisci", "tag_destinazione"): 5,
    ("shop add-item", "name"): 80,
    ("shop add-item", "description"): 200,
    ("giveaway", "prize"): 200,
}


@pytest.mark.asyncio
async def test_i_testi_liberi_hanno_la_lunghezza_massima():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = LevelingCog(bot)
    cog.cog_unload()
    await bot.add_cog(cog)

    trovate = {}
    for comando in bot.tree.walk_commands():
        if not isinstance(comando, app_commands.Command):
            continue
        for opzione in comando.to_dict(bot.tree)["options"]:
            chiave = (comando.qualified_name, opzione["name"])
            if chiave in LUNGHEZZE_ATTESE:
                trovate[chiave] = opzione.get("max_length")
    await bot.close()

    assert trovate == LUNGHEZZE_ATTESE


@pytest.mark.asyncio
async def test_nessun_testo_libero_senza_lunghezza_massima():
    """Ogni opzione di tipo testo del cog dichiara max_length."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = LevelingCog(bot)
    cog.cog_unload()
    await bot.add_cog(cog)

    senza_limite = []
    for comando in bot.tree.walk_commands():
        if not isinstance(comando, app_commands.Command):
            continue
        for opzione in comando.to_dict(bot.tree)["options"]:
            e_testo = opzione["type"] == discord.AppCommandOptionType.string.value
            if e_testo and not opzione.get("choices") and "max_length" not in opzione:
                senza_limite.append((comando.qualified_name, opzione["name"]))
    await bot.close()

    assert senza_limite == []


# ----------------------------------------------------------------------
# Liste a pagine
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_negozio_con_molti_oggetti_si_sfoglia_a_pagine(cog):
    for numero in range(35):
        # Nomi e descrizioni lunghi, come potevano essere salvati prima
        # che esistesse il limite sul comando.
        await shop_repo.add_item(
            GUILD_ID, name=f"Oggetto {numero:02d} " + "n" * 300, price=numero + 1,
            description="d" * 900,
        )
    interazione = _interazione()

    await cog.shop_list.callback(cog, interazione)

    inviato = _inviato(interazione)
    prima_pagina = inviato["embed"]
    assert len(prima_pagina.description) <= LIMITE_DESCRIZIONE_EMBED
    assert "Oggetto 00" in prima_pagina.description
    assert "Oggetto 34" not in prima_pagina.description
    assert "1/4" in prima_pagina.footer.text
    view = inviato["view"]

    # Avanti di una pagina: stesso messaggio, pagina 2.
    clic = _interazione()
    await view.avanti.callback(clic)
    seconda_pagina = clic.response.edit_message.await_args.kwargs["embed"]
    assert "2/4" in seconda_pagina.footer.text
    assert "Oggetto 10" in seconda_pagina.description
    assert len(seconda_pagina.description) <= LIMITE_DESCRIZIONE_EMBED
    view.stop()


@pytest.mark.asyncio
async def test_le_pagine_le_sfoglia_solo_chi_ha_usato_il_comando(cog):
    for numero in range(15):
        await shop_repo.add_item(GUILD_ID, name=f"Oggetto {numero}", price=numero + 1)
    interazione = _interazione(user_id=1)
    await cog.shop_list.callback(cog, interazione)
    view = _inviato(interazione)["view"]

    estraneo = _interazione(user_id=2)
    permesso = await view.interaction_check(estraneo)

    assert permesso is False
    assert estraneo.response.send_message.await_args.kwargs["ephemeral"] is True
    view.stop()


@pytest.mark.asyncio
async def test_negozio_corto_resta_senza_bottoni(cog):
    await shop_repo.add_item(GUILD_ID, name="Solo", price=1)
    interazione = _interazione()

    await cog.shop_list.callback(cog, interazione)

    assert "view" not in _inviato(interazione)


@pytest.mark.asyncio
async def test_ruoli_premio_numerosi_si_sfogliano_a_pagine(cog):
    for livello in range(1, 121):
        await level_reward_repo.add_reward(GUILD_ID, level_threshold=livello, role_id=1000 + livello)
    interazione = _interazione()

    await cog.level_roles_list.callback(cog, interazione)

    inviato = _inviato(interazione)
    assert len(inviato["embed"].description) <= LIMITE_DESCRIZIONE_EMBED
    assert "livello **1** " in inviato["embed"].description
    assert "livello **120** " not in inviato["embed"].description
    assert inviato["ephemeral"] is True
    inviato["view"].stop()


@pytest.mark.asyncio
async def test_membri_di_una_gilda_grande_si_sfogliano_a_pagine(cog):
    clan_id = await guild_clan_repo.create_clan(
        GUILD_ID, tag="ABC", name="Grande", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
        max_members=999,
    )
    for user_id in range(2, 302):
        await guild_clan_repo.add_member(clan_id, user_id)
    interazione = _interazione()

    await cog.clan_membri.callback(cog, interazione, tag=None)

    inviato = _inviato(interazione)
    assert len(inviato["embed"].description) <= LIMITE_DESCRIZIONE_EMBED
    assert "<@1>" in inviato["embed"].description
    assert "<@301>" not in inviato["embed"].description
    inviato["view"].stop()


@pytest.mark.asyncio
async def test_gilda_con_nome_lunghissimo_non_rompe_clan_info(cog):
    # Un nome salvato prima che esistesse il limite di 64 caratteri.
    await guild_clan_repo.create_clan(
        GUILD_ID, tag="ABC", name="N" * 400, owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    interazione = _interazione()

    await cog.clan_info.callback(cog, interazione, tag=None)

    assert len(_inviato(interazione)["embed"].title) <= LIMITE_TITOLO_EMBED
    altra = _interazione()
    await cog.clan_membri.callback(cog, altra, tag=None)
    assert len(_inviato(altra)["embed"].title) <= LIMITE_TITOLO_EMBED


@pytest.mark.asyncio
async def test_migrazione_0016_accorcia_i_testi_salvati_prima_del_limite(clean_db):
    from pathlib import Path

    import cogs.leveling.leveling as leveling_module
    from core.repositories.giveaway_repo import GiveawayRepository
    from core.repositories.guild_clan_repo import GuildClanRepository
    from core.repositories.shop_repo import ShopRepository

    sql = (
        Path(leveling_module.__file__).parents[2]
        / "core" / "migrations" / "0016_testi_liberi_entro_i_limiti.sql"
    ).read_text(encoding="utf-8")
    tra_un_giorno = datetime.now(timezone.utc) + timedelta(hours=24)
    clan_id = await GuildClanRepository(lambda: clean_db).create_clan(
        GUILD_ID, tag="ABC", name="N" * 400, owner_id=1, officialize_deadline=tra_un_giorno
    )
    corto_id = await GuildClanRepository(lambda: clean_db).create_clan(
        GUILD_ID, tag="XYZ", name="Nome corto", owner_id=2, officialize_deadline=tra_un_giorno
    )
    item_id = await ShopRepository(lambda: clean_db).add_item(
        GUILD_ID, name="O" * 300, price=1, description="D" * 900
    )
    giveaway_id = await GiveawayRepository(lambda: clean_db).create_giveaway(
        GUILD_ID, 5, "P" * 1000, 1, 0, None, tra_un_giorno, 1
    )

    await clean_db.execute(sql)

    assert await clean_db.fetchval("SELECT name FROM clans WHERE id = $1", clan_id) == "N" * 64
    assert await clean_db.fetchval("SELECT name FROM clans WHERE id = $1", corto_id) == "Nome corto"
    oggetto = await clean_db.fetchrow("SELECT name, description FROM shop_items WHERE id = $1", item_id)
    assert (oggetto["name"], oggetto["description"]) == ("O" * 80, "D" * 200)
    assert await clean_db.fetchval(
        "SELECT prize FROM giveaways WHERE id = $1", giveaway_id
    ) == "P" * 200

"""
tests/test_case_system_limiti.py
================================
/modcase history, /modcase view e /modnote list restano dentro i
limiti di un embed (LIM-8): descrizione entro 4096, campo entro 1024,
con "…e altri N" quando non ci sta tutto. /modnote add dichiara la
lunghezza massima della nota.

Database vero (clean_db): le note e i casi li scrive il codice di
produzione (comando /modnote add e repository delle sanzioni).
"""

import discord
import pytest
from discord.ext import commands

from cogs.moderation._shared import MODULE_CASE_SYSTEM
from cogs.moderation.case_system import ModerationCaseSystemCog
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_interaction, fake_member

ID_SERVER = 100
ID_UTENTE = 20


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_CASE_SYSTEM, True)
    yield
    database_module.db._modules_cache.clear()


def _interazione():
    interazione = fake_interaction()
    interazione.guild.id = ID_SERVER
    return interazione


def _embed_valido(embed: discord.Embed) -> None:
    assert len(embed.description or "") <= 4096
    assert len(embed.title or "") <= 256
    assert len(embed.fields) <= 25
    for campo in embed.fields:
        assert 1 <= len(campo.value) <= 1024
    assert len(embed) <= 6000


async def test_modnote_add_dichiara_la_lunghezza_massima():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot.add_cog(ModerationCaseSystemCog(bot))

    comando = bot.tree.get_command("modnote").get_command("add")
    opzioni = {o["name"]: o for o in comando.to_dict(bot.tree)["options"]}

    assert opzioni["note"]["min_length"] == 1
    assert opzioni["note"]["max_length"] == 1000


async def test_venti_note_lunghe_un_solo_embed_valido():
    cog = ModerationCaseSystemCog(bot=None)
    membro = fake_member(ID_UTENTE)
    for numero in range(20):
        await cog.note_add.callback(cog, _interazione(), membro, f"{numero:02d}" + "n" * 998)

    interazione = _interazione()
    await cog.note_list.callback(cog, interazione, membro)

    interazione.response.send_message.assert_awaited_once()
    embed = interazione.response.send_message.call_args.kwargs["embed"]
    _embed_valido(embed)
    # Si vedono le più recenti e si dice quante restano fuori.
    assert "19" + "n" * 10 in embed.description
    assert "…e altr" in embed.description


async def test_storico_con_motivi_lunghi_un_solo_embed_valido():
    """Casi vecchi o scritti da altri moduli possono avere motivi oltre 512."""
    for numero in range(10):
        await moderation_repo.create_case(
            guild_id=ID_SERVER,
            user_id=ID_UTENTE,
            moderator_id=1,
            action_type="warn",
            reason="m" * 2000,
        )
    cog = ModerationCaseSystemCog(bot=None)
    membro = fake_member(ID_UTENTE)
    membro.display_name = "utente"
    membro.display_avatar.url = "https://cdn.discordapp.com/embed/avatars/0.png"

    interazione = _interazione()
    await cog.history.callback(cog, interazione, membro)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    _embed_valido(embed)
    assert "#10" in embed.description


async def test_dettaglio_di_un_caso_con_motivo_lungo_embed_valido():
    numero = await moderation_repo.create_case(
        guild_id=ID_SERVER,
        user_id=ID_UTENTE,
        moderator_id=1,
        action_type="ban",
        reason="m" * 2000,
    )
    cog = ModerationCaseSystemCog(bot=None)

    interazione = _interazione()
    await cog.view.callback(cog, interazione, numero)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    _embed_valido(embed)
    motivo = next(campo for campo in embed.fields if campo.name == "Motivo")
    assert motivo.value.endswith("…")

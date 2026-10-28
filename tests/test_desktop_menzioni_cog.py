"""
tests/test_desktop_menzioni_cog.py
==================================
SPEC D.5, D.6 (#108): il bot mette in coda gli avvisi solo per chi li ha accesi e vede il canale.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import discord
import pytest

import cogs.utility.desktop_menzioni as dm
from core import desktop_eventi
from core.repositories.desktop_repo import DesktopRepository
from tests.support.discord_fakes import fake_guild, fake_member, fake_message


@pytest.fixture
def repo(monkeypatch, clean_db):
    r = DesktopRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(dm, "desktop_repo", r)
    monkeypatch.setattr(desktop_eventi, "desktop_repo", r)
    return r


def _messaggio(autore=1, contenuto="ciao", menzioni=(), vedono=(10, 11), riferimento=None):
    guild = fake_guild(guild_id=500)
    guild.get_member = MagicMock(side_effect=lambda uid: SimpleNamespace(id=uid) if uid in (10, 11, 12) else None)
    canale = MagicMock()
    canale.id = 77
    canale.name = "generale"
    canale.permissions_for = MagicMock(side_effect=lambda m: SimpleNamespace(view_channel=m.id in vedono))
    msg = fake_message(author=fake_member(user_id=autore), content=contenuto, guild=guild, channel=canale)
    msg.mentions = [SimpleNamespace(id=u) for u in menzioni]
    msg.reference = riferimento
    msg.id = 900
    return msg


async def test_menzione_solo_per_chi_ha_acceso(repo):
    await repo.imposta_menzioni(10, True)
    cog = dm.DesktopMenzioniCog(MagicMock())
    await cog.on_message(_messaggio(menzioni=(10, 11)))
    eventi = await repo.eventi(10)
    assert len(eventi) == 1 and eventi[0]["tipo"] == "menzione" and eventi[0]["message_id"] == 900
    assert eventi[0]["canale_nome"] == "generale" and eventi[0]["guild_id"] == 500
    assert await repo.eventi(11) == []


async def test_parola_chiave_e_canale_che_non_vede(repo):
    await repo.imposta_menzioni(10, True)
    await repo.imposta_parole(10, ["torneo"])
    cog = dm.DesktopMenzioniCog(MagicMock())
    await cog.on_message(_messaggio(contenuto="Domani c'è il TORNEO!", vedono=(10,)))
    assert [e["tipo"] for e in await repo.eventi(10)] == ["parola"]
    cog2 = dm.DesktopMenzioniCog(MagicMock())
    await cog2.on_message(_messaggio(contenuto="torneo", vedono=()))
    assert len(await repo.eventi(10)) == 1  # il canale non lo vede: niente avviso


async def test_risposta_bot_e_dm_ignorati(repo):
    await repo.imposta_menzioni(10, True)
    cog = dm.DesktopMenzioniCog(MagicMock())
    originale = MagicMock(spec=discord.Message)
    originale.author = SimpleNamespace(id=10)
    await cog.on_message(_messaggio(riferimento=SimpleNamespace(resolved=originale)))
    assert [e["tipo"] for e in await repo.eventi(10)] == ["risposta"]
    bot_msg = _messaggio(menzioni=(10,))
    bot_msg.author.bot = True
    await cog.on_message(bot_msg)
    dm_msg = _messaggio(menzioni=(10,))
    dm_msg.guild = None
    await cog.on_message(dm_msg)
    assert len(await repo.eventi(10)) == 1


async def test_errore_del_database_non_si_propaga(monkeypatch):
    finto = MagicMock()
    finto.utenti_con_avvisi.side_effect = RuntimeError("giù")
    monkeypatch.setattr(dm, "desktop_repo", finto)
    await dm.DesktopMenzioniCog(MagicMock()).on_message(_messaggio(menzioni=(10,)))


async def test_avvisa_utente_solo_se_collegato(repo):
    assert await desktop_eventi.avvisa_utente(10, "promemoria", "bevi") is False
    await repo.imposta_token(10, "c" * 64)
    assert await desktop_eventi.avvisa_utente(10, "promemoria", "bevi\nacqua") is True
    ev = await repo.eventi(10)
    assert ev[0]["tipo"] == "promemoria" and ev[0]["testo"] == "bevi acqua"
    with pytest.raises(ValueError):
        await desktop_eventi.avvisa_utente(10, "inventato", "x")

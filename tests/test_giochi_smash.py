"""/giochi smash (#131, B11, FUN-021): solo personaggi adulti, solo canali con limite d'età, un voto a testa."""
import json
import random
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.fun.smash as mod
from cogs.fun.entertainment import MODULE_FUN
from core import smash_logic as sl
from core.database import db
from core.repositories.smash_repo import smash_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

ID = 606


def _pagina(*righe):
    return json.dumps({"data": {"Page": {"characters": list(righe)}}})


def _r(i, eta, nome="Nome", opera="Opera"):
    return {"id": i, "age": eta, "name": {"full": nome}, "media": {"nodes": [{"title": {"romaji": opera, "english": None}}]}}


@pytest.mark.parametrize("eta,ok", [("20", True), ("18", True), ("17", False), ("14", False), ("17-23", False),
                                     ("19-23, (30's in Another)", True), (None, False), ("", False), ("sconosciuta", False), (25, False)])
def test_eta_adulta(eta, ok):
    assert sl.eta_adulta(eta) is ok


def test_pagina_tiene_solo_adulti_con_nome():
    p = sl.interpreta_pagina(_pagina(_r(1, "30", "Adulto"), _r(2, "15", "Minore"), _r(3, None), _r(4, "40", " "), {"id": "x"}, 5))
    assert [x.id for x in p] == [1] and p[0].pagina == "https://anilist.co/character/1" and p[0].opera == "Opera"
    for brutto in (None, "", "no", "{}", '{"data": null}'):
        assert sl.interpreta_pagina(brutto) == []


def test_settimana_iso():
    assert sl.settimana(datetime(2026, 11, 9, tzinfo=timezone.utc)) == "2026-W46"


class _Cache:
    def __init__(self):
        self.m = {}

    async def leggi(self, k):
        return self.m.get(k)

    async def salva(self, k, v, s):
        self.m[k] = v


async def test_personaggio_a_caso_usa_cache_e_non_inventa():
    chiamate = []

    async def scarica(p):
        chiamate.append(p)
        return _pagina(_r(1, "30", "A"), _r(2, "12", "B"))

    cache = _Cache()
    a = await sl.personaggio_a_caso(cache, random.Random(1), scarica)
    b = await sl.personaggio_a_caso(cache, random.Random(1), scarica)
    assert a == b and a.id == 1 and len(chiamate) == 1

    async def muta(p):
        return None

    assert await sl.personaggio_a_caso(_Cache(), random.Random(2), muta) is None
    async def solo_minori(p):
        return _pagina(_r(9, "10"))

    assert await sl.personaggio_a_caso(_Cache(), random.Random(2), solo_minori) is None


@pytest.fixture
async def attivo(monkeypatch, clean_db):
    import core.database as dm
    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


def _it(nsfw=True, u=5):
    it = fake_interaction(guild=fake_guild(ID), user=fake_member(u, "u"))
    it.channel = MagicMock()
    it.channel.is_nsfw.return_value = nsfw
    it.delete_original_response = AsyncMock()
    return it


async def test_albero_giochi_smash():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await mod.setup(bot)
    assert "smash" in percorsi_del_gruppo("giochi")
    comando_nel_gruppo("giochi", "smash").to_dict(bot.tree)


async def test_voto_unico_e_conteggio_settimanale(attivo):
    r = smash_repo
    assert await r.vota(ID, "2026-W46", "1", 10, "smash") is True
    assert await r.vota(ID, "2026-W46", "1", 10, "pass") is False  # resta il primo
    await r.vota(ID, "2026-W46", "1", 11, "pass")
    await r.vota(ID, "2026-W47", "1", 10, "pass")
    assert await r.conteggio(ID, "2026-W46", "1") == (1, 1)
    assert await r.conteggio(ID + 1, "2026-W46", "1") == (0, 0)


async def test_solo_canale_con_limite_eta(attivo, monkeypatch):
    cog = mod.SmashCog(bot=None)
    chiamato = AsyncMock()
    monkeypatch.setattr(mod.sl, "personaggio_a_caso", chiamato)
    it = _it(nsfw=False)
    await cog.smash.callback(cog, it)
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True
    chiamato.assert_not_awaited()


async def test_manda_link_bottoni_e_nessuna_menzione(attivo, monkeypatch):
    cog = mod.SmashCog(bot=None)
    monkeypatch.setattr(mod.sl, "personaggio_a_caso", AsyncMock(return_value=sl.Personaggio(77, "Nome @everyone", "Opera")))
    it = _it()
    await cog.smash.callback(cog, it)
    kw = it.followup.send.await_args.kwargs
    assert "https://anilist.co/character/77" in it.followup.send.await_args.args[0]
    assert isinstance(kw["view"], mod.SmashView) and len(kw["view"].children) == 2
    assert kw["allowed_mentions"].everyone is False
    # un clic vota; il secondo dello stesso utente no
    click = _it(u=31)
    await kw["view"].children[0].callback(click)
    click.response.edit_message.assert_awaited()
    assert "Smash 1" in click.response.edit_message.await_args.kwargs["content"]
    di_nuovo = _it(u=31)
    await kw["view"].children[1].callback(di_nuovo)
    di_nuovo.response.send_message.assert_awaited()
    assert await smash_repo.conteggio(ID, sl.settimana(datetime.now(timezone.utc)), "77") == (1, 0)


async def test_fonte_muta(attivo, monkeypatch):
    cog = mod.SmashCog(bot=None)
    monkeypatch.setattr(mod.sl, "personaggio_a_caso", AsyncMock(return_value=None))
    it = _it()
    await cog.smash.callback(cog, it)
    it.delete_original_response.assert_awaited()
    assert it.followup.send.await_args.kwargs["ephemeral"] is True

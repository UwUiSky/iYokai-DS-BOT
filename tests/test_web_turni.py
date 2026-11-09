"""/web turni (#131, B11, FUN-071): Splatoon 3 da splatoon3.ink e reset di WoW calcolati."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands

from core import turni_logic as tl
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

T0 = int(datetime(2026, 11, 9, 18, 30, tzinfo=timezone.utc).timestamp())


def _imp(regola, mappe, **kw):
    return {"vsStages": [{"name": m} for m in mappe], "vsRule": {"name": regola}, **kw}


def _nodo(ora_inizio, ora_fine, **kw):
    return {"startTime": f"2026-11-09T{ora_inizio:02d}:00:00Z", "endTime": f"2026-11-09T{ora_fine:02d}:00:00Z", **kw}


def _risposta(**extra):
    dati = {
        "regularSchedules": {"nodes": [
            _nodo(16, 18, regularMatchSetting=_imp("Vecchia", ["A", "B"])),  # già finita
            _nodo(18, 20, regularMatchSetting=_imp("Turf War", ["Scorch Gorge", "Eeltail Alley"])),
            _nodo(20, 22, regularMatchSetting=None),  # Splatfest: niente impostazione
            _nodo(22, 23, regularMatchSetting=_imp("Turf War", ["C", "D"])),
            _nodo(23, 24, regularMatchSetting=_imp("Turf War", ["E", "F"])),
        ]},
        "bankaraSchedules": {"nodes": [_nodo(18, 20, bankaraMatchSettings=[
            _imp("Rainmaker", ["G", "H"], bankaraMode="CHALLENGE"), _imp("Tower Control", ["I", "J"], bankaraMode="OPEN")])]},
        "xSchedules": {"nodes": [_nodo(18, 20, xMatchSetting=_imp("Clam Blitz", ["K", "L"]))]},
        "coopGroupingSchedule": {"regularSchedules": {"nodes": [{
            "startTime": "2026-11-09T16:00:00Z", "endTime": "2026-11-11T08:00:00Z",
            "setting": {"boss": {"name": "Horrorboros"}, "coopStage": {"name": "Smokeyard"}, "weapons": [{"name": "Nova"}, {"name": "Mini"}]}}]}},
    }
    dati.update(extra)
    return json.dumps({"data": dati})


def test_interpreta_splatoon_salta_il_passato_e_i_buchi():
    d = tl.interpreta_splatoon(_risposta(), T0)
    modi = {m["id"]: m["turni"] for m in d["modi"]}
    assert set(modi) == {"regular", "serie", "open", "x"}
    assert [t["mappe"] for t in modi["regular"]] == [["Scorch Gorge", "Eeltail Alley"], ["C", "D"]]  # 2 turni, né il passato né il buco
    assert modi["serie"][0]["regola"] == "Rainmaker" and modi["open"][0]["regola"] == "Tower Control"
    assert d["salmon"][0]["boss"] == "Horrorboros" and d["salmon"][0]["armi"] == ["Nova", "Mini"]
    assert modi["x"][0]["inizio"] < modi["x"][0]["fine"]


@pytest.mark.parametrize("brutto", [None, "", "non json", "[]", '{"data": 3}', '{"data": {}}', '{"data": {"regularSchedules": {"nodes": [1, "x"]}}}'])
def test_interpreta_resiste_a_risposte_sbagliate(brutto):
    assert tl.interpreta_splatoon(brutto, T0) is None


def test_reset_wow_calcolati():
    lun = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)  # lunedì
    r = tl.reset_wow(lun)
    assert datetime.fromtimestamp(r["us"], timezone.utc) == datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    assert datetime.fromtimestamp(r["eu"], timezone.utc) == datetime(2026, 11, 11, 4, 0, tzinfo=timezone.utc)
    mar_dopo = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)  # proprio al reset: il prossimo è fra una settimana
    assert datetime.fromtimestamp(tl.reset_wow(mar_dopo)["us"], timezone.utc) == datetime(2026, 11, 17, 15, 0, tzinfo=timezone.utc)
    gio = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
    assert datetime.fromtimestamp(tl.reset_wow(gio)["eu"], timezone.utc) == datetime(2026, 11, 18, 4, 0, tzinfo=timezone.utc)


class _Cache:
    def __init__(self):
        self.m = {}
        self.salvati = 0

    async def leggi(self, k):
        return self.m.get(k)

    async def salva(self, k, v, s):
        self.m[k] = v
        self.salvati += 1
        assert s == 900


async def test_splatoon3_usa_la_cache_per_15_minuti():
    chiamate = []

    async def scarica(url):
        chiamate.append(url)
        return _risposta()

    cache = _Cache()
    a = await tl.splatoon3(cache, T0, scarica)
    b = await tl.splatoon3(cache, T0 + 60, scarica)
    assert a == b and len(chiamate) == 1 and chiamate[0].startswith("https://splatoon3.ink/") and cache.salvati == 1


async def test_splatoon3_senza_risposta_o_cache_vecchia():
    async def niente(url):
        return None

    assert await tl.splatoon3(_Cache(), T0, niente) is None
    vecchia = _Cache()
    vecchia.m["turni:splatoon3"] = {"modi": [{"id": "regular", "turni": [{"fine": T0 - 10}]}], "salmon": []}
    chiamate = []

    async def scarica(url):
        chiamate.append(1)
        return _risposta()

    assert (await tl.splatoon3(vecchia, T0, scarica)) is not None and chiamate  # la cache con turni già finiti non vale


# ---------------------------------------------------------------- comando
import cogs.fun.turni_giochi as mod


def _scelta(v):
    return type("C", (), {"value": v, "name": v})()


async def test_albero_web_turni():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await mod.setup(bot)
    assert "turni" in percorsi_del_gruppo("web")
    comando_nel_gruppo("web", "turni").to_dict(bot.tree)


async def test_comando_wow_e_splatoon(monkeypatch):
    cog = mod.TurniGiochiCog(bot=None)
    it = fake_interaction(guild=fake_guild(1), user=fake_member(5, "u"))
    await cog.turni.callback(cog, it, _scelta("wow"))
    embed = it.followup.send.await_args.kwargs["embed"] if it.followup.send.await_args else it.response.send_message.await_args.kwargs["embed"]
    assert "<t:" in embed.description + "".join(f.value for f in embed.fields) and len(embed) <= 6000

    async def finto(cache, adesso):
        return tl.interpreta_splatoon(_risposta(), T0)

    monkeypatch.setattr(mod.tl, "splatoon3", finto)
    monkeypatch.setattr(mod.time, "time", lambda: T0)
    it2 = fake_interaction(guild=fake_guild(1), user=fake_member(5, "u"))
    await cog.turni.callback(cog, it2, _scelta("splatoon3"))
    embed = it2.followup.send.await_args.kwargs["embed"]
    assert len(embed.fields) >= 4 and all(len(f.value) <= 1024 for f in embed.fields) and len(embed) <= 6000
    assert "Scorch Gorge" in embed.fields[0].value


async def test_splatoon_fonte_muta_risponde_nascosto(monkeypatch):
    cog = mod.TurniGiochiCog(bot=None)

    async def niente(cache, adesso):
        return None

    monkeypatch.setattr(mod.tl, "splatoon3", niente)
    it = fake_interaction(guild=fake_guild(1), user=fake_member(5, "u"))
    await cog.turni.callback(cog, it, _scelta("splatoon3"))
    assert it.followup.send.await_args.kwargs["ephemeral"] is True

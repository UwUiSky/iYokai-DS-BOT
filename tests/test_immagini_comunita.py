"""/immagini post (#131, B10, FUN-053/055): Lemmy da elenco chiuso, niente nsfw, Segnala, blocco a 3 segnalazioni."""
import json
import random
from unittest.mock import AsyncMock

import pytest

from core import lemmy_logic as lm
from core.repositories.immagini_segnalazioni_repo import SOGLIA_BLOCCO, immagini_segnalazioni_repo


def _post(i=1, **kw):
    post = {"id": i, "name": f"Titolo {i}", "url": f"https://lemmy.world/pictrs/image/{i}.jpg", "url_content_type": "image/jpeg",
            "nsfw": False, "removed": False, "deleted": False, "ap_id": f"https://lemmy.world/post/{i}"}
    post.update(kw.pop("post", {}))
    riga = {"post": post, "creator": {"name": "marco", "actor_id": "https://lemmy.world/u/marco"},
            "community": {"name": "aww", "nsfw": False}}
    riga.update(kw)
    return riga


def _testo(*righe):
    return json.dumps({"posts": list(righe)})


def test_elenco_chiuso_con_tetto_e_solo_https():
    tutte = lm.comunita()
    assert 10 <= len(tutte) <= 25
    assert all(c.istanza.startswith("https://") for c in tutte)
    assert len({c.id for c in tutte}) == len(tutte)
    assert lm.trova("aww").nome == "aww" and lm.trova("sconosciuta") is None


def test_filtro_adulti_e_sconosciuti():
    c = lm.trova("aww")
    ok = lm.interpreta(_testo(_post(1), _post(2, post={"nsfw": True}), _post(3, community={"name": "aww", "nsfw": True}),
                             _post(4, post={"removed": True}), _post(5, post={"deleted": True}),
                             _post(6, post={"url": None}), _post(7, post={"url": "http://x.example/a.jpg"}),
                             _post(8, post={"url_content_type": "text/html", "url": "https://x.example/pagina"}),
                             _post(9, post={"url": "https://x.example/a.svg", "url_content_type": "image/svg+xml"})), c)
    assert [p.chiave for p in ok] == ["lemmy.world:1"]
    p = ok[0]
    assert p.autore == "marco" and p.pagina == "https://lemmy.world/post/1" and p.immagine.endswith("/1.jpg")


def test_interpreta_resiste_a_risposte_sbagliate():
    c = lm.trova("aww")
    for brutto in ("", "non json", "[]", '{"posts": "x"}', '{"posts": [1, null, {"post": 3}]}'):
        assert lm.interpreta(brutto, c) == []


def test_titolo_troncato_e_pagina_https():
    c = lm.trova("aww")
    p = lm.interpreta(_testo(_post(1, post={"name": "x" * 500, "ap_id": "http://evil.example/p"})), c)[0]
    assert len(p.titolo) <= 200 and p.pagina.startswith("https://lemmy.world/post/")


async def test_servizio_sceglie_scarta_bloccati_e_usa_cache():
    scaricati = []

    async def scarica(url):
        scaricati.append(url)
        return _testo(_post(1), _post(2))

    memoria = {}

    class Cache:
        async def leggi(self, k): return memoria.get(k)
        async def salva(self, k, v, s): memoria[k] = v

    s = lm.ServizioLemmy(scarica=scarica, cache=Cache(), rng=random.Random(1))
    c = lm.trova("aww")
    p = await s.post(c, bloccati={"lemmy.world:1"})
    assert p.chiave == "lemmy.world:2"
    await s.post(c, bloccati=set())
    assert len(scaricati) == 1 and "community_name=aww" in scaricati[0] and "api/v3/post/list" in scaricati[0]
    assert await s.post(c, bloccati={"lemmy.world:1", "lemmy.world:2"}) is None


async def test_servizio_senza_risposta_non_crasha():
    async def scarica(url):
        return None

    class Cache:
        async def leggi(self, k): return None
        async def salva(self, k, v, s): raise AssertionError("niente da salvare")

    assert await lm.ServizioLemmy(scarica=scarica, cache=Cache()).post(lm.trova("aww"), bloccati=set()) is None


async def test_segnalazioni_blocco_dopo_tre_persone_diverse(clean_db, monkeypatch):
    import core.database as dm
    monkeypatch.setattr(dm.db, "_pool", clean_db)
    r = immagini_segnalazioni_repo
    assert SOGLIA_BLOCCO == 3
    assert await r.segnala("lemmy.world:1", 10, 1) == 1
    assert await r.segnala("lemmy.world:1", 10, 1) == 1  # la stessa persona conta una volta
    assert await r.bloccati(["lemmy.world:1"]) == set()
    await r.segnala("lemmy.world:1", 11, 1)
    assert await r.segnala("lemmy.world:1", 12, 2) == 3
    assert await r.bloccati(["lemmy.world:1", "lemmy.world:2"]) == {"lemmy.world:1"}


# ---------------------------------------------------------------- comando e interruttori
import discord
from discord.ext import commands

import cogs.fun.immagini_comunita as mod
from cogs.fun.entertainment import MODULE_FUN
from core import fun_servizi_logic as servizi
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

ID = 303


class _Servizio:
    def __init__(self, post):
        self.post_scelto = post

    async def elenco(self, com):
        return [self.post_scelto] if self.post_scelto else []

    async def post(self, com, bloccati):
        p = self.post_scelto
        return None if p is None or p.chiave in bloccati else p


@pytest.fixture
async def cog(monkeypatch, clean_db):
    import core.database as dm
    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    p = lm.Post("lemmy.world:7", "Un gatto", "https://lemmy.world/pictrs/image/7.jpg", "https://lemmy.world/post/7", "marco", "aww")
    yield mod.ImmaginiComunitaCog(bot=None, servizio=_Servizio(p))
    dm.db._modules_cache.clear()
    dm.db._settings_cache.clear()


def _it(user_id=5):
    it = fake_interaction(guild=fake_guild(ID), user=fake_member(user_id, "u"))
    it.delete_original_response = AsyncMock()
    return it


async def test_albero_post_e_servizi():
    from core.command_groups import GRUPPI
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await mod.setup(bot)
    assert "post" in percorsi_del_gruppo("immagini") and "servizi" in percorsi_del_gruppo("admin-giochi")
    for g, n in (("immagini", "post"), ("admin-giochi", "servizi")):
        comando_nel_gruppo(g, n).to_dict(bot.tree)


async def test_post_spento_di_base(cog):
    it = _it()
    await cog.post.callback(cog, it, "aww")
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True
    it.response.defer.assert_not_awaited()


async def test_post_acceso_manda_embed_con_credito_e_bottone(cog):
    await db.set_guild_setting(ID, servizi.SETTING_IMMAGINI_POST, True)
    it = _it()
    await cog.post.callback(cog, it, "aww")
    kw = it.followup.send.await_args.kwargs
    assert kw["embed"].image.url.endswith("/7.jpg") and kw["embed"].url == "https://lemmy.world/post/7"
    assert "marco" in kw["embed"].footer.text and isinstance(kw["view"], mod.SegnalaView)
    assert kw["allowed_mentions"].users is False


async def test_post_comunita_sconosciuta_e_pausa(cog):
    await db.set_guild_setting(ID, servizi.SETTING_IMMAGINI_POST, True)
    it = _it()
    await cog.post.callback(cog, it, "boh")
    it.response.defer.assert_not_awaited()
    a, b = _it(8), _it(8)
    await cog.post.callback(cog, a, "aww")
    await cog.post.callback(cog, b, "aww")
    b.response.send_message.assert_awaited()  # seconda richiesta subito dopo: pausa


async def test_segnala_tre_persone_nasconde_il_post(cog):
    await db.set_guild_setting(ID, servizi.SETTING_IMMAGINI_POST, True)
    vista = mod.SegnalaView("lemmy.world:7", "Segnala")
    for utente in (21, 22):
        it = _it(utente)
        await vista._premuto(it)
        it.response.send_message.assert_awaited()
    ultimo = _it(23)
    await vista._premuto(ultimo)
    ultimo.response.edit_message.assert_awaited()
    assert ultimo.response.edit_message.await_args.kwargs["view"] is None
    it = _it()
    await cog.post.callback(cog, it, "aww")  # ora il solo post è bloccato
    it.followup.send.assert_awaited()
    assert "embed" not in it.followup.send.await_args.kwargs


async def test_admin_accende_e_spegne_con_storico(cog):
    it = _it()
    it.guild = fake_guild(ID)
    await db.ensure_guild_exists(ID)
    await cog.servizi_esterni.callback(cog, it, True, None)
    assert await servizi.acceso(ID, servizi.SETTING_IMMAGINI_POST) is True
    assert await servizi.acceso(ID, servizi.SETTING_GIF_CERCA) is False
    await cog.servizi_esterni.callback(cog, _it(), False, True)
    assert await servizi.acceso(ID, servizi.SETTING_IMMAGINI_POST) is False
    assert await servizi.acceso(ID, servizi.SETTING_GIF_CERCA) is True

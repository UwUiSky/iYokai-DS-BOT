"""
tests/test_messaggi_auto.py
===========================
Catalogo #128 B3 (D69): /admin-messaggi scrivi e auto, citazioni, correzione link, pubblicazione annunci
(10 all'ora), elenco e modelli dei messaggi fissi.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands as ext

import cogs.utility.messaggi_auto as cog
import cogs.utility.sticky_messages as sticky
from core import messaggi_auto_logic as L
from core.repositories.messaggi_auto_repo import MessaggiAutoRepository
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.support.percorsi import comando_nel_gruppo

G = 111111111111111111


def test_link_ai_messaggi_solo_stesso_server_senza_doppioni_max_3():
    t = " ".join(f"https://discord.com/channels/{G}/22222222222222222{i}/33333333333333333{i}" for i in range(5))
    t += f" https://discord.com/channels/{G}/222222222222222220/333333333333333330 https://discord.com/channels/999999999999999999/1{'0'*16}1/1{'0'*16}2"
    assert len(L.link_ai_messaggi(t, G)) == 3
    assert L.link_ai_messaggi(f"<https://discord.com/channels/{G}/222222222222222220/333333333333333330>", G) == []


def test_citare_regole_di_vista_e_nsfw():
    assert L.puo_citare(False, False, True)
    assert not L.puo_citare(False, False, False)  # chi scrive non vede l'origine
    assert not L.puo_citare(True, False, True)  # da NSFW a non NSFW
    assert L.puo_citare(True, True, True)


def test_correzione_dei_link():
    m = L.mappa_correzioni(["x.com>fixupx.com", "evil.com>x.it"])
    assert m == {"x.com": "fixupx.com"}  # solo l'elenco proposto
    assert L.link_corretti("guarda https://www.x.com/a/status/1?s=2 e <https://x.com/b> e https://altro.it", m) == [
        "https://fixupx.com/a/status/1?s=2"
    ]
    assert L.link_corretti("https://x.com/a", {}) == []
    assert len(L.link_corretti(" ".join(f"https://x.com/{i}" for i in range(9)), m)) == 3


def test_limite_di_pubblicazione_10_all_ora_e_un_solo_avviso():
    lim = L.LimitePubblicazioni()
    assert all(lim.ammessa(1, 100 + i) for i in range(10))
    assert not lim.ammessa(1, 200)
    assert lim.da_avvisare(1, 200) and not lim.da_avvisare(1, 300)
    assert lim.ammessa(2, 200)  # un altro canale ha il suo conto
    assert lim.ammessa(1, 100 + 3601)  # passata l'ora


@pytest.mark.asyncio
async def test_repo_correzioni_canali_e_tetto(clean_db):
    r = MessaggiAutoRepository(pool_provider=lambda: clean_db)
    assert (await r.get(1)).citazioni is False
    await r.imposta_citazioni(1, True)
    assert (await r.get(1)).citazioni is True
    assert await r.alterna_correzione(1, "x.com>fixupx.com") is True
    assert (await r.get(1)).correzioni == ("x.com>fixupx.com",)
    assert await r.alterna_correzione(1, "x.com>fixupx.com") is False
    for i in range(25):
        assert await r.aggiungi_canale_pubblica(1, 1000 + i)
    assert not await r.aggiungi_canale_pubblica(1, 5000)  # il 26°
    assert await r.aggiungi_canale_pubblica(1, 1000)  # già presente: va bene
    assert await r.togli_canale_pubblica(1, 1000) and not await r.togli_canale_pubblica(1, 1000)
    assert len((await r.get(1)).pubblica_canali) == 24


@pytest.mark.asyncio
async def test_la_cache_non_ricorda_una_lettura_fallita():
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=[RuntimeError("giù"), None])
    r = MessaggiAutoRepository(pool_provider=lambda: pool)
    with pytest.raises(RuntimeError):
        await r.get(7)
    assert (await r.get(7)).citazioni is False  # riletto, non preso da una copia vuota


@pytest.mark.asyncio
async def test_pubblica_il_messaggio_e_avvisa_una_volta(monkeypatch):
    c = cog.MessaggiAutoCog(MagicMock())
    canale = MagicMock(spec=discord.TextChannel)
    canale.id = 5
    canale.is_news.return_value = True
    msg = MagicMock(channel=canale, guild=fake_guild(), id=9, flags=discord.MessageFlags())
    msg.publish = AsyncMock()
    avviso = AsyncMock()
    monkeypatch.setattr(c, "_avvisa_limite", avviso)
    for _ in range(12):
        await c._pubblica(msg)
    assert msg.publish.await_count == 10
    avviso.assert_awaited_once()


@pytest.mark.asyncio
async def test_pubblica_solo_in_canali_annunci():
    c = cog.MessaggiAutoCog(MagicMock())
    canale = MagicMock(spec=discord.TextChannel)
    canale.is_news.return_value = False
    msg = MagicMock(channel=canale)
    msg.publish = AsyncMock()
    await c._pubblica(msg)
    msg.publish.assert_not_called()


@pytest.mark.asyncio
async def test_scrivi_senza_menzioni_di_tutti_e_modale_con_limite():
    canale = MagicMock(spec=discord.TextChannel)
    canale.id, canale.mention = 5, "#x"
    canale.send = AsyncMock()
    utente = MagicMock(spec=discord.Member)
    utente.guild_permissions = discord.Permissions(manage_guild=True)  # niente «Menziona tutti»
    m = cog.ScriviModal(canale, 77, "it")
    assert m.testo.max_length == 2000
    m.testo._value = "ciao @everyone"
    it = fake_interaction(user=utente)
    await m.on_submit(it)
    kw = canale.send.await_args.kwargs
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].roles is False
    assert kw["reference"].message_id == 77 and kw["reference"].fail_if_not_exists is False


def test_id_messaggio_da_link():
    assert cog.id_messaggio_da_link(f"https://discord.com/channels/{G}/5/99", G, 5) == 99
    assert cog.id_messaggio_da_link(f"https://discord.com/channels/{G}/6/99", G, 5) is None


@pytest.mark.asyncio
async def test_albero_auto_scrivi_fissi_elenco_e_limiti():
    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await cog.setup(bot)
    await sticky.setup(bot)
    auto = comando_nel_gruppo("admin-messaggi", "auto").to_dict(bot.tree)
    assert len(auto["options"]) == 5 and not any(o.get("required") for o in auto["options"])
    scelte = next(o for o in auto["options"] if o["name"] == "correggi_link")["choices"]
    assert 0 < len(scelte) <= 25
    imposta = comando_nel_gruppo("admin-messaggi", "fissi imposta").to_dict(bot.tree)["options"]
    assert [o["name"] for o in imposta] == ["channel", "message", "modello"]
    assert imposta[0]["required"] and not imposta[1].get("required") and not imposta[2].get("required")
    assert imposta[1]["max_length"] == 2000
    assert comando_nel_gruppo("admin-messaggi", "fissi elenco") is not None
    assert comando_nel_gruppo("admin-messaggi", "scrivi") is not None


@pytest.mark.asyncio
async def test_fissi_senza_testo_ne_modello_chiede_uno_dei_due():
    c = sticky.StickyMessagesCog(MagicMock())
    it = fake_interaction()
    await c.set_sticky.callback(c, it, MagicMock(spec=discord.TextChannel), None, None)
    it.response.send_message.assert_awaited_once()
    assert "modello" in it.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_non_ripubblica_un_messaggio_gia_pubblicato():
    c = cog.MessaggiAutoCog(MagicMock())
    canale = MagicMock(spec=discord.TextChannel)
    canale.id = 5
    canale.is_news.return_value = True
    msg = MagicMock(channel=canale, guild=fake_guild(), id=9, flags=discord.MessageFlags(crossposted=True))
    msg.publish = AsyncMock()
    for _ in range(12):
        await c._pubblica(msg)
    msg.publish.assert_not_awaited()
    assert c.limite.ammessa(5, 1.0)  # il tetto orario è intatto

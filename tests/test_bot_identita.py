"""
tests/test_bot_identita.py
==========================
Identità dei bot secondari in un server (MUS-090, D111): nickname e logo del server, bot musicali esclusi, permessi,
pausa contro i cambi ripetuti, ritorno all'originale, controllo del logo. Client e server di Discord finti.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import bot_identita as idn
from core import immagini_pipeline
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

GID = 4242
PNG_FINTO = b"\x89PNG-ricodificato"


def _admin():
    return fake_member(10, guild_permissions=discord.Permissions(manage_guild=True))


def _semplice():
    return fake_member(11, guild_permissions=discord.Permissions.none())


def _client(guild):
    c = MagicMock()
    c.is_closed.return_value = False
    c.get_guild.return_value = guild
    return c


@pytest.fixture(autouse=True)
def _pulito():
    idn._clients.clear()
    idn._limite_cambi._colpi.clear()
    yield
    idn._clients.clear()


@pytest.fixture
def bot_mod():
    guild = fake_guild(GID)
    guild.me.nick = None
    guild.me.guild_avatar = None
    guild.me.edit = AsyncMock()
    idn.registra("mod", _client(guild))
    return guild


@pytest.fixture
def logo_pulito(monkeypatch):
    esito = immagini_pipeline.EsitoImmagine(immagini_pipeline.PULITA, "x", png=PNG_FINTO)
    monkeypatch.setattr(immagini_pipeline, "analizza_immagine", AsyncMock(return_value=esito))


def test_i_bot_musicali_non_si_registrano():
    for nome in ("musica", "music", "worker"):
        with pytest.raises(ValueError):
            idn.registra(nome, MagicMock())
    with pytest.raises(ValueError):
        idn.registra("sconosciuto", MagicMock())
    assert idn._clients == {}


async def test_bot_musicale_rifiutato_senza_toccare_nulla(bot_mod):
    for nome in ("musica", "music", "worker"):
        assert await idn.applica_identita(_admin(), GID, nome, nick="Ciao") == "idn_musica_esclusa"
    bot_mod.me.edit.assert_not_awaited()
    assert [s.chiave for s in idn.stati(GID)] == ["mod"]  # nessun musicale in elenco


async def test_nickname_del_server(bot_mod):
    assert await idn.applica_identita(_admin(), GID, "mod", nick="  Custode  ") == "idn_ok"
    assert bot_mod.me.edit.await_args.kwargs["nick"] == "Custode"
    assert "avatar" not in bot_mod.me.edit.await_args.kwargs  # il logo non si tocca se non scelto


async def test_nickname_troppo_lungo_o_vuoto(bot_mod):
    assert await idn.applica_identita(_admin(), GID, "mod", nick="x" * 33) == "idn_nick_lungo"
    bot_mod.me.edit.assert_not_awaited()
    # nome vuoto = torna all'originale
    assert await idn.applica_identita(_admin(), GID, "mod", nick="   ") == "idn_ripristinato"
    assert bot_mod.me.edit.await_args.kwargs["nick"] is None


async def test_permesso_riletto_a_ogni_chiamata(bot_mod):
    assert await idn.applica_identita(_semplice(), GID, "mod", nick="Hack") == "idn_permesso_utente"
    assert await idn.ripristina_originale(_semplice(), GID, "mod") == "idn_permesso_utente"
    bot_mod.me.edit.assert_not_awaited()


async def test_bot_assente_o_scollegato(bot_mod):
    assert await idn.applica_identita(_admin(), GID, "nsfw", nick="A") == "idn_bot_assente"  # mai registrato
    idn._clients["mod"].get_guild.return_value = None  # il bot non è in questo server
    assert await idn.applica_identita(_admin(), GID, "mod", nick="A") == "idn_bot_assente"
    idn._clients["mod"].is_closed.return_value = True
    assert idn.stati(GID) == []
    assert await idn.applica_identita(_admin(), GID, "xyz", nick="A") == "idn_bot_sconosciuto"


async def test_logo_ricodificato_e_non_l_originale(bot_mod, logo_pulito):
    originale = b"ORIGINALE-NON-SICURO"
    assert await idn.applica_identita(_admin(), GID, "mod", logo=originale) == "idn_ok"
    assert bot_mod.me.edit.await_args.kwargs["avatar"] == PNG_FINTO
    assert originale not in bot_mod.me.edit.await_args.kwargs.values()


async def test_logo_non_pulito_o_non_analizzato_si_rifiuta(bot_mod, monkeypatch):
    for esito in (
        immagini_pipeline.EsitoImmagine(immagini_pipeline.MALEVOLA, "x", png=PNG_FINTO),
        immagini_pipeline.EsitoImmagine(immagini_pipeline.PULITA, "x", png=PNG_FINTO, non_analizzata="sandbox"),
        immagini_pipeline.EsitoImmagine(immagini_pipeline.PULITA, "x", png=b""),
    ):
        monkeypatch.setattr(immagini_pipeline, "analizza_immagine", AsyncMock(return_value=esito))
        assert await idn.applica_identita(_admin(), GID, "mod", logo=b"dati") == "idn_logo_non_valido"
    monkeypatch.setattr(immagini_pipeline, "analizza_immagine", AsyncMock(side_effect=RuntimeError("sandbox giù")))
    assert await idn.applica_identita(_admin(), GID, "mod", logo=b"dati") == "idn_logo_non_valido"
    bot_mod.me.edit.assert_not_awaited()


async def test_logo_troppo_pesante(bot_mod):
    assert await idn.applica_identita(_admin(), GID, "mod", logo=b"0" * (idn.MAX_LOGO + 1)) == "idn_logo_grande"
    bot_mod.me.edit.assert_not_awaited()


async def test_logo_vero_non_immagine_passa_dai_controlli_veri(bot_mod):
    assert await idn.applica_identita(_admin(), GID, "mod", logo=b"MZ\x90\x00 non sono un'immagine") == "idn_logo_non_valido"
    bot_mod.me.edit.assert_not_awaited()


async def test_pausa_contro_i_cambi_ripetuti_ma_l_originale_resta_possibile(bot_mod):
    for i in range(4):
        assert await idn.applica_identita(_admin(), GID, "mod", nick=f"N{i}") == "idn_ok"
    assert await idn.applica_identita(_admin(), GID, "mod", nick="N5") == "idn_attendi"
    assert await idn.ripristina_originale(_admin(), GID, "mod") == "idn_ripristinato"
    assert bot_mod.me.edit.await_args.kwargs == {"nick": None, "avatar": None, "reason": bot_mod.me.edit.await_args.kwargs["reason"]}


async def test_la_pausa_e_per_server_e_per_bot(bot_mod):
    for i in range(4):
        await idn.applica_identita(_admin(), GID, "mod", nick=f"N{i}")
    altro = fake_guild(GID)
    altro.me.edit = AsyncMock()
    idn.registra("nsfw", _client(altro))
    assert await idn.applica_identita(_admin(), GID, "nsfw", nick="Libero") == "idn_ok"


async def test_discord_rifiuta(bot_mod):
    risposta = MagicMock(status=403)
    bot_mod.me.edit.side_effect = discord.Forbidden(risposta, "no")
    assert await idn.applica_identita(_admin(), GID, "mod", nick="A") == "idn_permesso_bot"
    bot_mod.me.edit.side_effect = discord.HTTPException(MagicMock(status=500), "boom")
    assert await idn.applica_identita(_admin(), GID, "mod", nick="B") == "idn_errore"


async def test_stato_mostra_il_profilo_del_server(bot_mod):
    bot_mod.me.nick = "Custode"
    bot_mod.me.guild_avatar = MagicMock(url="https://cdn.example/avatar.png")
    (s,) = idn.stati(GID)
    assert (s.chiave, s.nick, s.logo, s.personalizzato) == ("mod", "Custode", "https://cdn.example/avatar.png", True)


async def test_niente_da_cambiare(bot_mod):
    assert await idn.applica_identita(_admin(), GID, "mod") == "idn_niente"


# --- il comando ------------------------------------------------------------
async def _cog():
    from cogs.utility.identita_bot import IdentitaBotCog

    return IdentitaBotCog(MagicMock())


async def test_comando_senza_scelte_mostra_l_elenco(bot_mod):
    cog = await _cog()
    it = fake_interaction(guild=fake_guild(GID), user=_admin())
    await cog.identita.callback(cog, it)
    testo = it.followup.send.await_args.args[0]
    assert "iYokai Mod" in testo and "iYokai Music" in testo
    bot_mod.me.edit.assert_not_awaited()


async def test_comando_permesso(bot_mod):
    cog = await _cog()
    it = fake_interaction(guild=fake_guild(GID), user=_semplice())
    scelta = MagicMock(value="mod")
    await cog.identita.callback(cog, it, scelta, "Hack")
    assert "Gestisci server" in it.response.send_message.await_args.args[0]
    bot_mod.me.edit.assert_not_awaited()


async def test_comando_cambia_nome_e_torna_originale(bot_mod):
    cog = await _cog()
    scelta = MagicMock(value="mod")
    it = fake_interaction(guild=fake_guild(GID), user=_admin())
    await cog.identita.callback(cog, it, scelta, "Custode")
    assert bot_mod.me.edit.await_args.kwargs["nick"] == "Custode"
    it = fake_interaction(guild=fake_guild(GID), user=_admin())
    await cog.identita.callback(cog, it, scelta, None, None, True)
    assert bot_mod.me.edit.await_args.kwargs["nick"] is None and bot_mod.me.edit.await_args.kwargs["avatar"] is None
    assert "originali" in it.followup.send.await_args.args[0]


def test_comando_senza_scelta_musicale():
    from cogs.utility.identita_bot import ETICHETTE

    assert not set(ETICHETTE) & set(idn.BOT_ESCLUSI)
    assert set(ETICHETTE) == set(idn.BOT_SCELTI)

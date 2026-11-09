"""Comandi /gif reazione|azione|privacy (#131, D70, FUN-137/139): privacy, blocchi, menzioni, ricambia, limiti."""
from unittest.mock import AsyncMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.fun.gif as gifmod
from cogs.fun.entertainment import MODULE_FUN
from core.database import db
from core.gif_fonti import Gif, ServizioGif
from core.repositories.gif_privacy_repo import MAX_BLOCCHI, gif_privacy_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

ID = 202
AUTORE, BERS = 1001, 1002


class _C:
    def __init__(self, value):
        self.value = value
        self.name = value


class _Servizio:
    def __init__(self, gif=Gif("https://nekos.best/a.gif", "nekos.best", "Titolo", "https://x.example/a")):
        self.gif = gif
        self.viste = []

    async def prendi(self, voce):
        self.viste.append(voce.id)
        return self.gif


@pytest.fixture(autouse=True)
async def _attivo(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    monkeypatch.setattr(gifmod, "servizio_gif", _Servizio())
    yield
    dm.db._modules_cache.clear()


@pytest.fixture
def cog():
    return gifmod.GifCog(bot=None)


def _it(user_id=AUTORE):
    it = fake_interaction(guild=fake_guild(ID), user=fake_member(user_id, "autore"))
    it.delete_original_response = AsyncMock()
    return it


def _risposta(it):
    return it.response.send_message.await_args


async def test_albero_gif_ha_tre_comandi_e_regge_i_limiti():
    from core.command_groups import GRUPPI

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await gifmod.setup(bot)
    assert percorsi_del_gruppo("gif") == {"reazione", "azione", "privacy"}
    assert len(GRUPPI["gif"].commands) <= 25
    for nome in ("reazione", "azione", "privacy"):
        comando_nel_gruppo("gif", nome).to_dict(bot.tree)


async def test_reazione_manda_embed_con_credito_senza_menzioni(cog):
    it = _it()
    await cog.reazione.callback(cog, it, "piange", "@everyone che giornata")
    it.response.defer.assert_awaited()
    kw = it.followup.send.await_args.kwargs
    embed = kw["embed"]
    assert embed.image.url == "https://nekos.best/a.gif"
    assert "nekos.best" in embed.footer.text and "Titolo" in embed.footer.text
    assert "autore piange" in embed.description and "che giornata" in embed.description
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].users is False
    assert len(embed) <= 6000


async def test_reazione_riconvalida_il_valore_e_modulo_spento(cog):
    it = _it()
    await cog.reazione.callback(cog, it, "inventata", None)
    assert _risposta(it).kwargs["ephemeral"] is True
    it.response.defer.assert_not_awaited()
    await db.set_module_active_for_guild(ID, MODULE_FUN, False)
    it = _it()
    await cog.reazione.callback(cog, it, "piange", None)
    assert _risposta(it).kwargs["ephemeral"] is True


async def test_reazione_senza_gif_ritira_il_messaggio_e_avvisa_nascosto(cog, monkeypatch):
    monkeypatch.setattr(gifmod, "servizio_gif", _Servizio(None))
    it = _it()
    await cog.reazione.callback(cog, it, "piange", None)
    it.delete_original_response.assert_awaited()
    assert it.followup.send.await_args.kwargs["ephemeral"] is True


async def test_azione_pinga_solo_il_bersaglio_e_ha_il_bottone(cog):
    it = _it()
    await cog.azione.callback(cog, it, "abbraccia", fake_member(BERS, "bersaglio"))
    kw = it.followup.send.await_args.kwargs
    assert f"<@{AUTORE}> abbraccia <@{BERS}>" in kw["content"]
    assert [u.id for u in kw["allowed_mentions"].users] == [BERS]
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].roles is False
    bottone = kw["view"].bottone
    assert bottone.custom_id == f"gif:ric:abbraccia:{AUTORE}:{BERS}" and len(bottone.custom_id) < 100
    assert kw["view"].timeout == 600


async def test_azione_su_bot_e_su_se_stessi_e_nessuna_gif(cog):
    for bersaglio in (fake_member(BERS, "bot", bot=True), fake_member(AUTORE, "io")):
        it = _it()
        await cog.azione.callback(cog, it, "abbraccia", bersaglio)
        assert _risposta(it).kwargs["ephemeral"] is True
        it.followup.send.assert_not_awaited()


async def test_azione_rispetta_blocca_tutti_e_blocco_personale_senza_ping(cog):
    await gif_privacy_repo.imposta_blocca_tutti(BERS, True)
    it = _it()
    await cog.azione.callback(cog, it, "schiaffo", fake_member(BERS, "bersaglio"))
    assert _risposta(it).kwargs["ephemeral"] is True
    it.followup.send.assert_not_awaited()
    assert gifmod.servizio_gif.viste == []  # niente richiesta alla fonte
    await gif_privacy_repo.imposta_blocca_tutti(BERS, False)
    await gif_privacy_repo.blocca(BERS, AUTORE)
    it = _it()
    await cog.azione.callback(cog, it, "schiaffo", fake_member(BERS, "bersaglio"))
    assert _risposta(it).kwargs["ephemeral"] is True
    it = _it(user_id=777)  # un altro autore non è bloccato
    await cog.azione.callback(cog, it, "schiaffo", fake_member(BERS, "bersaglio"))
    it.followup.send.assert_awaited()


async def test_privacy_comandi_e_tetto_25(cog):
    it = _it()
    await cog.privacy.callback(cog, it, _C("blocca-tutti"), None)
    assert await gif_privacy_repo.blocca_tutti(AUTORE)
    await cog.privacy.callback(cog, _it(), _C("consenti-tutti"), None)
    assert not await gif_privacy_repo.blocca_tutti(AUTORE)
    for i in range(MAX_BLOCCHI):
        assert await gif_privacy_repo.blocca(AUTORE, 5000 + i) == "ok"
    assert await gif_privacy_repo.blocca(AUTORE, 5000) == "gia"
    assert await gif_privacy_repo.blocca(AUTORE, 9999) == "tetto"
    it = _it()
    utente = create_autospec(discord.User, instance=True)
    utente.id, utente.mention = 9999, "<@9999>"
    await cog.privacy.callback(cog, it, _C("blocca-utente"), utente)
    assert _risposta(it).kwargs["ephemeral"] is True and str(MAX_BLOCCHI) in _risposta(it).args[0]
    it = _it()
    await cog.privacy.callback(cog, it, _C("elenco"), None)
    embed = _risposta(it).kwargs["embed"]
    assert embed.description.count("<@") == MAX_BLOCCHI and len(embed.description) <= 4000
    assert _risposta(it).kwargs["ephemeral"] is True
    it = _it()
    utente.id, utente.mention = 5000, "<@5000>"
    await cog.privacy.callback(cog, it, _C("sblocca-utente"), utente)
    assert 5000 not in await gif_privacy_repo.elenco(AUTORE)


async def test_privacy_serve_l_utente_e_non_su_se_stessi(cog):
    it = _it()
    await cog.privacy.callback(cog, it, _C("blocca-utente"), None)
    assert _risposta(it).kwargs["ephemeral"] is True
    me = create_autospec(discord.User, instance=True)
    me.id, me.mention = AUTORE, f"<@{AUTORE}>"
    it = _it()
    await cog.privacy.callback(cog, it, _C("blocca-utente"), me)
    assert await gif_privacy_repo.elenco(AUTORE) == []


async def test_privacy_funziona_con_il_modulo_spento(cog):
    await db.set_module_active_for_guild(ID, MODULE_FUN, False)
    await cog.privacy.callback(cog, _it(), _C("blocca-tutti"), None)
    assert await gif_privacy_repo.blocca_tutti(AUTORE)


async def test_ricambia_solo_il_bersaglio_una_volta_e_senza_nuovo_bottone(cog):
    voce = gifmod.catalogo.trova("azione", "abbraccia")
    vista = gifmod.RicambiaView(cog, voce, AUTORE, BERS, "Ricambia")
    intruso = _it(user_id=555)
    await vista._premuto(intruso)
    assert _risposta(intruso).kwargs["ephemeral"] is True and not vista.bottone.disabled
    it = _it(user_id=BERS)
    autore = fake_member(AUTORE, "autore")
    it.guild.get_member.return_value = autore
    await vista._premuto(it)
    assert vista.bottone.disabled
    it.response.edit_message.assert_awaited()
    kw = it.followup.send.await_args.kwargs
    assert "view" not in kw and [u.id for u in kw["allowed_mentions"].users] == [AUTORE]


async def test_ricambia_rispetta_il_blocco_dell_autore(cog):
    voce = gifmod.catalogo.trova("azione", "abbraccia")
    await gif_privacy_repo.blocca(AUTORE, BERS)
    vista = gifmod.RicambiaView(cog, voce, AUTORE, BERS, "Ricambia")
    it = _it(user_id=BERS)
    it.guild.get_member.return_value = fake_member(AUTORE, "autore")
    await vista._premuto(it)
    assert it.followup.send.await_args.kwargs["ephemeral"] is True
    assert gifmod.servizio_gif.viste == []


async def test_il_completamento_usa_solo_dati_locali_e_resta_nei_limiti():
    it = fake_interaction()
    scelte = await gifmod._completa_reazione(it, "")
    assert len(scelte) == 25 and all(len(s.name) <= 100 and len(s.value) <= 100 for s in scelte)
    assert [s.value for s in await gifmod._completa_azione(it, "abbr")] == ["abbraccia"]


async def test_spegnere_le_azioni_nel_server_e_solo_la_politica_139():
    from core import command_policy as p

    assert await p.modifica_elenco(ID, p.CHIAVE_COMANDI_OFF, "gif azione", aggiungi=True, changed_by=1)
    politica = await p.leggi_politica(ID)
    kw = dict(canali=[], ruoli=[], user_id=AUTORE, esente=False)
    assert p.valuta(politica, percorso="gif azione", **kw) == p.MOTIVO_COMANDO_OFF
    assert p.valuta(politica, percorso="gif reazione", **kw) is None


async def test_ricambia_non_aggira_il_modulo_spento_ne_la_politica(cog):
    from core import command_policy as p

    voce = gifmod.catalogo.trova("azione", "abbraccia")
    vista = gifmod.RicambiaView(cog, voce, AUTORE, BERS, "Ricambia")
    assert await p.modifica_elenco(ID, p.CHIAVE_COMANDI_OFF, "gif azione", aggiungi=True, changed_by=1)
    it = _it(user_id=BERS)
    it.guild.get_member.return_value = fake_member(AUTORE, "autore")
    await vista._premuto(it)
    assert _risposta(it).kwargs["ephemeral"] is True and not vista.bottone.disabled
    assert gifmod.servizio_gif.viste == []

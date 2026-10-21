"""
tests/test_nsfw_canale.py
=========================
NF-23 (#94): istanza NSFW. Solo canali vietati ai minori (ricontrollati a
ogni invio), lista permessa e lista vietata, registro con l'impronta,
segnalazione che blocca in tutti i server, pubblicazione automatica, albero
separato e nessun effetto sul bot principale.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from core import nsfw_autopost_worker as worker
from core import nsfw_servizio as servizio
from core.nsfw_filter_logic import ElementoFonte, impronta
from core.nsfw_bot import NsfwBot
from core.repositories.nsfw_repo import NsfwRepository
from tests.support.discord_fakes import fake_interaction, fake_text_channel

pytestmark = pytest.mark.asyncio

GUILD = 700


def _el(id_fonte, tag=("amateur",), verificato=True):
    return ElementoFonte(
        fonte="redgifs", id_fonte=id_fonte, tag=tag, testo="", autore="creatrice", verificato=verificato,
        url_pagina=f"https://www.redgifs.com/watch/{id_fonte}",
        url_anteprima=f"https://media.redgifs.com/{id_fonte}-poster.jpg",
    )


class FontiFinte:
    def __init__(self, elementi):
        self.elementi = elementi
        self.scaricati: list[str] = []

    async def cerca(self, tag):
        return list(self.elementi)

    async def scarica_anteprima(self, elemento):
        self.scaricati.append(elemento.id_fonte)
        return f"immagine-{elemento.id_fonte}".encode()


def _canale(nsfw=True, channel_id=55):
    canale = fake_text_channel(channel_id)
    canale.is_nsfw.return_value = nsfw
    canale.guild = SimpleNamespace(id=GUILD)
    canale.send = AsyncMock(return_value=SimpleNamespace(id=9000 + channel_id))
    return canale


@pytest.fixture
async def repo(clean_db, monkeypatch):
    r = NsfwRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(servizio, "nsfw_repo", r)
    monkeypatch.setattr(worker, "nsfw_repo", r)
    return r


@pytest.fixture
def fonti(monkeypatch):
    f = FontiFinte([_el("vietato", tag=("amateur", "teen")), _el("nonverificato", verificato=False), _el("buono")])
    monkeypatch.setattr(servizio, "fonti_nsfw", f)
    return f


async def _attiva(tag="amateur"):
    await servizio.imposta_attivo(GUILD, True, 1)
    assert (await servizio.aggiungi_tag(GUILD, tag))[0]


# ---------------------------------------------------------------- scelte del server
async def test_spenta_non_pubblica(repo, fonti):
    esito = await servizio.scegli(GUILD, "amateur")
    assert isinstance(esito, str) and "non è attiva" in esito
    assert fonti.scaricati == []


async def test_lista_permessa_rifiuta_tag_vietati_e_tiene_il_tetto(repo):
    ok, testo = await servizio.aggiungi_tag(GUILD, "loli")
    assert not ok and "lista vietata" in testo
    assert (await servizio.aggiungi_tag(GUILD, "Amateur"))[0]
    assert not (await servizio.aggiungi_tag(GUILD, "amateur"))[0]
    assert (await servizio.leggi(GUILD)).tag_permessi == ("amateur",)
    assert (await servizio.togli_tag(GUILD, "amateur"))[0]
    assert (await servizio.leggi(GUILD)).tag_permessi == ()


async def test_tag_vuoto_sceglie_a_caso_nella_lista_permessa(repo, fonti):
    await _attiva()
    scelta = await servizio.scegli(GUILD, "")
    assert not isinstance(scelta, str) and scelta.elemento.id_fonte == "buono"


async def test_tag_fuori_lista_permessa_rifiutato(repo, fonti):
    await _attiva()
    esito = await servizio.scegli(GUILD, "redhead")
    assert isinstance(esito, str) and "lista permessa" in esito


# ---------------------------------------------------------------- scelta e invio
async def test_sceglie_solo_il_contenuto_che_passa_i_filtri(repo, fonti):
    await _attiva()
    scelta = await servizio.scegli(GUILD, "amateur")
    assert not isinstance(scelta, str)
    assert scelta.elemento.id_fonte == "buono"
    assert scelta.impronta == impronta(b"immagine-buono")
    assert fonti.scaricati == ["buono"]  # i vietati non si scaricano nemmeno


async def test_invio_rifiutato_se_il_canale_non_e_nsfw(repo, fonti):
    await _attiva()
    scelta = await servizio.scegli(GUILD, "amateur")
    canale = _canale(nsfw=False)
    esito = await servizio.pubblica(canale, scelta, None)
    assert esito == servizio.CANALE_NON_AMMESSO
    canale.send.assert_not_awaited()


async def test_invio_registra_impronta_e_non_ripete(repo, fonti):
    await _attiva()
    canale = _canale()
    scelta = await servizio.scegli(GUILD, "amateur")
    messaggio = await servizio.pubblica(canale, scelta, None)
    assert messaggio.id == 9055
    assert canale.send.await_args.kwargs["file"].spoiler is True
    invio = await repo.invio_del_messaggio(9055)
    assert (invio.id_fonte, invio.impronta) == ("buono", impronta(b"immagine-buono"))
    # Lo stesso contenuto non esce due volte nello stesso server.
    esito = await servizio.scegli(GUILD, "amateur")
    assert isinstance(esito, str) and "Nessun contenuto nuovo" in esito


async def test_segnala_blocca_in_tutti_i_server(repo, fonti):
    await _attiva()
    scelta = await servizio.scegli(GUILD, "amateur")
    await servizio.pubblica(_canale(), scelta, None)
    invio, ovunque = await servizio.segnala(9055, da=42)
    assert invio.id_fonte == "buono" and ovunque
    assert await repo.e_bloccato("redgifs", "buono")
    # In un altro server il contenuto bloccato non si scarica più.
    await servizio.imposta_attivo(GUILD + 1, True, 1)
    await servizio.aggiungi_tag(GUILD + 1, "amateur")
    fonti.scaricati.clear()
    esito = await servizio.scegli(GUILD + 1, "amateur")
    assert isinstance(esito, str) and fonti.scaricati == []
    assert await servizio.segnala(1, da=42) is None


# ---------------------------------------------------------------- pubblicazione automatica
async def test_autopost_solo_in_canale_nsfw_e_con_tag_permesso(repo):
    await _attiva()
    assert not (await servizio.imposta_autopost(GUILD, _canale(nsfw=False), "amateur", 60, 1))[0]
    assert not (await servizio.imposta_autopost(GUILD, _canale(), "redhead", 60, 1))[0]
    assert not (await servizio.imposta_autopost(GUILD, _canale(), "amateur", 10, 1))[0]
    assert (await servizio.imposta_autopost(GUILD, _canale(), "amateur", 60, 1))[0]
    assert (await servizio.imposta_autopost(GUILD, _canale(channel_id=56), None, 60, 1))[0]
    assert [a.tag for a in await servizio.elenco_autopost(GUILD)] == ["amateur", ""]
    # Spegnere l'istanza ferma anche le pubblicazioni automatiche.
    await servizio.imposta_attivo(GUILD, False, 1)
    assert await servizio.elenco_autopost(GUILD) == []


async def test_autopost_pubblica_e_ricontrolla_il_canale(repo, fonti):
    await _attiva()
    canale = _canale()
    await servizio.imposta_autopost(GUILD, canale, "amateur", 60, 1)
    bot = MagicMock()
    bot.get_channel.return_value = canale
    adesso = datetime.now(timezone.utc)
    [voce] = await repo.autopost_scaduti(10)
    assert await worker.esegui_uno(bot, voce, lambda: None, adesso) == "pubblicato"
    assert await repo.autopost_scaduti(10) == []
    # Il canale perde il segno NSFW: niente invio, e dopo 5 errori la pubblicazione si toglie.
    canale.is_nsfw.return_value = False
    canale.send.reset_mock()
    await repo.rimanda_autopost(GUILD, canale.id, adesso - timedelta(minutes=1), worker.MAX_ERRORI - 1)
    [voce] = await repo.autopost_scaduti(10)
    assert await worker.esegui_uno(bot, voce, lambda: None, adesso) == "tolto"
    canale.send.assert_not_awaited()
    assert await servizio.elenco_autopost(GUILD) == []


# ---------------------------------------------------------------- comandi e albero
async def test_il_bot_principale_non_riceve_i_comandi_nsfw():
    import cogs.nsfw.ricerca as ricerca

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await ricerca.setup(bot)
    assert bot.tree.get_commands() == [] and bot.cogs == {}
    await bot.close()


async def test_albero_nsfw_separato_e_vietato_ai_minori():
    bot = NsfwBot()
    await bot.carica_cog()
    try:
        radici = bot.tree.get_commands()
        assert {r.name for r in radici} == {"nsfw", "nsfw-admin"}
        for radice in radici:
            assert radice.nsfw and radice.guild_only
            assert len(radice.commands) <= 25
            for comando in radice.commands:
                for p in comando.parameters:
                    if p.type is discord.AppCommandOptionType.string:
                        assert p.max_value is not None, f"{comando.qualified_name}:{p.name} senza massimo"
        admin = next(r for r in radici if r.name == "nsfw-admin")
        assert admin.default_permissions == discord.Permissions(manage_guild=True)
    finally:
        await bot.close()


async def test_cerca_rifiuta_un_canale_non_nsfw_senza_lavorare(repo, fonti):
    import cogs.nsfw.ricerca as ricerca

    cog = ricerca.NsfwCog(MagicMock())
    interazione = fake_interaction(channel=_canale(nsfw=False))
    await cog.cerca.callback(cog, interazione, "amateur")
    interazione.response.send_message.assert_awaited_once()
    assert interazione.response.send_message.await_args.args[0] == servizio.CANALE_NON_AMMESSO
    interazione.response.defer.assert_not_awaited()
    assert fonti.scaricati == []


async def test_attiva_chiede_la_conferma(repo):
    import cogs.nsfw.ricerca as ricerca

    cog = ricerca.NsfwCog(MagicMock())
    interazione = fake_interaction()
    interazione.guild.id = GUILD
    interazione.user.guild_permissions = discord.Permissions(manage_guild=True)
    await cog.attiva.callback(cog, interazione, True, False)
    assert not (await servizio.leggi(GUILD)).attivo
    await cog.attiva.callback(cog, interazione, True, True)
    assert (await servizio.leggi(GUILD)).attivo


async def test_segnala_dal_bottone_toglie_il_messaggio(repo, fonti, monkeypatch):
    import cogs.nsfw.ricerca as ricerca

    await _attiva()
    scelta = await servizio.scegli(GUILD, "amateur")
    await servizio.pubblica(_canale(), scelta, None)
    monkeypatch.setattr(ricerca, "_avvisa_owner", AsyncMock())
    interazione = fake_interaction()
    interazione.message = MagicMock(spec=discord.Message)
    interazione.message.id = 9055
    interazione.message.delete = AsyncMock()
    vista = ricerca.VistaSegnala()
    await vista.segnala.callback(interazione)
    interazione.message.delete.assert_awaited_once()
    assert await repo.e_bloccato("redgifs", "buono")


async def test_segnala_non_svuota_la_fonte_per_tutti(repo, fonti, monkeypatch):
    """Un server oltre il tetto di 24 ore blocca solo per sé: il contenuto resta negli altri server."""
    monkeypatch.setattr(servizio, "MAX_BLOCCHI_SERVER_GIORNO", 2)
    for i in range(2):
        await repo.blocca(f"h{i}", "redgifs", f"altro{i}", "segnalato", GUILD, 42)
    await _attiva()
    scelta = await servizio.scegli(GUILD, "amateur")
    await servizio.pubblica(_canale(), scelta, None)
    invio, ovunque = await servizio.segnala(9055, da=42)
    assert not ovunque
    assert not await repo.e_bloccato("redgifs", "buono")
    # Nel server che ha segnalato non torna (registro), negli altri sì.
    assert isinstance(await servizio.scegli(GUILD, "amateur"), str)
    await servizio.imposta_attivo(GUILD + 1, True, 1)
    await servizio.aggiungi_tag(GUILD + 1, "amateur")
    assert not isinstance(await servizio.scegli(GUILD + 1, "amateur"), str)

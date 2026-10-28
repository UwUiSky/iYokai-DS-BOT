"""
tests/test_user_app_messaggi_cog.py
===================================
SPEC B.2 (#107): menu sul messaggio e `/segnalibri` di iYokai App. Database vero; Discord finto con oggetti fedeli.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import cogs.user_app.messaggi as msg
from core.repositories.user_app_repo import UserAppRepository
from tests.support.discord_fakes import fake_interaction, fake_member, fake_message


@pytest.fixture(autouse=True)
def db(monkeypatch, clean_db):
    repo = UserAppRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(msg, "user_app_repo", repo)
    monkeypatch.setattr("core.user_app_impostazioni.user_app_repo", repo)
    return repo


@pytest.fixture
def cog():
    bot = MagicMock(tree=MagicMock())
    bot.bot_principale = None
    return msg.MessaggiCog(bot)


def _i(user_id=7):
    i = fake_interaction(user=fake_member(user_id=user_id))
    i.response.send_modal = AsyncMock()
    return i


def _m(contenuto="ciao a tutti", allegati=(), autore_id=9):
    m = fake_message(123, author=fake_member(user_id=autore_id), content=contenuto)
    m.embeds = []
    m.attachments = list(allegati)
    m.guild.id = 5
    m.channel.id = 6
    m.author.display_name = "Anna"
    return m


def _testo(i):
    return i.response.send_message.await_args.args[0]


def test_i_menu_sul_messaggio_sono_otto_e_dentro_il_limite_di_discord(cog):
    assert len(cog._menu) == 8 <= 15
    assert all(len(n) <= 32 for n in msg.NOMI_MENU)


async def test_segnalibro_salva_e_l_elenco_lo_mostra(cog, db):
    i = _i()
    await cog.menu_segnalibro(i, _m("un messaggio importante"))
    assert "numero" in _testo(i)
    i = _i()
    await cog.elenco.callback(cog, i, 0)
    corpo = i.response.send_message.await_args.kwargs["embed"].description
    assert "un messaggio importante" in corpo and "channels/5/6/123" in corpo
    i = _i(8)  # un altro utente non vede i miei
    await cog.elenco.callback(cog, i, 0)
    assert "non hai" in _testo(i).lower() or "Non hai" in _testo(i)


async def test_segnalibro_senza_testo_e_tetto(cog, db, monkeypatch):
    monkeypatch.setattr(msg, "MAX_SEGNALIBRI", 1)
    monkeypatch.setattr(db, "salva_segnalibro", AsyncMock(return_value=None))
    i = _i()
    await cog.menu_segnalibro(i, _m(""))
    assert "1" in _testo(i)


async def test_rimuovi_segnalibro_solo_il_proprio(cog, db):
    n = await db.salva_segnalibro(7, 5, 6, 1, "Anna", "x")
    i = _i(8)
    await cog.rimuovi.callback(cog, i, n)
    assert "Non trovo" in _testo(i)
    i = _i(7)
    await cog.rimuovi.callback(cog, i, n)
    assert "tolto" in _testo(i)


async def test_elenco_segnalibri_con_pagina_successiva(cog, db):
    for n in range(12):
        await db.salva_segnalibro(7, 5, 6, 100 + n, "Anna", f"messaggio {n}")
    i = _i()
    await cog.elenco.callback(cog, i, 0)
    embed = i.response.send_message.await_args.kwargs["embed"]
    assert embed.description.count("\n") == 9 and "dopo:" in embed.footer.text
    ultimo = int(embed.footer.text.split("dopo:")[1])
    i = _i()
    await cog.elenco.callback(cog, i, ultimo)
    assert i.response.send_message.await_args.kwargs["embed"].description.count("messaggio") == 2


async def test_traduci_usa_l_ai_fuori_dal_server_e_non_salva_in_cache(cog):
    i = _i()
    with patch.object(msg, "chiedi_ai_app", AsyncMock(return_value=("Hello everyone", None))) as chiedi:
        await cog.menu_traduci(i, _m("ciao a tutti"))
    args = chiedi.await_args.args
    assert args[0] == 7 and args[1] == "app_traduci" and args[2] == "traduzione" and args[3] == "ciao a tutti"
    assert i.followup.send.await_args.args[0] == "Hello everyone"
    assert i.followup.send.await_args.kwargs["ephemeral"] is True


async def test_traduci_senza_testo_e_ai_non_disponibile(cog):
    i = _i()
    await cog.menu_traduci(i, _m(""))
    assert "non ha testo" in _testo(i)
    i = _i()
    with patch.object(msg, "chiedi_ai_app", AsyncMock(return_value=(None, "L'AI è in manutenzione"))):
        await cog.menu_traduci(i, _m("ciao"))
    assert "manutenzione" in i.followup.send.await_args.args[0]


async def test_spiega_un_testo_lungo_diventa_riassunto(cog):
    i = _i()
    with patch.object(msg, "chiedi_ai_app", AsyncMock(return_value=("ok", None))) as chiedi:
        await cog.menu_spiega(i, _m("parola " * 200))
    assert chiedi.await_args.args[1] == "app_riassumi"
    i = _i()
    with patch.object(msg, "chiedi_ai_app", AsyncMock(return_value=("ok", None))) as chiedi:
        await cog.menu_spiega(i, _m("breve"))
    assert chiedi.await_args.args[1] == "app_spiega"


async def test_controlla_i_link(cog):
    i = _i()
    await cog.menu_link(i, _m("niente di che"))
    assert "non ci sono link" in _testo(i)
    i = _i()
    await cog.menu_link(i, _m("vai su https://free-nitro-gift.com e https://rust-lang.org"))
    testo = _testo(i)
    assert "free-nitro-gift.com" in testo and "⚠️" in testo and "✅" in testo


async def test_ricordamelo_apre_il_modulo_e_programma_il_promemoria(cog):
    i = _i()
    await cog.menu_ricordamelo(i, _m("da rivedere"))
    modulo = i.response.send_modal.await_args.args[0]
    assert isinstance(modulo, msg.RicordamiModal)

    modulo.durata._value = "2h"
    i2 = _i()
    with patch.object(msg, "programma_promemoria", AsyncMock(return_value=41)) as prog:
        await modulo.on_submit(i2)
    secondi, testo = prog.await_args.args[1], prog.await_args.args[2]
    assert secondi == 7200 and "da rivedere" in testo and "channels/5/6/123" in testo
    assert "41" in _testo(i2)


async def test_ricordamelo_rifiuta_durata_sbagliata_e_dm_spenti(cog, db):
    modulo = msg.RicordamiModal("https://x", "t")
    modulo.durata._value = "10s"
    i = _i()
    await modulo.on_submit(i)
    assert "almeno 1 minuto" in _testo(i)
    await db.imposta(7, "dm_ok", False)
    modulo.durata._value = "2h"
    i = _i(7)
    await modulo.on_submit(i)
    assert "messaggi diretti" in _testo(i)


async def test_citazione_manda_un_png(cog):
    i = _i()
    m = _m("una frase memorabile")
    m.author.display_avatar.read = AsyncMock(return_value=b"")
    await cog.menu_citazione(i, m)
    assert i.followup.send.await_args.kwargs["file"].filename == "citazione.png"
    assert i.followup.send.await_args.kwargs["ephemeral"] is True
    i = _i()
    await cog.menu_citazione(i, _m(""))
    assert "non ha testo" in _testo(i)


async def test_citazione_pubblica_se_la_persona_l_ha_scelto(cog, db):
    await db.imposta(7, "risposte_private", False)
    i = _i(7)
    m = _m("frase")
    m.author.display_avatar.read = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=404), "x"))
    await cog.menu_citazione(i, m)
    assert i.followup.send.await_args.kwargs["ephemeral"] is False


async def test_meme_serve_un_allegato_immagine(cog):
    i = _i()
    await cog.menu_meme(i, _m("niente"))
    assert "immagine" in _testo(i)
    allegato = MagicMock(spec=discord.Attachment)
    allegato.content_type, allegato.size = "image/png", 1000
    i = _i()
    await cog.menu_meme(i, _m("foto", [allegato]))
    assert isinstance(i.response.send_modal.await_args.args[0], msg.MemeModal)


async def test_meme_modulo_genera_l_immagine(cog):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (200, 200), (10, 20, 30)).save(buffer, format="PNG")
    allegato = MagicMock(spec=discord.Attachment)
    allegato.read = AsyncMock(return_value=buffer.getvalue())
    modulo = msg.MemeModal(allegato)
    modulo.alto._value, modulo.basso._value = "ciao", ""
    i = _i()
    await modulo.on_submit(i)
    assert i.followup.send.await_args.kwargs["file"].filename == "meme.png"
    modulo.alto._value = ""
    i = _i()
    await modulo.on_submit(i)
    assert "almeno un testo" in _testo(i)


async def test_segnala_alla_rete_apre_la_richiesta_per_lo_staff(cog, monkeypatch):
    principale = MagicMock()
    i = _i()
    modulo = msg.SegnalaModal(_m("clicca qui per nitro gratis", autore_id=99), principale)
    modulo.motivo._value = "è una truffa"
    apri = AsyncMock(return_value=SimpleNamespace(numero=12, thread_id=1))
    monkeypatch.setattr(msg, "apri_richiesta", apri)
    await modulo.on_submit(i)
    assert apri.await_args.args[0] is principale
    assert "ID 99" in apri.await_args.args[5] and "truffa" in apri.await_args.args[5]
    assert "12" in i.followup.send.await_args.args[0]


async def test_segnala_senza_staff_e_il_proprio_messaggio(cog):
    i = _i()
    modulo = msg.SegnalaModal(_m("x"), None)
    modulo.motivo._value = "è una truffa"
    await modulo.on_submit(i)
    assert "non è attiva" in _testo(i)
    i = _i(9)
    await cog.menu_segnala(i, _m("mio", autore_id=9))
    assert "tuo messaggio" in _testo(i)
    i = _i(7)
    await cog.menu_segnala(i, _m("altrui", autore_id=9))
    assert isinstance(i.response.send_modal.await_args.args[0], msg.SegnalaModal)

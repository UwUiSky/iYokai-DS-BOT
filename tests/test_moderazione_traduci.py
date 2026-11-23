"""
tests/test_moderazione_traduci.py
=================================
Bottone «Traduci» sui messaggi pubblici di moderazione (#115, D110): bottone persistente, testi del bot per it/en,
snodo AI per le altre lingue, AI spenta detta chiaramente, tetto di 5 al minuto, nessuna menzione.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import i18n
from core import moderazione_traduci as mt
from core.ai_servizio import AINonDisponibile, RispostaAI


@pytest.fixture(autouse=True)
def pulito():
    mt.azzera_tetti()
    yield
    mt.azzera_tetti()


def _embed(titolo="t", descr="d", campi=(), piede=""):
    e = discord.Embed(title=titolo, description=descr, color=0x123456)
    for n, v in campi:
        e.add_field(name=n, value=v, inline=False)
    if piede:
        e.set_footer(text=piede)
    return e


def _interazione(locale="tr", embeds=None, content="", guild_id=666, user_id=7):
    i = MagicMock()
    i.locale = discord.Locale(locale)
    i.guild = MagicMock(id=guild_id)
    i.guild_id = guild_id
    i.channel_id = 11
    i.user = MagicMock(id=user_id)
    i.message = MagicMock(embeds=embeds if embeds is not None else [_embed()], content=content)
    i.response.send_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


@pytest.fixture
def lingua_server(monkeypatch):
    def imposta(codice):
        async def f(guild_id):
            return codice
        monkeypatch.setattr(i18n, "lingua_server", f)
    imposta("en")
    return imposta


@pytest.fixture
def ai(monkeypatch):
    servizio = MagicMock()

    async def richiedi(r):
        elenco = json.loads(r.testo)
        return RispostaAI(testo=json.dumps([f"TR:{x}" for x in elenco]))

    servizio.richiedi = AsyncMock(side_effect=richiedi)
    monkeypatch.setattr(mt, "servizio_ai", lambda: servizio)
    return servizio


# ---------------------------------------------------------------- struttura
def test_scomponi_e_ricompone_senza_perdere_nulla():
    msg = MagicMock(embeds=[_embed("Titolo", "Descr", [("Utente", "Mario"), ("Motivo", "spam")], "piede")], content="")
    c = mt.scomponi(msg)
    testi = mt.testi_di(c)
    assert testi == ["Titolo", "Descr", "piede", "Utente", "Mario", "Motivo", "spam"]
    nuovo = mt.con_testi(c, [x.upper() for x in testi])
    e = mt.a_embed(nuovo)[0]
    assert (e.title, e.description) == ("TITOLO", "DESCR")
    assert [(f.name, f.value) for f in e.fields] == [("UTENTE", "MARIO"), ("MOTIVO", "SPAM")]
    assert e.footer.text == "PIEDE"


def test_senza_embed_vale_il_contenuto():
    c = mt.scomponi(MagicMock(embeds=[], content="Blocco attivo"))
    assert mt.testi_di(c) == ["Blocco attivo"]


def test_embed_tagliati_ai_tetti():
    grosso = _embed("t" * 300, "d" * 5000, [(f"n{i}", "v" * 1500) for i in range(25)])
    risultato = mt.a_embed(mt.scomponi(MagicMock(embeds=[grosso], content="")))
    totale = sum(len(e) for e in risultato)
    assert totale <= 6000 and len(risultato[0].title) <= 256


def test_leggi_traduzioni_rifiuta_risposte_storte():
    assert mt.leggi_traduzioni('["a", "b"]', 2) == ["a", "b"]
    assert mt.leggi_traduzioni('Ecco: ```["a"]```', 1) == ["a"]
    assert mt.leggi_traduzioni('["a"]', 2) is None
    assert mt.leggi_traduzioni('[1, 2]', 2) is None
    assert mt.leggi_traduzioni("niente", 1) is None


def test_tetto_cinque_al_minuto():
    assert all(mt.consenti(1, 100.0 + i) for i in range(5))
    assert mt.consenti(1, 106.0) is False
    assert mt.consenti(2, 106.0) is True
    assert mt.consenti(1, 161.0) is True


def test_riconosce_un_testo_fisso_del_bot():
    esatto = i18n.t("automod_avviso_titolo", "it")
    assert mt.riconosci(esatto, "it") == ("automod_avviso_titolo", {})
    assert mt.riconosci("testo che il bot non ha mai scritto in nessun posto", "it") is None


def test_riconosce_un_modello_con_segnaposto():
    scritto = i18n.t("casesystem_chat_pronta", "it", n=5, canale="#generale")
    chiave, valori = mt.riconosci(scritto, "it")
    assert chiave == "casesystem_chat_pronta" and valori == {"n": "5", "canale": "#generale"}


# ---------------------------------------------------------------- bottone
async def test_il_bottone_e_persistente_con_custom_id_fisso():
    vista = mt.VistaTraduci()
    assert vista.timeout is None and vista.is_persistent()
    assert [b.custom_id for b in vista.children] == [mt.CUSTOM_ID]
    assert len(mt.CUSTOM_ID) <= 100


async def test_lingua_del_bot_usa_i_testi_del_bot_senza_ai(lingua_server, ai):
    lingua_server("it")
    i = _interazione("en-US", embeds=[_embed(i18n.t("automod_avviso_titolo", "it"), "descrizione del moderatore")])
    await mt.rispondi_traduzione(i)
    corpo = i.followup.send.await_args.kwargs
    assert corpo["ephemeral"] is True
    assert corpo["embeds"][0].title == "Message removed"
    # il testo libero del moderatore non e' del bot: passa dall'AI, il testo fisso no
    inviato = json.loads(ai.richiedi.await_args.args[0].testo)
    assert inviato == ["descrizione del moderatore"]


async def test_lingua_diversa_passa_dallo_snodo_ai(lingua_server, ai):
    i = _interazione("tr", embeds=[_embed("Ban", "spam", [("Motivo", "reklam")])])
    await mt.rispondi_traduzione(i)
    corpo = i.followup.send.await_args.kwargs
    assert corpo["embeds"][0].title == "TR:Ban"
    assert corpo["embeds"][0].fields[0].value == "TR:reklam"
    r = ai.richiedi.await_args.args[0]
    assert (r.tipo, r.funzione, r.guild_id, r.messaggi_utenti) == ("traduzione", "traduci", 666, True)
    assert "Turkish" in r.istruzioni or "tr" in r.istruzioni


async def test_risposta_senza_menzioni(lingua_server, ai):
    i = _interazione("tr")
    await mt.rispondi_traduzione(i)
    m = i.followup.send.await_args.kwargs["allowed_mentions"]
    assert m.everyone is False and m.roles is False and m.users is False


async def test_ai_spenta_lo_dice_chiaramente(lingua_server, monkeypatch):
    servizio = MagicMock()
    servizio.richiedi = AsyncMock(side_effect=AINonDisponibile("spenta"))
    monkeypatch.setattr(mt, "servizio_ai", lambda: servizio)
    i = _interazione("tr")
    await mt.rispondi_traduzione(i)
    testo = i.followup.send.await_args.args[0] if i.followup.send.await_args.args else i.followup.send.await_args.kwargs["content"]
    assert "AI" in testo and i.followup.send.await_args.kwargs["ephemeral"] is True


async def test_errore_imprevisto_dell_ai_non_solleva(lingua_server, monkeypatch):
    servizio = MagicMock()
    servizio.richiedi = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(mt, "servizio_ai", lambda: servizio)
    i = _interazione("tr")
    await mt.rispondi_traduzione(i)
    i.followup.send.assert_awaited_once()


async def test_stessa_lingua_del_server_non_traduce(lingua_server, ai):
    lingua_server("it")
    i = _interazione("it")
    await mt.rispondi_traduzione(i)
    ai.richiedi.assert_not_called()
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_tetto_per_persona_nel_bottone(lingua_server, ai):
    for _ in range(5):
        await mt.rispondi_traduzione(_interazione("tr"))
    i = _interazione("tr")
    await mt.rispondi_traduzione(i)
    assert ai.richiedi.await_count == 5
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_messaggio_senza_testo_o_fuori_dal_server(lingua_server, ai):
    vuoto = _interazione("tr", embeds=[], content="")
    await mt.rispondi_traduzione(vuoto)
    vuoto.response.send_message.assert_awaited_once()
    fuori = _interazione("tr")
    fuori.guild = None
    await mt.rispondi_traduzione(fuori)
    fuori.response.send_message.assert_awaited_once()
    ai.richiedi.assert_not_called()

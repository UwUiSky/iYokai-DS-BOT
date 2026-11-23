"""
tests/test_auto_foto_controllo_fun017.py
========================================
FUN-017 (D122): controllo automatico delle foto delle auto per contenuti per adulti, dallo snodo AI. Foto per adulti:
rifiutata (o tolta alla prossima visualizzazione, se gia' salvata). Controllo non disponibile: la foto passa come prima
(D123). Database vero, fornitore AI finto, nessuna rete.
"""

from unittest.mock import AsyncMock

import pytest

from cogs.fun import auto as cog_auto
from cogs.fun.auto import AutoCog
from core import ai_moderazione_immagini as mod, auto_foto_controllo as controllo
from core.ai_providers import ErroreFornitore, TrasportoHTTP
from core.repositories.ai_repo import AiRepository
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_member
from tests.test_auto_fun import G, _allegato, _i, png, r  # noqa: F401

TIPO = ("moderazione_immagine",)


@pytest.fixture
def ai(r, monkeypatch, clean_db):  # noqa: F811
    """Un servizio AI con un fornitore di moderazione finto, usato dal controllo delle foto."""
    def costruisci(fornitori=None, adulti=False):
        trasporto = TrasportoFinto()
        trasporto.moderazione["alfa"] = "adulti" if adulti else "ok"
        servizio, _ = servizio_finto(
            AiRepository(lambda: clean_db), fornitori=fornitori if fornitori is not None else [fornitore(tipi=TIPO)], trasporto=trasporto,
        )
        monkeypatch.setattr(controllo, "servizio_ai", lambda: servizio)
        return trasporto
    return costruisci


async def _comando(r, monkeypatch, dati=None):  # noqa: F811
    from core import allegati_tipo_logic as t

    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")

    async def finto_esamina(d, nome, ctype, guild_id, **k):
        return ("foto.png", png((5, 5, 5), (800, 600))), t.decidi(d, nome, ctype)

    monkeypatch.setattr(cog_auto, "esamina_allegato", finto_esamina)
    cog = AutoCog(AsyncMock())
    cog._rimborsi.cancel()
    i = _i(fake_member(1))
    await AutoCog.foto.callback(cog, i, "risaia", _allegato(dati or png()))
    return i


# ------------------------------------------------------------------ lettura della risposta
def test_la_risposta_del_fornitore_si_legge_per_categorie_e_punteggi():
    assert mod.e_per_adulti({"results": [{"categories": {"sexual": True}, "category_scores": {}}]}) is True
    assert mod.e_per_adulti({"results": [{"categories": {"sexual": False}, "category_scores": {"sexual": 0.7}}]}) is True
    assert mod.e_per_adulti({"results": [{"categories": {}, "category_scores": {"sexual/minors": 0.3}}]}) is True
    assert mod.e_per_adulti({"results": [{"categories": {"violence": True}, "category_scores": {"sexual": 0.01}}]}) is False
    for rotta in ({}, {"results": []}, {"results": [{"categories": "x"}]}, None):
        with pytest.raises(ValueError):
            mod.e_per_adulti(rotta)


async def test_il_trasporto_manda_la_foto_e_traduce_la_risposta(monkeypatch):
    visto = {}

    async def finto_post(self, f, percorso, corpo):
        visto.update(percorso=percorso, corpo=corpo)
        return {"results": [{"categories": {"sexual": True}, "category_scores": {}}]}, {}

    monkeypatch.setattr(TrasportoHTTP, "_post", finto_post)
    esito = await TrasportoHTTP().moderazione_immagine(fornitore(tipi=TIPO), png())
    assert esito.testo == "adulti" and visto["percorso"] == "/moderations"
    assert visto["corpo"]["input"][0]["image_url"]["url"].startswith("data:image/png;base64,")

    async def rotto(self, f, percorso, corpo):
        return {"nonsenso": 1}, {}

    monkeypatch.setattr(TrasportoHTTP, "_post", rotto)
    with pytest.raises(ErroreFornitore):
        await TrasportoHTTP().moderazione_immagine(fornitore(tipi=TIPO), png())


# ------------------------------------------------------------------ snodo
async def test_lo_snodo_dice_adulti_o_pulita(ai):
    t = ai(adulti=True)
    assert await controllo.controlla(png(), G) == controllo.ADULTI
    assert t.chiamate and t.chiamate[0][0] == "alfa"  # la foto e' andata al fornitore, passando dallo snodo
    ai(adulti=False)
    assert await controllo.controlla(png(), G) == controllo.PULITA


async def test_senza_fornitore_di_moderazione_il_controllo_non_c_e(ai):
    ai(fornitori=[fornitore()])  # solo chat: nessuno sa moderare le immagini
    assert await controllo.controlla(png(), G) == controllo.NON_DISPONIBILE
    ai(fornitori=[])
    assert await controllo.controlla(png(), G) == controllo.NON_DISPONIBILE


async def test_un_fornitore_che_addestra_sui_dati_non_vede_mai_la_foto(ai):
    t = ai(fornitori=[fornitore(tipi=TIPO, addestra=True)], adulti=True)
    assert await controllo.controlla(png(), G) == controllo.NON_DISPONIBILE
    assert t.chiamate == []


async def test_un_errore_del_servizio_vale_non_disponibile(ai):
    t = ai()
    t.errori["alfa"] = ErroreFornitore(500)
    assert await controllo.controlla(png(), G) == controllo.NON_DISPONIBILE


# ------------------------------------------------------------------ comando /auto foto
async def test_la_foto_per_adulti_e_rifiutata_e_non_si_salva(r, ai, monkeypatch):  # noqa: F811
    ai(adulti=True)
    i = await _comando(r, monkeypatch)
    assert await r.a.foto(G, 1, "risaia") is None
    testo = i.followup.send.await_args.args[0]
    assert "adulti" in testo.lower() and i.followup.send.await_args.kwargs["ephemeral"] is True
    assert "un'altra" in testo or "another" in testo.lower()  # chiede un'altra foto


async def test_la_foto_pulita_passa_ed_e_segnata_come_controllata(r, ai, monkeypatch):  # noqa: F811
    ai(adulti=False)
    await _comando(r, monkeypatch)
    foto = await r.a.foto(G, 1, "risaia")
    assert foto is not None and foto[2] is True


async def test_la_foto_passa_se_l_ai_non_c_e(r, ai, monkeypatch):  # noqa: F811
    ai(fornitori=[])
    i = await _comando(r, monkeypatch)
    foto = await r.a.foto(G, 1, "risaia")
    assert foto is not None and foto[2] is False  # salvata, da ricontrollare quando l'AI tornera'
    assert "adulti" not in i.followup.send.await_args.args[0].lower()


# ------------------------------------------------------------------ foto gia' salvate
async def test_una_foto_gia_salvata_per_adulti_si_toglie_alla_visualizzazione(r, ai):  # noqa: F811
    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")
    await r.a.imposta_foto(G, 1, "risaia", png(), "a" * 64)  # salvata prima del controllo: mai controllata
    ai(adulti=True)
    assert await cog_auto.foto_visibile(G, await r.a.auto(G, 1, "risaia")) is None
    assert await r.a.foto(G, 1, "risaia") is None and not (await r.a.auto(G, 1, "risaia")).con_foto


async def test_una_foto_gia_salvata_pulita_si_segna_e_non_si_ricontrolla(r, ai):  # noqa: F811
    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")
    await r.a.imposta_foto(G, 1, "risaia", png(), "a" * 64)
    t = ai(adulti=False)
    auto = await r.a.auto(G, 1, "risaia")
    assert await cog_auto.foto_visibile(G, auto) is not None
    assert (await r.a.foto(G, 1, "risaia"))[2] is True
    n = len(t.chiamate)
    assert await cog_auto.foto_visibile(G, auto) is not None
    assert len(t.chiamate) == n  # gia' controllata: nessuna seconda chiamata


async def test_una_foto_gia_salvata_senza_ai_resta_visibile_e_da_controllare(r, ai):  # noqa: F811
    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")
    await r.a.imposta_foto(G, 1, "risaia", png(), "a" * 64)
    ai(fornitori=[])
    assert await cog_auto.foto_visibile(G, await r.a.auto(G, 1, "risaia")) is not None
    assert (await r.a.foto(G, 1, "risaia"))[2] is False


async def test_sostituire_la_foto_riparte_da_non_controllata(r):  # noqa: F811
    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")
    await r.a.imposta_foto(G, 1, "risaia", png(), "a" * 64, controllata=True)
    assert (await r.a.foto(G, 1, "risaia"))[2] is True
    await r.a.imposta_foto(G, 1, "risaia", png((1, 1, 1)), "b" * 64)
    assert (await r.a.foto(G, 1, "risaia"))[2] is False

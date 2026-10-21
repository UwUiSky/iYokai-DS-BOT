"""
tests/test_nsfw_filter_logic.py
===============================
NF-23 (#94): lista vietata fissa, lista permessa del server, fonti ammesse,
canale vietato ai minori, impronta delle immagini.
"""

from unittest.mock import MagicMock

import discord
import pytest

from core import nsfw_filter_logic as f


def _elemento(**kw):
    base = dict(
        fonte="redgifs", id_fonte="abc123", tag=("amateur", "couple"), testo="", autore="creatrice",
        verificato=True, url_pagina="https://www.redgifs.com/watch/abc123",
        url_anteprima="https://media.redgifs.com/Abc123-poster.jpg",
    )
    base.update(kw)
    return f.ElementoFonte(**base)


@pytest.mark.parametrize(
    "testo",
    [
        "loli", "Teen", "teenager", "schoolgirl", "s c h o o l g i r l", "l.o.l.i", "l0l1", "16yo", "15 anni",
        "17 years", "barely legal", "Minorenne", "ragazzina", "petite", "kid", "cp", "babysitter", "ddlg",
        "età: 16 anni",
    ],
)
def test_lista_vietata_minori(testo):
    assert f.motivo_vietato(testo) == "minori"


@pytest.mark.parametrize(
    "testo, categoria",
    [
        ("rape", "violenza o consenso"),
        ("drugged", "violenza o consenso"),
        ("stepsister", "violenza o consenso"),
        ("sleeping", "violenza o consenso"),
        ("hidden cam", "persone reali senza consenso"),
        ("upskirt", "persone reali senza consenso"),
        ("deepfake", "persone reali senza consenso"),
        ("celebrity", "persone reali senza consenso"),
        ("zoo", "animali"),
        ("bestiality", "animali"),
        ("hentai", "disegnati o generati (età non dichiarabile)"),
        ("AI generated", "disegnati o generati (età non dichiarabile)"),
        ("3d", "disegnati o generati (età non dichiarabile)"),
        ("cosplay", "disegnati o generati (età non dichiarabile)"),
    ],
)
def test_lista_vietata_altre_categorie(testo, categoria):
    assert f.motivo_vietato(testo) == categoria


@pytest.mark.parametrize("testo", ["amateur", "couple", "milf", "redhead", "lingerie", "18", "25 years", "tattoo"])
def test_testi_leciti_passano(testo):
    assert f.motivo_vietato(testo) is None


def test_valida_tag():
    assert f.valida_tag("  Red Head ") == ("red head", None)
    tag, errore = f.valida_tag("teen")
    assert tag is None and "lista vietata" in errore
    assert f.valida_tag("x")[0] is None
    assert f.valida_tag("a" * 33)[0] is None


def test_elemento_lecito_passa():
    assert f.motivo_scarto(_elemento(), {"amateur"}) is None


def test_serve_un_tag_della_lista_permessa():
    assert "lista permessa" in f.motivo_scarto(_elemento(), {"lingerie"})
    assert "lista permessa" in f.motivo_scarto(_elemento(), set())


def test_fonte_non_verificata_scartata():
    assert "età e consenso" in f.motivo_scarto(_elemento(verificato=False), {"amateur"})


def test_fonte_sconosciuta_scartata():
    assert f.motivo_scarto(_elemento(fonte="rule34"), {"amateur"}) == "fonte non ammessa"


def test_indirizzo_fuori_dalla_fonte_scartato():
    e = _elemento(url_anteprima="https://evil.example/x.jpg")
    assert f.motivo_scarto(e, {"amateur"}) == "indirizzo fuori dalla fonte"
    e = _elemento(url_pagina="http://www.redgifs.com/watch/abc123")
    assert f.motivo_scarto(e, {"amateur"}) == "indirizzo fuori dalla fonte"


@pytest.mark.parametrize("campo", ["tag", "testo", "autore"])
def test_vietato_in_qualsiasi_campo(campo):
    valore = ("amateur", "teen") if campo == "tag" else "schoolgirl"
    assert f.motivo_scarto(_elemento(**{campo: valore}), {"amateur"}).startswith("lista vietata")


def test_filtra_tiene_solo_i_leciti():
    buoni = _elemento()
    assert f.filtra([buoni, _elemento(tag=("amateur", "loli")), _elemento(verificato=False)], {"amateur"}) == [buoni]


def test_canale_ammesso_solo_se_nsfw():
    canale = MagicMock(spec=discord.TextChannel)
    canale.is_nsfw.return_value = True
    assert f.canale_ammesso(canale)
    canale.is_nsfw.return_value = False
    assert not f.canale_ammesso(canale)
    thread = MagicMock(spec=discord.Thread)
    thread.is_nsfw.return_value = True
    assert f.canale_ammesso(thread)
    vocale = MagicMock(spec=discord.VoiceChannel)
    vocale.is_nsfw.return_value = True
    assert not f.canale_ammesso(vocale)
    assert not f.canale_ammesso(None)


def test_impronta_sha256():
    assert f.impronta(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_leggi_redgifs():
    payload = {
        "gifs": [
            {"id": "verdeacqua", "tags": ["Amateur"], "niches": ["couples"], "verified": True, "userName": "u",
             "urls": {"poster": "https://media.redgifs.com/Verdeacqua-poster.jpg"}},
            {"id": "nonpubblicato", "published": False, "urls": {"poster": "https://media.redgifs.com/x.jpg"}},
            {"id": "SENZA/ID!", "urls": {"poster": "https://media.redgifs.com/x.jpg"}},
            {"id": "senzaurl"},
            {"id": "nonverificato", "urls": {"thumbnail": "https://media.redgifs.com/y.jpg"}},
            "spazzatura",
        ]
    }
    elementi = f.leggi_redgifs(payload)
    assert [e.id_fonte for e in elementi] == ["verdeacqua", "nonverificato"]
    assert elementi[0].tag == ("Amateur", "couples")
    assert elementi[0].verificato and not elementi[1].verificato
    assert elementi[0].url_pagina == "https://www.redgifs.com/watch/verdeacqua"
    assert f.leggi_redgifs({"gifs": None}) == [] and f.leggi_redgifs([]) == []


# Rilievi del cacciatore-bug (r9nsfw): la lista vietata si aggirava.
@pytest.mark.parametrize(
    "testo",
    [
        "lоli",  # "o" cirillica
        "schоolgirl",
        "te​en",  # spazio a larghezza zero
        "t­een",  # trattino morbido
        "hotteen",  # tag composti
        "amateurteen",
        "highschool",
        "t-e-e-n",
        "t_e_e_n",
        "kiddo",
        "nymphet",
        "prepubescent",
        "sixteen",
        "sedicenne",
        "١٦yo",  # cifre arabe
    ],
)
def test_lista_vietata_non_si_aggira(testo):
    assert f.motivo_vietato(testo) is not None


@pytest.mark.parametrize("testo", ["rapist", "cnc"])
def test_sinonimi_di_violenza(testo):
    assert f.motivo_vietato(testo) == "violenza o consenso"


def test_tag_permesso_con_caratteri_nascosti_rifiutato():
    assert f.valida_tag("te​en")[0] is None
    assert f.valida_tag("lоli")[0] is None


def test_leggi_redgifs_tag_non_in_lista_non_rompe():
    payload = {"gifs": [{"id": "abc", "tags": "teen", "niches": {"x": 1}, "verified": True,
                         "urls": {"poster": "https://media.redgifs.com/a.jpg"}}]}
    [elemento] = f.leggi_redgifs(payload)
    assert elemento.tag == ()

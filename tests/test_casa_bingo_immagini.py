"""ECO-112 (bingo) ed ECO-087 (casa) come immagini (D127): misura fissa, righe complete, mobili posseduti. Nessuna rete."""
import asyncio
import io

import pytest
from PIL import Image

from core import bingo_image as bi
from core import casa_image as ci
from core import mondo_logic as ml

CARTELLA = [[1, 2, 3, 4, 5], [11, 12, 13, 14, 15], [21, 22, 23, 24, 25]]


def _apri(png):
    img = Image.open(io.BytesIO(png))
    img.load()
    return img


def test_cartella_ha_misura_fissa_e_i_numeri_usciti_cambiano_l_immagine():
    vuota = _apri(bi.render_cartella(CARTELLA, set()))
    parziale = _apri(bi.render_cartella(CARTELLA, {1, 12}))
    assert vuota.size == parziale.size == (bi.LARGHEZZA, bi.ALTEZZA) and vuota.format == "PNG"
    assert vuota.tobytes() != parziale.tobytes()
    # un numero uscito è cerchiato in rosso al centro della sua cella
    centro = (bi.MARGINE + 48, bi.MARGINE + 18)  # in alto nel cerchio, sopra il numero
    assert parziale.getpixel(centro) == bi.USCITO and vuota.getpixel(centro) != bi.USCITO


def test_la_riga_completa_e_evidenziata():
    senza = _apri(bi.render_cartella(CARTELLA, {1, 2, 3, 4}))
    completa = _apri(bi.render_cartella(CARTELLA, {1, 2, 3, 4, 5}))
    bordo = (bi.MARGINE + 4 + 50, bi.MARGINE + 4)  # bordo alto della prima cella
    assert completa.getpixel(bordo) == bi.RIGA_COMPLETA and senza.getpixel(bordo) != bi.RIGA_COMPLETA


@pytest.mark.parametrize("cattiva", [[[1, 2, 3]], CARTELLA[:2], [[0, 2, 3, 4, 5]] + CARTELLA[1:], [[99, 2, 3, 4, 5]] + CARTELLA[1:]])
def test_cartella_non_valida_non_si_disegna(cattiva):
    with pytest.raises(ValueError):
        bi.render_cartella(cattiva, set())


def test_casa_ha_misura_fissa_e_mostra_solo_i_mobili_posseduti():
    nomi = {n: n.upper() for n in ml.MOBILI}
    vuota = _apri(ci.render_casa(set(), nomi))
    con_letto = _apri(ci.render_casa({"letto"}, nomi))
    assert vuota.size == con_letto.size == (ci.LARGHEZZA, ci.ALTEZZA)
    posto = ml.MOBILI["letto"][2]
    x, y = ci.MARGINE + (posto % ci.COLONNE) * ci.CELLA + 12, ci.MARGINE + (posto // ci.COLONNE) * ci.CELLA + 12
    assert con_letto.getpixel((x, y)) == ci.COLORI["letto"] and vuota.getpixel((x, y)) == ci.VUOTO
    tutti = _apri(ci.render_casa(set(ml.MOBILI), nomi))
    assert tutti.size == vuota.size


def test_casa_regge_etichette_lunghe_emoji_e_mobili_sconosciuti():
    png = ci.render_casa({"letto", "inventato"}, {"letto": "😀" * 80, "inventato": "x"})
    assert _apri(png).size == (ci.LARGHEZZA, ci.ALTEZZA)


# ---- i comandi: immagine in uscita e ripiego testuale ----
from types import SimpleNamespace

import cogs.fun.sala as sala
import cogs.leveling.mondo as mondo
from core import sala_logic as sl


def _interazione():
    cat = {"msg": [], "kw": []}

    async def _invia(testo=None, **kw):
        cat["msg"].append(testo)
        cat["kw"].append(kw)

    async def _defer(**kw):
        cat["defer"] = kw

    i = SimpleNamespace(
        guild=SimpleNamespace(id=1), user=SimpleNamespace(id=9), locale=None,
        response=SimpleNamespace(send_message=_invia, defer=_defer, is_done=lambda: False),
        followup=SimpleNamespace(send=_invia),
    )
    return i, cat


@pytest.fixture
def casa(monkeypatch):
    async def _no(i):
        return False

    async def _casa(u):
        return {"letto", "gatto"}

    async def _gettoni(u):
        return 7

    monkeypatch.setattr(mondo, "_comando_rifiutato", _no)
    monkeypatch.setattr(mondo.mondo_repo, "casa", _casa, raising=False)
    monkeypatch.setattr(mondo.mondo_repo, "gettoni", _gettoni, raising=False)


async def test_casa_manda_l_immagine_a_misura_fissa_solo_a_chi_la_chiede(casa):
    i, cat = _interazione()
    await mondo.MondoCog.casa.callback(SimpleNamespace(), i, None)
    f = cat["kw"][-1]["file"]
    assert f.filename == "casa.png" and cat["kw"][-1]["ephemeral"] is True and cat["defer"]["ephemeral"] is True
    f.fp.seek(0)
    assert _apri(f.fp.read()).size == (ci.LARGHEZZA, ci.ALTEZZA)
    assert "7" in cat["msg"][-1]


async def test_casa_ricade_sul_testo_se_l_immagine_non_si_disegna(casa, monkeypatch):
    async def _rotto(func, *args):
        raise OSError("Pillow rotto")

    monkeypatch.setattr(mondo, "run_image_task", _rotto)
    i, cat = _interazione()
    await mondo.MondoCog.casa.callback(SimpleNamespace(), i, None)
    assert "file" not in cat["kw"][-1] and "🛏️" in cat["msg"][-1]


async def test_cartella_del_bingo_come_immagine_e_ripiego_testuale(monkeypatch):
    vista = sala.VistaBingo([9, 10], {9: CARTELLA, 10: CARTELLA}, {"cartella": "La mia", "bingo": "BINGO"})
    vista.estratti = {1, 2}
    i, cat = _interazione()
    await vista.vista_cartella.callback(i)
    assert cat["kw"][-1]["file"].filename == "cartella.png" and cat["defer"]["ephemeral"] is True

    async def _rotto(func, *args):
        raise OSError("Pillow rotto")

    monkeypatch.setattr(sala, "run_image_task", _rotto)
    await vista.vista_cartella.callback(i)
    assert "file" not in cat["kw"][-1] and sl.testo_cartella(CARTELLA, {1, 2}) in cat["msg"][-1]

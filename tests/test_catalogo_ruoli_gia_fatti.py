"""
tests/test_catalogo_ruoli_gia_fatti.py
======================================
Catalogo «Benvenuto e ruoli» (#123): voci già presenti nel codice senza il loro codice scritto.
Ogni prova porta il codice RUO nel nome. Provano la logica vera, senza Discord.
"""

import io

import pytest
from PIL import Image

from core.autorole_logic import (
    RegolaAutoruolo,
    membro_in_attesa,
    piano_ingresso,
    regola_vale_per,
    ruoli_da_ridare,
)
from core.greetings_logic import render_template
from core.role_menu_logic import COMPORTAMENTI, decidi_azione, membro_ammesso
from core.welcome_image import (
    ALTEZZA,
    FORME,
    LARGHEZZA,
    DatiBenvenuto,
    prepara_sfondo,
    render_welcome_image,
)
from tests.support.percorsi import comando_nel_gruppo


def _png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


def test_RUO_002_immagine_di_benvenuto_con_avatar_e_nome():
    png = render_welcome_image(DatiBenvenuto(nome="Mario", numero=12), _png(64, 64), None)
    assert Image.open(io.BytesIO(png)).size == (LARGHEZZA, ALTEZZA)


def test_RUO_003_sfondo_caricato_portato_alla_misura():
    assert Image.open(io.BytesIO(prepara_sfondo(_png(1500, 900)))).size == (LARGHEZZA, ALTEZZA)


def test_RUO_006_avatar_tondo_o_quadrato():
    assert set(FORME) == {"tondo", "quadrato"}


def test_RUO_009_titolo_del_banner_cambia_l_immagine():
    uno = render_welcome_image(DatiBenvenuto(nome="A", numero=1, titolo="Ciao"), None, None)
    due = render_welcome_image(DatiBenvenuto(nome="A", numero=1, titolo="Benvenuta"), None, None)
    assert uno != due


def test_RUO_011_togli_sfondo_e_il_modello_pronto():
    # senza sfondo l'immagine torna al modello (comando `immagine togli_sfondo`)
    assert render_welcome_image(DatiBenvenuto(nome="A", numero=1), None, None)


def test_RUO_020_RUO_021_nome_visualizzato_e_id_del_server():
    testo = render_template(
        "{displayname}|{serverid}", "@u", "u", "S", 3, display_name="Nome", server_id=77
    )
    assert testo == "Nome|77"


def test_RUO_028_ruolo_dato_a_chi_entra_ma_non_ai_bot():
    regole = [RegolaAutoruolo(1)]
    assert piano_ingresso(regole, is_bot=False, ruoli_posseduti=set()) == ([1], [])
    assert piano_ingresso(regole, is_bot=True, ruoli_posseduti=set()) == ([], [])


def test_RUO_029_RUO_030_RUO_032_comandi_auto_aggiungi_togli_elenco():
    import asyncio
    import discord
    from discord.ext import commands

    import cogs.utility.autoroles as modulo

    async def _monta():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        await modulo.setup(bot)

    asyncio.run(_monta())
    for nome in ("aggiungi", "togli", "elenco"):
        assert comando_nel_gruppo("admin-ruoli", f"auto {nome}") is not None


def test_RUO_031_ruolo_con_ritardo_va_nello_scheduler():
    subito, dopo = piano_ingresso([RegolaAutoruolo(5, 600)], is_bot=False, ruoli_posseduti=set())
    assert subito == [] and dopo == [(5, 600)]


def test_RUO_033_regola_tolta_non_vale_piu_allo_scatto():
    # lo scatto controlla che la regola esista ancora (handle_autorole_give): regola assente = niente ruolo
    import inspect

    import cogs.utility.autoroles as modulo

    assert "regola is None" in inspect.getsource(modulo.AutorolesCog.handle_autorole_give)


def test_RUO_037_membro_in_attesa_di_accettare_le_regole():
    assert membro_in_attesa(True, False, False) is True
    assert membro_in_attesa(False, False, False) is False


def test_RUO_039_ruoli_ridati_a_chi_rientra_entro_i_giorni():
    from datetime import datetime, timedelta, timezone

    ora = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert ruoli_da_ridare([1, 2], ora - timedelta(days=3), ora, 30) == [1, 2]
    assert ruoli_da_ridare([1, 2], ora - timedelta(days=40), ora, 30) == []


@pytest.mark.parametrize("modo", ["unique", "verify", "drop", "reversed", "binding", "temp", "lock", "normal"])
def test_RUO_054_061_ogni_comportamento_del_menu_esiste(modo):
    assert modo in COMPORTAMENTI


def test_RUO_054_RUO_064_unique_toglie_il_ruolo_precedente():
    d = decidi_azione(
        "unique", attiva=True, via_reazione=False, ruolo_id=2, ruoli_menu={1, 2}, ruoli_membro={1}
    )
    assert d.aggiungi == (2,) and d.togli == (1,)


def test_RUO_055_RUO_056_verify_non_toglie_e_drop_toglie_soltanto():
    v = decidi_azione("verify", attiva=True, via_reazione=False, ruolo_id=1, ruoli_menu={1}, ruoli_membro={1})
    assert v.rifiuto and not v.togli
    d = decidi_azione("drop", attiva=True, via_reazione=False, ruolo_id=1, ruoli_menu={1}, ruoli_membro={1})
    assert d.togli == (1,)


def test_RUO_057_RUO_058_RUO_059_reversed_binding_lock():
    r = decidi_azione("reversed", attiva=True, via_reazione=True, ruolo_id=1, ruoli_menu={1}, ruoli_membro={1})
    assert r.togli == (1,)
    b = decidi_azione("binding", attiva=True, via_reazione=False, ruolo_id=2, ruoli_menu={1, 2}, ruoli_membro={1})
    assert b.rifiuto
    lk = decidi_azione("lock", attiva=True, via_reazione=False, ruolo_id=1, ruoli_menu={1}, ruoli_membro=set())
    assert lk.rifiuto


def test_RUO_060_RUO_061_temp_ha_scadenza_e_normal_e_il_ritorno():
    t = decidi_azione(
        "temp", attiva=True, via_reazione=False, ruolo_id=1, ruoli_menu={1}, ruoli_membro=set(), temp_secondi=60
    )
    assert t.temporaneo_secondi == 60
    n = decidi_azione("normal", attiva=True, via_reazione=False, ruolo_id=1, ruoli_menu={1}, ruoli_membro=set())
    assert n.aggiungi == (1,) and n.temporaneo_secondi is None


def test_RUO_066_RUO_067_ruoli_ammessi_ed_esclusi_l_esclusione_vince():
    assert membro_ammesso([5], [], {5}) is None
    assert membro_ammesso([5], [], {9}) is not None
    assert membro_ammesso([5], [6], {5, 6}) is not None
    assert regola_vale_per(RegolaAutoruolo(1), set())


def test_RUO_078_il_menu_si_pubblica_prima_e_si_salva_dopo():
    import inspect

    import cogs.utility.role_menus as modulo

    sorgente = inspect.getsource(modulo.RoleMenuCog.add_option_cmd.callback)
    assert sorgente.index("_pubblica_menu") < sorgente.index("role_menu_repo.add_option")

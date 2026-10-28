"""
tests/test_boss_logic.py
========================
Regole del World Boss (§25.49–§25.52, §25.59, §25.70): formule, orario, mostri, premi.
"""

import random
from datetime import date, datetime, timezone

from core import boss_logic as b


def test_vita_cresce_con_i_membri_attivi_entro_i_tetti():
    assert b.vita_boss(0) == b.VITA_MINIMA
    assert b.vita_boss(20) == 3000
    assert b.vita_boss(100_000) == b.VITA_MASSIMA
    assert b.vita_boss(20, vita_extra=500) == 3500


def test_danno_cresce_con_il_livello_e_ha_un_tetto():
    rng = random.Random(1)
    basso = sum(b.danno_attacco(1, rng) for _ in range(200)) / 200
    alto = sum(b.danno_attacco(30, rng) for _ in range(200)) / 200
    assert alto > basso * 2
    assert b.danno_attacco(10_000, random.Random(2)) <= round(b.DANNO_MASSIMO * 1.2)
    assert b.danno_magia(5, random.Random(3)) >= 3


def test_contrattacco_ogni_dieci_azioni():
    assert [n for n in range(0, 31) if b.contrattacco_dovuto(n)] == [10, 20, 30]


def test_barra_vita():
    assert b.barra_vita(100, 100) == "█" * 20
    assert b.barra_vita(0, 100) == "░" * 20
    assert b.barra_vita(1, 1000).startswith("█") and b.barra_vita(1, 1000).count("█") == 1


def test_premi_con_tetti_e_proporzione():
    assert b.premio(0, 1000, 5) == b.Premio(0, 0)
    piccolo, grande = b.premio(50, 1000, 10), b.premio(900, 1000, 10)
    assert grande.monete > piccolo.monete >= 40
    assert grande.monete <= b.PREMIO_MONETE_MAX and grande.xp <= b.PREMIO_XP_MAX


def test_comparsa_a_orario_una_volta_per_giorno_nel_fuso_del_server():
    venerdi_21_roma = datetime(2026, 10, 30, 20, 5, tzinfo=timezone.utc)  # 21:05 a Roma (ora solare)
    assert b.giorno_di_comparsa([4], 21, "Europe/Rome", venerdi_21_roma) == date(2026, 10, 30)
    assert b.giorno_di_comparsa([4], 21, "Europe/Rome", venerdi_21_roma, ultimo_giorno=date(2026, 10, 30)) is None
    assert b.giorno_di_comparsa([3], 21, "Europe/Rome", venerdi_21_roma) is None
    assert b.giorno_di_comparsa([4], 21, "Europe/Rome", datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc)) is None
    assert b.giorno_di_comparsa([4], 21, "Europe/Rome", datetime(2026, 10, 30, 23, 30, tzinfo=timezone.utc)) is None
    assert b.giorno_di_comparsa([4], 21, "Fuso/Che/Non/Esiste", venerdi_21_roma) == date(2026, 10, 30)


def test_giorni_a_parole():
    assert b.leggi_giorni("lun, ven") == [0, 4]
    assert b.leggi_giorni("venerdì") == [4]
    assert b.leggi_giorni("ogni giorno") == list(range(7))
    assert b.leggi_giorni("pippo") is None and b.leggi_giorni("") is None
    assert b.descrivi_orario([4, 0], 21, "Europe/Rome") == "lunedì, venerdì alle 21:00 (Europe/Rome)"
    assert b.fuso_valido("Europe/Rome") and b.fuso_valido("Nope/Nope") is None


def test_mostri_pronti_per_ogni_tema_e_riserva():
    for tema, mostri in b.MOSTRI_PRONTI.items():
        assert mostri and all(m.nome and m.frasi for m in mostri), tema
    assert b.mostro_pronto("tema-sconosciuto", random.Random(0)) in b.MOSTRI_PRONTI["yokai"]


def test_mostro_scritto_dall_ai_ripulito():
    m = b.leggi_mostro('```{"nome": "Orso <@123> `Nero`", "aspetto": "grande https://x.example/a", "frasi": ["Grr", 5, "", "a", "b", "c", "d"]}```')
    assert m.nome == "Orso 123 Nero" and "http" not in m.aspetto
    assert m.frasi == ("Grr", "a", "b", "c", "d")
    assert b.leggi_mostro("niente") is None and b.leggi_mostro('{"nome": ""}') is None


def test_immagine_del_boss_e_un_png_piccolo():
    import io

    from PIL import Image

    from core.boss_image import ALTEZZA, LARGHEZZA, disegna_boss

    dati = disegna_boss("Gashadokuro 🦴", "Uno scheletro enorme " * 10, 1500, 3000, "yokai")
    img = Image.open(io.BytesIO(dati))
    assert img.format == "PNG" and img.size == (LARGHEZZA, ALTEZZA) and len(dati) < 1_000_000
    assert Image.open(io.BytesIO(disegna_boss("X", "", 0, 100, "tema-ignoto"))).size == (LARGHEZZA, ALTEZZA)

"""
tests/test_music_esporta_coda.py
================================
La coda musicale come file di testo (MUS-043): niente nomi di chi ha chiesto i brani, solo indirizzi web veri.
Funzioni coperte: MUS-043
"""

from core.music_queue_logic import coda_come_testo


# MUS-043
def test_il_file_elenca_il_brano_attuale_e_la_coda_in_ordine():
    testo = coda_come_testo(
        ("Uno", "Autore A", "https://example.com/uno"),
        [("Due", "Autore B", "https://example.com/due"), ("Tre", "", "https://example.com/tre")],
    )
    righe = testo.strip().split("\n")
    assert righe[0].startswith("In riproduzione: Uno")
    assert righe[1] == "1. Due — Autore B — https://example.com/due"
    assert righe[2] == "2. Tre — https://example.com/tre"


# MUS-043
def test_il_file_non_porta_indirizzi_strani_ne_righe_di_comando_e_ha_un_tetto():
    testo = coda_come_testo(None, [("x\nfalso", "a", "file:///etc/passwd"), ("ok", "a", "javascript:alert(1)")] + [("t", "a", "https://e.it/")] * 5000)
    assert "file:" not in testo and "javascript:" not in testo
    assert testo.split("\n")[0] == "1. x falso — a"  # il titolo con l'a capo resta su una riga sola
    assert len(testo.encode()) <= 1_000_000
    assert coda_come_testo(None, []).strip() == "La coda è vuota."

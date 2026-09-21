"""
tests/test_main_radio_logic.py
==================================
Test di core/main_radio_logic.py — logica pura.
"""

from datetime import datetime, timedelta, timezone

from core.main_radio_logic import (
    RadioTrackInfo,
    compute_current_position,
    next_track_index,
)

ORA = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

TRACCE_DI_ESEMPIO = [
    RadioTrackInfo(identifier="traccia-1", duration_ms=180_000),  # 3 min
    RadioTrackInfo(identifier="traccia-2", duration_ms=240_000),  # 4 min
    RadioTrackInfo(identifier="traccia-3", duration_ms=200_000),  # ~3.3 min
]


class TestComputeCurrentPosition:
    def test_playlist_vuota_restituisce_none(self):
        assert compute_current_position([], 0, ORA, ORA) is None

    def test_indice_di_riferimento_fuori_range_restituisce_none(self):
        assert compute_current_position(TRACCE_DI_ESEMPIO, 99, ORA, ORA) is None

    def test_nessun_tempo_trascorso_resta_sulla_stessa_traccia_a_inizio(self):
        risultato = compute_current_position(TRACCE_DI_ESEMPIO, 0, ORA, ORA)
        assert risultato.track_index == 0
        assert risultato.elapsed_ms_in_track == 0

    def test_a_meta_della_prima_traccia(self):
        adesso = ORA + timedelta(minutes=1, seconds=30)  # metà dei 3 minuti
        risultato = compute_current_position(TRACCE_DI_ESEMPIO, 0, ORA, adesso)
        assert risultato.track_index == 0
        assert risultato.elapsed_ms_in_track == 90_000

    def test_avanza_alla_traccia_successiva_dopo_la_fine_della_prima(self):
        adesso = ORA + timedelta(minutes=4)  # 3 min (traccia 1) + 1 min dentro la 2
        risultato = compute_current_position(TRACCE_DI_ESEMPIO, 0, ORA, adesso)
        assert risultato.track_index == 1
        assert risultato.elapsed_ms_in_track == 60_000

    def test_attraversa_piu_tracce_se_e_passato_molto_tempo(self):
        # 3+4+3.33 = 10.33 min per un giro completo. Dopo 12 minuti
        # dall'inizio della traccia 0, dovremmo essere di nuovo sulla
        # traccia 0 (loop), a 12-10.333 = 1.667 min dentro.
        adesso = ORA + timedelta(minutes=12)
        risultato = compute_current_position(TRACCE_DI_ESEMPIO, 0, ORA, adesso)
        assert risultato.track_index == 0
        assert abs(risultato.elapsed_ms_in_track - 100_000) < 1000

    def test_orologio_di_riferimento_nel_futuro_non_produce_valori_assurdi(self):
        passato = ORA - timedelta(minutes=5)
        risultato = compute_current_position(TRACCE_DI_ESEMPIO, 1, ORA, passato)
        assert risultato.track_index == 1
        assert risultato.elapsed_ms_in_track == 0

    def test_parte_da_un_indice_di_riferimento_diverso_da_zero(self):
        adesso = ORA + timedelta(seconds=30)
        risultato = compute_current_position(TRACCE_DI_ESEMPIO, 2, ORA, adesso)
        assert risultato.track_index == 2
        assert risultato.elapsed_ms_in_track == 30_000

    def test_durata_zero_non_causa_un_ciclo_infinito(self):
        tracce_con_zero = [RadioTrackInfo(identifier="x", duration_ms=0)]
        adesso = ORA + timedelta(seconds=5)
        # Non deve bloccarsi - il test stesso ha successo se ritorna.
        risultato = compute_current_position(tracce_con_zero, 0, ORA, adesso)
        assert risultato is not None


class TestNextTrackIndex:
    def test_avanza_di_uno(self):
        assert next_track_index(0, 3) == 1
        assert next_track_index(1, 3) == 2

    def test_fa_loop_alla_fine_della_playlist(self):
        assert next_track_index(2, 3) == 0

    def test_playlist_vuota_restituisce_zero(self):
        assert next_track_index(0, 0) == 0

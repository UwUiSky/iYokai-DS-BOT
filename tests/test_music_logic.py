"""
tests/test_music_logic.py
=============================
Test di core/music_logic.py — logica pura.
"""

from core.music_logic import (
    LavalinkNodeConfig,
    build_queue_display,
    format_duration,
    parse_lavalink_nodes,
)


class TestParseLavalinkNodes:
    def test_stringa_vuota_restituisce_lista_vuota(self):
        assert parse_lavalink_nodes("") == []
        assert parse_lavalink_nodes("   ") == []

    def test_un_nodo_singolo(self):
        risultato = parse_lavalink_nodes("http://esempio.com:2333|password123")
        assert risultato == [LavalinkNodeConfig(uri="http://esempio.com:2333", password="password123")]

    def test_piu_nodi_separati_da_virgola(self):
        risultato = parse_lavalink_nodes(
            "http://a.com:2333|pass1,http://b.com:443|pass2"
        )
        assert len(risultato) == 2
        assert risultato[0].uri == "http://a.com:2333"
        assert risultato[1].uri == "http://b.com:443"

    def test_spazi_intorno_vengono_rimossi(self):
        risultato = parse_lavalink_nodes(" http://a.com:2333 | pass1 , http://b.com:443 | pass2 ")
        assert risultato[0].uri == "http://a.com:2333"
        assert risultato[0].password == "pass1"

    def test_pezzo_senza_separatore_viene_ignorato(self):
        # Typo dell'utente (dimenticato il "|") - non deve far
        # sparire gli altri nodi validi accanto.
        risultato = parse_lavalink_nodes("nodo_scritto_male,http://b.com:443|pass2")
        assert len(risultato) == 1
        assert risultato[0].uri == "http://b.com:443"

    def test_pezzo_vuoto_tra_due_virgole_viene_ignorato(self):
        risultato = parse_lavalink_nodes("http://a.com:2333|pass1,,http://b.com:443|pass2")
        assert len(risultato) == 2

    def test_password_vuota_e_valida(self):
        # Alcuni nodi pubblici non richiedono password.
        risultato = parse_lavalink_nodes("http://a.com:2333|")
        assert risultato == [LavalinkNodeConfig(uri="http://a.com:2333", password="")]


class TestFormatDuration:
    def test_meno_di_un_minuto(self):
        assert format_duration(45_000) == "0:45"

    def test_minuti_e_secondi(self):
        assert format_duration(225_000) == "3:45"

    def test_esattamente_un_ora(self):
        assert format_duration(3_600_000) == "1:00:00"

    def test_oltre_un_ora(self):
        assert format_duration(3_725_000) == "1:02:05"

    def test_zero_millisecondi(self):
        assert format_duration(0) == "0:00"

    def test_valore_negativo_non_solleva(self):
        # Un valore negativo (es. per uno stream live senza durata
        # nota) non deve far crashare la formattazione.
        assert format_duration(-1000) == "0:00"

    def test_secondi_singola_cifra_hanno_lo_zero_davanti(self):
        assert format_duration(65_000) == "1:05"


class TestBuildQueueDisplay:
    def test_nessuna_traccia_in_riproduzione_e_coda_vuota(self):
        risultato = build_queue_display(None, [])
        assert "Nessuna traccia" in risultato
        assert "vuota" in risultato

    def test_traccia_in_riproduzione_senza_coda(self):
        risultato = build_queue_display("Canzone Attuale", [])
        assert "Canzone Attuale" in risultato
        assert "vuota" in risultato

    def test_coda_con_tracce_le_elenca_numerate(self):
        risultato = build_queue_display("Attuale", ["Prima", "Seconda", "Terza"])
        assert "1. Prima" in risultato
        assert "2. Seconda" in risultato
        assert "3. Terza" in risultato

    def test_coda_lunga_mostra_solo_max_shown_e_un_contatore(self):
        tracce = [f"Traccia {i}" for i in range(15)]
        risultato = build_queue_display("Attuale", tracce, max_shown=10)
        assert "Traccia 0" in risultato
        assert "Traccia 9" in risultato
        assert "Traccia 10" not in risultato
        assert "altre 5 tracce" in risultato

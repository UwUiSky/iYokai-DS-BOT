"""
tests/test_music_logic.py
=============================
Test di core/music_logic.py — logica pura.
"""

from core.music_logic import (
    MAX_PLAYLIST_TRACKS,
    LavalinkNodeConfig,
    build_progress_bar,
    build_queue_display,
    format_duration,
    is_spotify_query,
    parse_lavalink_nodes,
    truncate_playlist_tracks,
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

    def test_default_public_nodes_si_analizza_correttamente(self):
        # Il caso reale: la password di Serenetia è essa stessa un
        # URL (con "://" dentro) - verifica che il separatore "|"
        # non venga confuso con quello.
        from core.music_logic import DEFAULT_PUBLIC_LAVALINK_NODES

        risultato = parse_lavalink_nodes(DEFAULT_PUBLIC_LAVALINK_NODES)
        assert len(risultato) == 5
        assert all(nodo.uri.startswith(("http://", "https://")) for nodo in risultato)


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


class TestBuildProgressBar:
    def test_inizio_traccia_pallino_al_primo_slot(self):
        risultato = build_progress_bar(0, 100_000, bar_length=10)
        assert risultato.startswith("🔘")
        assert risultato.count("▬") == 9

    def test_metà_traccia_pallino_a_metà(self):
        risultato = build_progress_bar(50_000, 100_000, bar_length=10)
        # 50% di 10 slot = indice 5 (0-based) → 5 trattini prima, 4 dopo
        prima_del_pallino = risultato.split("🔘")[0]
        assert prima_del_pallino.count("▬") == 5

    def test_fine_traccia_pallino_all_ultimo_slot(self):
        risultato = build_progress_bar(100_000, 100_000, bar_length=10)
        prima_del_pallino = risultato.split("🔘")[0]
        assert prima_del_pallino.count("▬") == 9

    def test_durata_zero_o_negativa_restituisce_indicatore_live(self):
        # Una traccia in streaming live (Lavalink riporta length=0
        # per gli stream senza durata nota) non deve far crashare la
        # barra con una divisione per zero.
        assert build_progress_bar(5_000, 0, bar_length=10) == "🔴 LIVE"
        assert build_progress_bar(5_000, -1, bar_length=10) == "🔴 LIVE"

    def test_elapsed_oltre_la_durata_non_sfora_la_barra(self):
        # Può succedere per un piccolo scarto di sincronizzazione con
        # Lavalink appena prima del cambio traccia.
        risultato = build_progress_bar(150_000, 100_000, bar_length=10)
        prima_del_pallino = risultato.split("🔘")[0]
        assert prima_del_pallino.count("▬") == 9

    def test_elapsed_negativo_non_sfora_la_barra(self):
        risultato = build_progress_bar(-5_000, 100_000, bar_length=10)
        prima_del_pallino = risultato.split("🔘")[0]
        assert prima_del_pallino.count("▬") == 0

    def test_lunghezza_totale_della_barra_fissa(self):
        risultato = build_progress_bar(30_000, 100_000, bar_length=20)
        assert risultato.count("▬") + risultato.count("🔘") == 20


class TestTruncatePlaylistTracks:
    def test_sotto_il_limite_resta_invariata(self):
        tracce = list(range(10))
        assert truncate_playlist_tracks(tracce, limit=750) == tracce

    def test_esattamente_al_limite_resta_invariata(self):
        tracce = list(range(750))
        risultato = truncate_playlist_tracks(tracce, limit=750)
        assert len(risultato) == 750
        assert risultato == tracce

    def test_sopra_il_limite_viene_tagliata_alle_prime_n(self):
        tracce = list(range(1000))
        risultato = truncate_playlist_tracks(tracce, limit=750)
        assert len(risultato) == 750
        assert risultato == tracce[:750]

    def test_limite_di_default_è_750(self):
        tracce = list(range(2000))
        assert len(truncate_playlist_tracks(tracce)) == 750
        assert MAX_PLAYLIST_TRACKS == 750

    def test_lista_vuota_resta_vuota(self):
        assert truncate_playlist_tracks([], limit=750) == []


class TestIsSpotifyQuery:
    def test_url_open_spotify(self):
        assert is_spotify_query("https://open.spotify.com/track/abc123") is True

    def test_uri_spotify(self):
        assert is_spotify_query("spotify:track:abc123") is True

    def test_maiuscole_e_spazi_non_contano(self):
        assert is_spotify_query("  SPOTIFY:track:abc123  ") is True

    def test_query_youtube_falso(self):
        assert is_spotify_query("https://youtube.com/watch?v=abc") is False

    def test_ricerca_testuale_semplice_falso(self):
        assert is_spotify_query("una canzone qualsiasi") is False

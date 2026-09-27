"""
tests/test_ticket_logic.py
=============================
Test di core/ticket_logic.py — logica pura, nessuna dipendenza da
Discord.
"""

from core.ticket_logic import (
    build_transcript_text,
    format_duration_seconds,
    format_transcript_line,
    is_first_response,
    merge_support_role_ids,
)


class TestFormatTranscriptLine:
    def test_riga_con_testo(self):
        riga = format_transcript_line("12:34", "Mario", "Ciao a tutti")
        assert riga == "[12:34] Mario: Ciao a tutti"

    def test_riga_senza_testo_usa_placeholder(self):
        riga = format_transcript_line("12:34", "Mario", "")
        assert "nessun testo" in riga


class TestBuildTranscriptText:
    def test_con_messaggi(self):
        testo = build_transcript_text(["Ticket #0001"], ["[12:00] A: ciao", "[12:01] B: ciao a te"])
        assert testo.startswith("Ticket #0001\n\n")
        assert "[12:00] A: ciao" in testo
        assert "[12:01] B: ciao a te" in testo

    def test_senza_messaggi(self):
        testo = build_transcript_text(["Ticket #0001"], [])
        assert "nessun messaggio nel canale" in testo


class TestIsFirstResponse:
    def test_messaggio_dello_staff_conta(self):
        assert is_first_response(author_id=2, ticket_owner_id=1, author_is_bot=False) is True

    def test_messaggio_dell_utente_non_conta(self):
        assert is_first_response(author_id=1, ticket_owner_id=1, author_is_bot=False) is False

    def test_messaggio_del_bot_non_conta(self):
        # Es. il messaggio di benvenuto automatico del bot stesso.
        assert is_first_response(author_id=2, ticket_owner_id=1, author_is_bot=True) is False


class TestMergeSupportRoleIds:
    def test_solo_legacy(self):
        assert merge_support_role_ids(42, []) == [42]

    def test_solo_nuovi(self):
        assert merge_support_role_ids(None, [1, 2]) == [1, 2]

    def test_legacy_e_nuovi_senza_duplicati(self):
        assert merge_support_role_ids(1, [1, 2, 3]) == [1, 2, 3]

    def test_nessun_ruolo_configurato(self):
        assert merge_support_role_ids(None, []) == []


class TestFormatDurationSeconds:
    def test_nessun_dato(self):
        assert format_duration_seconds(None) == "n/d"

    def test_solo_secondi(self):
        assert format_duration_seconds(45) == "45s"

    def test_minuti_e_secondi(self):
        assert format_duration_seconds(135) == "2m 15s"

    def test_ore_e_minuti(self):
        assert format_duration_seconds(3900) == "1h 5m"

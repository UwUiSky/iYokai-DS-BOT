"""
tests/test_spam_trap_transcript.py
=====================================
Test di core/spam_trap_transcript.py. Il test più importante è
l'escaping anti-XSS: un nickname o un contenuto messaggio con markup
HTML dentro non deve poter eseguire codice quando lo staff apre il
transcript in un browser.
"""

from datetime import datetime, timezone

from core.spam_trap_transcript import TranscriptEntry, build_transcript_html


def _entry(**overrides) -> TranscriptEntry:
    base = dict(
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        author_display_name="Mario",
        author_tag="mario#0001",
        content="ciao a tutti",
        attachment_filenames=[],
        is_deleted_source=False,
    )
    base.update(overrides)
    return TranscriptEntry(**base)


class TestEscapingAntiXSS:
    def test_nickname_con_script_tag_viene_escapato(self):
        entry = _entry(author_display_name="<script>alert(1)</script>")
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)

        assert "<script>alert(1)</script>" not in html_output
        assert "&lt;script&gt;" in html_output

    def test_contenuto_messaggio_con_html_viene_escapato(self):
        entry = _entry(content='<img src=x onerror="alert(1)">')
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)

        assert '<img src=x onerror="alert(1)">' not in html_output
        assert "&lt;img" in html_output

    def test_tag_nel_titolo_viene_escapato(self):
        html_output = build_transcript_html(
            [], title="<b>Titolo</b>", generated_at=datetime.now(timezone.utc)
        )
        assert "<b>Titolo</b>" not in html_output
        assert "&lt;b&gt;" in html_output

    def test_nome_allegato_con_html_viene_escapato(self):
        entry = _entry(attachment_filenames=["<script>x</script>.png"])
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert "<script>x</script>.png" not in html_output

    def test_virgolette_nel_contenuto_vengono_escapate(self):
        # quote=True in html.escape(): previene anche l'injection
        # dentro attributi HTML se il contenuto finisse mai in un
        # attributo in una versione futura del template.
        entry = _entry(content='testo con "virgolette" e \'apici\'')
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert "&quot;" in html_output or "&#x27;" in html_output


class TestContenutoStrutturale:
    def test_lista_vuota_produce_messaggio_placeholder(self):
        html_output = build_transcript_html([], title="Vuoto", generated_at=datetime.now(timezone.utc))
        assert "Nessun messaggio indicizzato" in html_output

    def test_contenuto_vuoto_produce_placeholder_nessun_testo(self):
        entry = _entry(content="")
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert "nessun testo" in html_output

    def test_conteggio_messaggi_nel_documento(self):
        entries = [_entry(content=f"messaggio {i}") for i in range(3)]
        html_output = build_transcript_html(entries, title="Test", generated_at=datetime.now(timezone.utc))
        assert "3 message" in html_output

    def test_messaggio_da_fonte_cancellata_ha_classe_dedicata(self):
        entry = _entry(is_deleted_source=True)
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert "deleted-source" in html_output

    def test_allegati_elencati(self):
        entry = _entry(attachment_filenames=["foto.png", "documento.pdf"])
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert "foto.png" in html_output
        assert "documento.pdf" in html_output

    def test_documento_e_html_valido_minimale(self):
        html_output = build_transcript_html(
            [_entry()], title="Test", generated_at=datetime.now(timezone.utc)
        )
        assert html_output.strip().startswith("<!DOCTYPE html>")
        assert "<html" in html_output
        assert "</html>" in html_output


class TestThumbnailImmagini:
    def test_data_uri_inserita_come_src_immagine(self):
        entry = _entry(
            attachment_thumbnail_data_uris=["data:image/webp;base64,AAAA"]
        )
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert 'src="data:image/webp;base64,AAAA"' in html_output
        assert "<img" in html_output

    def test_piu_thumbnail_nello_stesso_messaggio(self):
        entry = _entry(
            attachment_thumbnail_data_uris=[
                "data:image/webp;base64,AAAA",
                "data:image/webp;base64,BBBB",
            ]
        )
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert html_output.count("<img") == 2

    def test_nessuna_thumbnail_nessun_tag_img(self):
        entry = _entry(attachment_thumbnail_data_uris=[])
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert "<img" not in html_output

    def test_compatibilita_allentro_precedente_senza_il_nuovo_campo(self):
        # Un TranscriptEntry costruito come nella versione precedente
        # (senza passare attachment_thumbnail_data_uris) deve
        # continuare a funzionare grazie al default_factory — nessuna
        # rottura per chi lo istanzia nel modo "vecchio".
        entry = TranscriptEntry(
            timestamp=datetime.now(timezone.utc),
            author_display_name="Mario",
            author_tag="mario#0001",
            content="test",
        )
        html_output = build_transcript_html([entry], title="Test", generated_at=entry.timestamp)
        assert "<img" not in html_output


class TestAvatarReport:
    def test_avatar_presente_produce_img_nellintestazione(self):
        html_output = build_transcript_html(
            [_entry()],
            title="Test",
            generated_at=datetime.now(timezone.utc),
            author_avatar_data_uri="data:image/webp;base64,CCCC",
        )
        assert 'class="author-avatar"' in html_output
        assert 'src="data:image/webp;base64,CCCC"' in html_output

    def test_avatar_assente_nessun_img_nellintestazione(self):
        html_output = build_transcript_html(
            [_entry()], title="Test", generated_at=datetime.now(timezone.utc)
        )
        assert 'class="author-avatar"' not in html_output

    def test_avatar_e_mostrato_una_sola_volta_non_per_messaggio(self):
        # Tre messaggi, un solo avatar nell'intestazione — non uno
        # per riga: coerente col fatto che il transcript riguarda
        # sempre un solo utente.
        entries = [_entry(content=f"messaggio {i}") for i in range(3)]
        html_output = build_transcript_html(
            entries,
            title="Test",
            generated_at=datetime.now(timezone.utc),
            author_avatar_data_uri="data:image/webp;base64,DDDD",
        )
        assert html_output.count('class="author-avatar"') == 1

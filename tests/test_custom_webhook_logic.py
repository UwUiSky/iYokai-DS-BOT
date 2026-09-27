"""
tests/test_custom_webhook_logic.py
======================================
Test di core/custom_webhook_logic.py — logica pura.
"""

from core.custom_webhook_logic import (
    DEFAULT_MESSAGE_TEMPLATE,
    MAX_MESSAGE_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_URL_LENGTH,
    build_webhook_url,
    extract_webhook_fields,
    generate_webhook_token,
    render_webhook_message,
)


class TestGenerateWebhookToken:
    def test_restituisce_una_stringa_non_vuota(self):
        token = generate_webhook_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_due_chiamate_danno_token_diversi(self):
        # Non una garanzia matematica assoluta, ma con secrets.
        # token_urlsafe(32) una collisione è astronomicamente
        # improbabile — se questo test fallisse davvero per caso
        # varrebbe la pena comprare un biglietto della lotteria.
        assert generate_webhook_token() != generate_webhook_token()

    def test_nessun_carattere_che_romperebbe_un_url(self):
        token = generate_webhook_token()
        assert " " not in token
        assert "/" not in token


class TestBuildWebhookUrl:
    def test_unisce_base_e_token(self):
        assert build_webhook_url("https://esempio.com", "abc123") == "https://esempio.com/webhook/abc123"

    def test_rimuove_lo_slash_finale_della_base(self):
        assert build_webhook_url("https://esempio.com/", "abc123") == "https://esempio.com/webhook/abc123"


class TestExtractWebhookFields:
    def test_payload_completo(self):
        title, message, url = extract_webhook_fields(
            {"title": "Titolo", "message": "Corpo", "url": "https://esempio.com"}
        )
        assert title == "Titolo"
        assert message == "Corpo"
        assert url == "https://esempio.com"

    def test_payload_vuoto_restituisce_stringhe_vuote(self):
        assert extract_webhook_fields({}) == ("", "", "")

    def test_payload_non_dizionario_non_solleva(self):
        # Un mittente esterno potrebbe mandare un array JSON o una
        # stringa nuda invece di un oggetto — non deve far crashare
        # il server.
        assert extract_webhook_fields([1, 2, 3]) == ("", "", "")
        assert extract_webhook_fields("una stringa") == ("", "", "")
        assert extract_webhook_fields(None) == ("", "", "")

    def test_alias_content_per_il_corpo(self):
        _, message, _ = extract_webhook_fields({"content": "Dal campo content"})
        assert message == "Dal campo content"

    def test_alias_text_per_il_corpo(self):
        _, message, _ = extract_webhook_fields({"text": "Dal campo text"})
        assert message == "Dal campo text"

    def test_message_ha_priorita_su_content_e_text(self):
        _, message, _ = extract_webhook_fields(
            {"message": "Vince questo", "content": "Non questo", "text": "Nemmeno questo"}
        )
        assert message == "Vince questo"

    def test_alias_link_per_url(self):
        _, _, url = extract_webhook_fields({"link": "https://alias.esempio.com"})
        assert url == "https://alias.esempio.com"

    def test_url_ha_priorita_su_link(self):
        _, _, url = extract_webhook_fields({"url": "https://vince.com", "link": "https://non-vince.com"})
        assert url == "https://vince.com"

    def test_valore_non_stringa_viene_convertito(self):
        # Un mittente esterno potrebbe mandare un numero o un booleano
        # per errore — deve diventare una stringa, non far crashare.
        title, message, url = extract_webhook_fields({"title": 42, "message": True, "url": 3.14})
        assert title == "42"
        assert message == "True"
        assert url == "3.14"

    def test_valore_none_esplicito_diventa_stringa_vuota(self):
        assert extract_webhook_fields({"title": None}) == ("", "", "")

    def test_campi_troppo_lunghi_vengono_troncati(self):
        title, message, url = extract_webhook_fields(
            {
                "title": "a" * (MAX_TITLE_LENGTH + 100),
                "message": "b" * (MAX_MESSAGE_LENGTH + 100),
                "url": "c" * (MAX_URL_LENGTH + 100),
            }
        )
        assert len(title) == MAX_TITLE_LENGTH
        assert len(message) == MAX_MESSAGE_LENGTH
        assert len(url) == MAX_URL_LENGTH

    def test_spazi_ai_bordi_vengono_rimossi(self):
        title, _, _ = extract_webhook_fields({"title": "  con spazi  "})
        assert title == "con spazi"


class TestRenderWebhookMessage:
    def test_template_di_default_con_payload_completo(self):
        risultato = render_webhook_message(
            DEFAULT_MESSAGE_TEMPLATE,
            "Il Mio Webhook",
            {"title": "Titolo", "message": "Corpo", "url": "https://esempio.com"},
        )
        assert "Il Mio Webhook" in risultato
        assert "Titolo" in risultato
        assert "Corpo" in risultato
        assert "https://esempio.com" in risultato

    def test_righe_vuote_vengono_rimosse(self):
        # Payload con solo "message": {title} e {url} risultano
        # stringhe vuote — le righe corrispondenti nel template di
        # default non devono comparire vuote nel messaggio finale.
        risultato = render_webhook_message(
            DEFAULT_MESSAGE_TEMPLATE, "Label", {"message": "Solo questo"}
        )
        righe = risultato.split("\n")
        assert all(riga.strip() for riga in righe)
        assert "Solo questo" in risultato

    def test_template_personalizzato(self):
        risultato = render_webhook_message(
            "🔔 {label} dice: {message}", "Monitor", {"message": "Il server è caduto"}
        )
        assert risultato == "🔔 Monitor dice: Il server è caduto"

    def test_payload_completamente_vuoto_con_template_default_non_solleva(self):
        risultato = render_webhook_message(DEFAULT_MESSAGE_TEMPLATE, "Label", {})
        assert "Label" in risultato

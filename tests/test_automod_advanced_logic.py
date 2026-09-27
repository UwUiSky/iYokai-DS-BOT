"""
tests/test_automod_advanced_logic.py
========================================
Test della logica pura dei filtri AutoMod avanzati (SPEC.md
§6.3-§6.10) — nessun mock di discord.py o del DB, solo input/output.
"""

from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    CapsFilterConfig,
    MessageSignals,
    RateFilterConfig,
    ThresholdFilterConfig,
    VIOLATION_ANTI_LINK,
    VIOLATION_ATTACHMENT_SPAM,
    VIOLATION_CAPS,
    VIOLATION_MASS_MENTION,
    VIOLATION_SPAM_EMOJI,
    VIOLATION_SPAM_MESSAGES,
    VIOLATION_SPAM_STICKER,
    VIOLATION_ZALGO,
    evaluate_message_violations,
    extract_domains,
    is_caps_violation,
    is_link_violation,
    is_zalgo_violation,
)


class TestExtractDomains:
    def test_nessun_link_restituisce_tupla_vuota(self):
        assert extract_domains("ciao a tutti, nessun link qui") == ()

    def test_estrae_dominio_singolo_senza_www(self):
        assert extract_domains("guarda qui https://www.esempio.com/pagina") == ("esempio.com",)

    def test_estrae_piu_domini(self):
        risultato = extract_domains("https://a.com e anche http://b.it/x")
        assert risultato == ("a.com", "b.it")


class TestAntiLink:
    def test_mode_off_non_viola_mai(self):
        assert is_link_violation(("qualunque.com",), "off", (), ()) is False

    def test_whitelist_blocca_dominio_non_elencato(self):
        assert is_link_violation(("cattivo.com",), "whitelist", ("buono.com",), ()) is True

    def test_whitelist_permette_dominio_elencato(self):
        assert is_link_violation(("buono.com",), "whitelist", ("buono.com",), ()) is False

    def test_blacklist_blocca_dominio_elencato(self):
        assert is_link_violation(("cattivo.com",), "blacklist", (), ("cattivo.com",)) is True

    def test_blacklist_permette_dominio_non_elencato(self):
        assert is_link_violation(("altro.com",), "blacklist", (), ("cattivo.com",)) is False

    def test_nessun_link_non_viola(self):
        assert is_link_violation((), "blacklist", (), ("cattivo.com",)) is False


class TestCaps:
    def test_sotto_lunghezza_minima_non_viola(self):
        assert is_caps_violation("CIAO", threshold_percent=70, min_length=10) is False

    def test_sopra_soglia_viola(self):
        assert is_caps_violation("QUESTO E TUTTO MAIUSCOLO", threshold_percent=70, min_length=5) is True

    def test_sotto_soglia_non_viola(self):
        assert is_caps_violation("Questo e normale testo", threshold_percent=70, min_length=5) is False

    def test_solo_punteggiatura_e_numeri_non_conta_come_lettere(self):
        assert is_caps_violation("123456!!!!!", threshold_percent=70, min_length=3) is False


class TestZalgo:
    def test_testo_normale_non_e_zalgo(self):
        assert is_zalgo_violation("Ciao come va, tutto bene?") is False

    def test_accenti_italiani_normali_non_sono_zalgo(self):
        assert is_zalgo_violation("Perché città però caffè università") is False

    def test_molti_segni_combinanti_sono_zalgo(self):
        base = "A"
        combinanti = "́" * 10  # accento acuto combinante ripetuto
        assert is_zalgo_violation(base + combinanti) is True


class TestEvaluateMessageViolations:
    def _config(self, **overrides) -> AutomodAdvancedConfig:
        return AutomodAdvancedConfig(**overrides)

    def test_messaggio_pulito_nessuna_violazione(self):
        config = self._config(
            anti_spam_messages=RateFilterConfig(enabled=True, max_count=5),
            anti_caps=CapsFilterConfig(enabled=True),
        )
        segnali = MessageSignals(content="Un messaggio normale", recent_message_count=1)
        assert evaluate_message_violations(segnali, config) == ()

    def test_link_non_in_whitelist_viola(self):
        config = self._config(anti_link=AntiLinkConfig(mode="whitelist", whitelist=("ok.com",)))
        segnali = MessageSignals(content="vai su https://cattivo.com ora")
        assert evaluate_message_violations(segnali, config) == (VIOLATION_ANTI_LINK,)

    def test_spam_messaggi_oltre_soglia_viola(self):
        config = self._config(anti_spam_messages=RateFilterConfig(enabled=True, max_count=3))
        segnali = MessageSignals(content="spam", recent_message_count=4)
        assert evaluate_message_violations(segnali, config) == (VIOLATION_SPAM_MESSAGES,)

    def test_spam_emoji_oltre_soglia_viola(self):
        config = self._config(anti_spam_emoji=ThresholdFilterConfig(enabled=True, max_count=5))
        segnali = MessageSignals(content="tante emoji", emoji_count=6)
        assert evaluate_message_violations(segnali, config) == (VIOLATION_SPAM_EMOJI,)

    def test_spam_sticker_conta_solo_se_il_messaggio_ha_uno_sticker(self):
        config = self._config(anti_spam_sticker=RateFilterConfig(enabled=True, max_count=2))
        # recent_sticker_count alto ma QUESTO messaggio non ha sticker: non deve valere
        segnali = MessageSignals(content="", sticker_count=0, recent_sticker_count=5)
        assert VIOLATION_SPAM_STICKER not in evaluate_message_violations(segnali, config)

    def test_spam_sticker_con_sticker_e_oltre_soglia_viola(self):
        config = self._config(anti_spam_sticker=RateFilterConfig(enabled=True, max_count=2))
        segnali = MessageSignals(content="", sticker_count=1, recent_sticker_count=3)
        assert evaluate_message_violations(segnali, config) == (VIOLATION_SPAM_STICKER,)

    def test_mass_mention_oltre_soglia_viola(self):
        config = self._config(anti_mass_mention=ThresholdFilterConfig(enabled=True, max_count=5))
        segnali = MessageSignals(content="ping", mention_count=6)
        assert evaluate_message_violations(segnali, config) == (VIOLATION_MASS_MENTION,)

    def test_attachment_spam_conta_solo_se_il_messaggio_ha_allegati(self):
        config = self._config(anti_attachment_spam=RateFilterConfig(enabled=True, max_count=2))
        segnali = MessageSignals(content="", attachment_count=0, recent_attachment_count=5)
        assert VIOLATION_ATTACHMENT_SPAM not in evaluate_message_violations(segnali, config)

    def test_attachment_spam_con_allegati_e_oltre_soglia_viola(self):
        config = self._config(anti_attachment_spam=RateFilterConfig(enabled=True, max_count=2))
        segnali = MessageSignals(content="", attachment_count=1, recent_attachment_count=3)
        assert evaluate_message_violations(segnali, config) == (VIOLATION_ATTACHMENT_SPAM,)

    def test_piu_violazioni_insieme_restituite_in_ordine_fisso(self):
        config = self._config(
            anti_caps=CapsFilterConfig(enabled=True, threshold_percent=50, min_length=3),
            anti_mass_mention=ThresholdFilterConfig(enabled=True, max_count=1),
        )
        segnali = MessageSignals(content="TUTTO MAIUSCOLO", mention_count=5)
        risultato = evaluate_message_violations(segnali, config)
        assert risultato == (VIOLATION_CAPS, VIOLATION_MASS_MENTION)

    def test_filtro_disattivato_non_viola_anche_sopra_soglia(self):
        config = self._config(anti_spam_emoji=ThresholdFilterConfig(enabled=False, max_count=1))
        segnali = MessageSignals(content="", emoji_count=99)
        assert evaluate_message_violations(segnali, config) == ()

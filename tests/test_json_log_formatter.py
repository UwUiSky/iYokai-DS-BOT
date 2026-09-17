"""
tests/test_json_log_formatter.py
====================================
Test di core/json_log_formatter.py. Due livelli: LogRecord costruiti
a mano (controllo preciso sui campi) e un logger vero con un handler
in memoria (verifica che il wiring reale — interpolazione %s,
cattura dell'exc_info — funzioni, non solo la funzione format() in
isolamento).
"""

import io
import json
import logging

from core.json_log_formatter import JSONFormatter


def _make_record(msg: str, args=(), level=logging.INFO, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=exc_info,
    )


class TestFormatDirettoSuLogRecord:
    def test_output_e_json_valido(self):
        formatter = JSONFormatter()
        record = _make_record("messaggio di prova")
        risultato = formatter.format(record)

        parsed = json.loads(risultato)  # solleva se non è JSON valido
        assert parsed["message"] == "messaggio di prova"

    def test_campi_essenziali_presenti(self):
        formatter = JSONFormatter()
        record = _make_record("test")
        parsed = json.loads(formatter.format(record))

        assert "timestamp" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "message" in parsed

    def test_livello_corretto(self):
        formatter = JSONFormatter()
        record = _make_record("errore", level=logging.ERROR)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "ERROR"

    def test_nome_logger_corretto(self):
        formatter = JSONFormatter()
        record = _make_record("test")
        parsed = json.loads(formatter.format(record))
        assert parsed["logger"] == "test.logger"

    def test_messaggio_con_argomenti_interpolati(self):
        # getMessage() fa l'interpolazione %s — il campo "message"
        # nel JSON deve contenere il testo GIÀ formattato, non i
        # placeholder grezzi (altrimenti un tool che legge il JSON
        # dovrebbe rifare l'interpolazione da solo).
        formatter = JSONFormatter()
        record = _make_record("utente %s ha fatto %s", args=("Mario", "login"))
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "utente Mario ha fatto login"

    def test_nessuna_eccezione_nessun_campo_exception(self):
        formatter = JSONFormatter()
        record = _make_record("senza errori")
        parsed = json.loads(formatter.format(record))
        assert "exception" not in parsed

    def test_con_eccezione_il_traceback_e_incluso(self):
        formatter = JSONFormatter()
        try:
            raise ValueError("qualcosa è andato storto")
        except ValueError:
            import sys
            record = _make_record("errore catturato", exc_info=sys.exc_info())

        parsed = json.loads(formatter.format(record))
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "qualcosa è andato storto" in parsed["exception"]

    def test_caratteri_non_ascii_non_vengono_convertiti_in_escape(self):
        # ensure_ascii=False: un log con "città" resta leggibile come
        # "città", non "citt\u00e0" — più comodo da leggere a occhio
        # nel file, senza perdere validità JSON.
        formatter = JSONFormatter()
        record = _make_record("città è una parola con lettera accentata")
        risultato = formatter.format(record)
        assert "città" in risultato


class TestIntegrazioneConLoggerReale:
    def test_logger_reale_produce_una_riga_json_per_chiamata(self):
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(JSONFormatter())

        logger = logging.getLogger("test.integrazione.json")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False  # non duplicare sull'handler root nei test

        try:
            logger.info("evento di test con valore %d", 42)
        finally:
            logger.removeHandler(handler)

        riga = buffer.getvalue().strip()
        parsed = json.loads(riga)
        assert parsed["message"] == "evento di test con valore 42"
        assert parsed["logger"] == "test.integrazione.json"

    def test_logger_reale_con_logger_exception_include_traceback(self):
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(JSONFormatter())

        logger = logging.getLogger("test.integrazione.json.exc")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False

        try:
            try:
                raise RuntimeError("errore di integrazione")
            except RuntimeError:
                logger.exception("fallito durante il test")
        finally:
            logger.removeHandler(handler)

        parsed = json.loads(buffer.getvalue().strip())
        assert "exception" in parsed
        assert "RuntimeError" in parsed["exception"]

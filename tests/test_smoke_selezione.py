"""
tests/test_smoke_selezione.py
=============================
Test di scripts/smoke.py: la scelta dei test a partire dai file cambiati.
"""

import importlib.util
import pathlib

RADICE = pathlib.Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("smoke", RADICE / "scripts" / "smoke.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


def _radice_finta(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ticket.py").write_text("from cogs.tickets.tickets import TicketCog\n")
    (tmp_path / "tests" / "test_safe.py").write_text("from core import safe_http\n")
    (tmp_path / "tests" / "test_altro.py").write_text("from core.scheduler import scheduler\n")
    (tmp_path / "tests" / "test_command_policy.py").write_text("# struttura\n")
    return tmp_path


def test_sceglie_i_test_che_importano_il_modulo_cambiato(tmp_path):
    radice = _radice_finta(tmp_path)

    scelti = smoke.seleziona_test(["cogs/tickets/tickets.py"], radice)

    assert "tests/test_ticket.py" in scelti
    assert "tests/test_altro.py" not in scelti


def test_riconosce_anche_from_pacchetto_import_modulo(tmp_path):
    radice = _radice_finta(tmp_path)

    scelti = smoke.seleziona_test(["core/safe_http.py"], radice)

    assert "tests/test_safe.py" in scelti


def test_un_test_cambiato_viene_eseguito(tmp_path):
    radice = _radice_finta(tmp_path)

    scelti = smoke.seleziona_test(["tests/test_altro.py"], radice)

    assert "tests/test_altro.py" in scelti


def test_i_controlli_di_struttura_ci_sono_sempre(tmp_path):
    radice = _radice_finta(tmp_path)

    scelti = smoke.seleziona_test(["README.md"], radice)

    assert scelti == ["tests/test_command_policy.py"]


def test_i_file_che_toccano_tutto_chiedono_la_suite_completa():
    delicati = smoke.serve_la_suite_completa(
        ["main.py", "cogs/fun/entertainment.py", "core/migrations/0005_x.sql"]
    )

    assert delicati == ["main.py", "core/migrations/0005_x.sql"]


def test_i_controlli_di_struttura_elencati_esistono_davvero():
    mancanti = [nome for nome in smoke.TEST_SEMPRE if not (RADICE / nome).exists()]

    assert mancanti == []

"""
tests/test_ip_client_unico.py
=============================
Blocco A, voce 10: dietro il reverse proxy l'IP vero si legge in UN solo posto. Il bot rifiuta di partire se
ascolta solo in locale e nessun proxy è fidato. Cricchetto: nessun altro file di produzione legge
`X-Forwarded-For` per decidere l'IP.
"""

import pathlib
from types import SimpleNamespace

import pytest

from core import config as modulo_config
from core import web_panel_logic as logica

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Chi può nominare l'intestazione: la funzione unica, chi le passa il valore, chi cerca solo se c'è e il segnale VPN.
PERMESSI = {
    "core/web_panel_logic.py", "core/web_panel_server.py", "core/custom_webhook_server.py",
    "core/verify_vpn_logic.py", "core/alt_detection_logic.py", "core/config.py",  # config: solo un commento
}


def test_solo_pochi_file_nominano_x_forwarded_for():
    trovati = set()
    for percorso in list(ROOT.glob("core/**/*.py")) + list(ROOT.glob("cogs/**/*.py")) + [ROOT / "main.py"]:
        if "x-forwarded-for" in percorso.read_text(encoding="utf-8").lower():
            trovati.add(str(percorso.relative_to(ROOT)))
    assert trovati <= PERMESSI, f"una seconda regola per l'IP del client: {sorted(trovati - PERMESSI)}"


def _richiesta(remoto, inoltrato=None):
    return SimpleNamespace(remote=remoto, headers={"X-Forwarded-For": inoltrato} if inoltrato else {})


def test_ip_del_client_legge_l_intestazione_solo_dal_proxy_fidato(monkeypatch):
    import core.config as c

    monkeypatch.setattr(c, "config", SimpleNamespace(WEB_PANEL_TRUSTED_PROXY="127.0.0.1,::1"))
    assert logica.ip_del_client(_richiesta("127.0.0.1", "1.1.1.1, 2.2.2.2")) == "2.2.2.2"  # l'ultimo lo scrive il proxy
    assert logica.ip_del_client(_richiesta("::1", "3.3.3.3")) == "3.3.3.3"
    assert logica.ip_del_client(_richiesta("9.9.9.9", "3.3.3.3")) == "9.9.9.9"  # non fidato: l'intestazione si ignora
    assert logica.ip_del_client(_richiesta("127.0.0.1")) == "127.0.0.1"


def test_il_valore_di_base_e_il_proxy_locale(monkeypatch):
    monkeypatch.delenv("WEB_PANEL_TRUSTED_PROXY", raising=False)
    assert modulo_config._proxy_fidati_da_ambiente() == "127.0.0.1,::1"


def test_nessuno_con_ascolto_locale_non_parte(monkeypatch):
    monkeypatch.setenv("WEB_PANEL_TRUSTED_PROXY", "nessuno")
    monkeypatch.setenv("WEB_BIND_HOST", "127.0.0.1")
    with pytest.raises(SystemExit):
        modulo_config._proxy_fidati_da_ambiente()
    monkeypatch.setenv("WEB_BIND_HOST", "0.0.0.0")  # esposto davvero: nessun proxy è una scelta ammessa
    assert modulo_config._proxy_fidati_da_ambiente() == ""
    monkeypatch.setenv("WEB_PANEL_TRUSTED_PROXY", "10.0.0.5")
    assert modulo_config._proxy_fidati_da_ambiente() == "10.0.0.5"

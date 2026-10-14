"""
tests/test_web_panel_logic.py
=============================
Regole di sicurezza del pannello web (SPEC §24.1): accensione, state
OAuth2, CSRF, limite di frequenza, IP dietro il proxy, intestazioni.
"""

import secrets

from core import web_panel_logic as regole

CHIAVE = secrets.token_urlsafe(48)


def test_pannello_spento_senza_variabili():
    assert regole.pannello_configurato("1", "s", CHIAVE, "https://pannello.example")
    assert not regole.pannello_configurato("", "s", CHIAVE, "https://pannello.example")
    assert not regole.pannello_configurato("1", "", CHIAVE, "https://pannello.example")
    assert not regole.pannello_configurato("1", "s", "corta", "https://pannello.example")
    assert not regole.pannello_configurato("1", "s", CHIAVE, "")
    assert not regole.pannello_configurato("1", "s", CHIAVE, "ftp://x")


def test_state_valido_solo_con_il_suo_cookie():
    state, cookie = regole.nuovo_state(CHIAVE, adesso=1000)
    assert regole.state_valido(CHIAVE, cookie, state, adesso=1001)
    assert not regole.state_valido(CHIAVE, cookie, state + "x", adesso=1001)
    assert not regole.state_valido(CHIAVE, None, state, adesso=1001)
    assert not regole.state_valido(CHIAVE, cookie, state, adesso=1000 + regole.DURATA_STATE_SECONDI + 1)
    altra = secrets.token_urlsafe(48)
    assert not regole.state_valido(altra, cookie, state, adesso=1001)
    nonce, scade, firma = cookie.split(".")
    assert not regole.state_valido(CHIAVE, f"{nonce}.{int(scade) + 999}.{firma}", state, adesso=1001)


def test_csrf_legato_alla_sessione():
    a, b = regole.nuovo_token(), regole.nuovo_token()
    assert regole.csrf_valido(CHIAVE, a, regole.csrf_per(CHIAVE, a))
    assert not regole.csrf_valido(CHIAVE, b, regole.csrf_per(CHIAVE, a))
    assert not regole.csrf_valido(CHIAVE, a, None)


def test_impronta_non_e_il_token():
    token = regole.nuovo_token()
    assert regole.impronta(token) != token and len(regole.impronta(token)) == 64


def test_url_autorizzazione_chiede_solo_identify():
    url = regole.url_autorizzazione("42", "https://p.example/callback", "abc")
    assert url.startswith("https://discord.com/oauth2/authorize?")
    assert "scope=identify&" in url and "state=abc" in url and "guilds" not in url


def test_limite_frequenza():
    limite = regole.LimiteFrequenza(2, 10, chiavi_massime=3)
    assert limite.consenti("a", 0) and limite.consenti("a", 1)
    assert not limite.consenti("a", 2)
    assert limite.consenti("a", 11)
    for chiave in "bcdef":
        limite.consenti(chiave, 12)
    assert len(limite._colpi) == 3


def test_ip_cliente_si_fida_del_proxy_solo_in_locale():
    assert regole.ip_cliente("127.0.0.1", "1.2.3.4, 5.6.7.8") == "5.6.7.8"
    assert regole.ip_cliente("9.9.9.9", "1.2.3.4") == "9.9.9.9"


def test_intestazioni_sicurezza():
    h = regole.intestazioni_sicurezza(https=True)
    assert "default-src 'none'" in h["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["X-Content-Type-Options"] == "nosniff"
    # Con "no-referrer" i browser mandano `Origin: null` sui POST dei moduli
    # (Fetch, "append a request Origin header") e il pannello li rifiuterebbe tutti.
    assert h["Referrer-Policy"] == "same-origin"
    assert "Strict-Transport-Security" in h
    assert "Strict-Transport-Security" not in regole.intestazioni_sicurezza(https=False)

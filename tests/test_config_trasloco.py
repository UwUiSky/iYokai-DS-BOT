"""
tests/test_config_trasloco.py
=============================
CFG-043 (#122): chiave di configurazione per portare le impostazioni su un altro server. L'esportazione scrive il
nome dei canali e dei ruoli citati; l'importazione rimappa per nome e non scrive mai ID che non esistono qui.
"""

from unittest.mock import MagicMock

import pytest

from core import config_trasloco as ct


def _oggetto(i, nome):
    o = MagicMock()
    o.id, o.name = i, nome
    return o


def _guild(guild_id, canali=(), ruoli=()):
    g = MagicMock()
    g.id = guild_id
    tutti_ruoli = [_oggetto(guild_id, "@everyone"), *[_oggetto(i, n) for i, n in ruoli]]
    tutti_canali = [_oggetto(i, n) for i, n in canali]
    g.roles, g.channels = tutti_ruoli, tutti_canali
    g.get_role = lambda i: next((r for r in tutti_ruoli if r.id == i), None)
    g.get_channel = lambda i: next((c for c in tutti_canali if c.id == i), None)
    return g


SETTINGS = {
    "log_channel_id": 10,
    "ticket_support_role_ids": [20, 21],
    "policy_ruoli_richiesti": {"fun": [20], "immagini": [99]},
    "progressi_attivi": True,
    "policy_ignora_utenti": [777],
}


def test_esporta_i_nomi_solo_di_cio_che_esiste():
    g = _guild(1, canali=[(10, "log")], ruoli=[(20, "Staff")])
    rif = ct.raccogli_riferimenti(SETTINGS, g)
    assert rif == {"10": {"tipo": "canale", "nome": "log"}, "20": {"tipo": "ruolo", "nome": "Staff"}}
    assert ct.errore_riferimenti(rif) is None


def test_stesso_server_gli_id_che_esistono_restano():
    g = _guild(1, canali=[(10, "log")], ruoli=[(20, "Staff"), (21, "Aiuto"), (99, "Foto")])
    esito = ct.rimappa_impostazioni(g, SETTINGS, None)
    assert esito.settings == SETTINGS and esito.rimappati == 0 and esito.tolti == 0


def test_altro_server_si_ritrova_per_nome_e_il_resto_si_toglie():
    rif = {
        "10": {"tipo": "canale", "nome": "log"},
        "20": {"tipo": "ruolo", "nome": "Staff"},
        "21": {"tipo": "ruolo", "nome": "Aiuto"},
        "99": {"tipo": "ruolo", "nome": "Foto"},
    }
    g = _guild(2, canali=[(110, "log")], ruoli=[(120, "Staff"), (121, "Aiuto"), (122, "Aiuto")])  # «Aiuto» è doppio
    esito = ct.rimappa_impostazioni(g, SETTINGS, rif)
    assert esito.settings["log_channel_id"] == 110
    assert esito.settings["ticket_support_role_ids"] == [120]  # il nome ambiguo non si indovina
    assert esito.settings["policy_ruoli_richiesti"] == {"fun": [120]}  # «Foto» non c'è: la voce sparisce
    assert esito.settings["progressi_attivi"] is True and esito.settings["policy_ignora_utenti"] == [777]
    assert esito.rimappati == 3 and esito.tolti == 2


def test_senza_nomi_nessun_id_di_un_altro_server_passa():
    g = _guild(2, canali=[(110, "log")], ruoli=[(120, "Staff")])
    esito = ct.rimappa_impostazioni(g, SETTINGS, {})
    for chiave in ("log_channel_id", "ticket_support_role_ids", "policy_ruoli_richiesti"):
        assert chiave not in esito.settings
    assert set(esito.chiavi_tolte) == {"log_channel_id", "ticket_support_role_ids", "policy_ruoli_richiesti"}


def test_un_nome_non_apre_un_oggetto_di_un_altro_tipo_ne_everyone():
    rif = {"20": {"tipo": "canale", "nome": "Staff"}, "10": {"tipo": "canale", "nome": "@everyone"}}
    g = _guild(2, canali=[(110, "Staff")], ruoli=[(120, "Staff")])
    esito = ct.rimappa_impostazioni(g, {"ticket_support_role_ids": [20], "log_channel_id": 10}, rif)
    assert esito.settings == {}  # 20 è dichiarato canale ma la chiave vuole un ruolo
    # @everyone ha l'id del server: non è mai un ruolo valido
    esito = ct.rimappa_impostazioni(g, {"mute_role_id": 2}, {"2": {"tipo": "ruolo", "nome": "@everyone"}})
    assert "mute_role_id" not in esito.settings


def test_server_non_in_memoria_non_si_tocca_niente():
    g = _guild(2)
    g.roles = []
    with pytest.raises(ct.ServerNonPronto):
        ct.rimappa_impostazioni(g, SETTINGS, None)
    # senza ID da controllare non serve sapere cosa esiste
    assert ct.rimappa_impostazioni(g, {"progressi_attivi": True}, None).settings == {"progressi_attivi": True}


def test_il_campo_riferimenti_e_validato_voce_per_voce():
    assert ct.errore_riferimenti(None) is None
    brutti = [
        [],
        {"x": {"tipo": "canale", "nome": "a"}},
        {"１２": {"tipo": "canale", "nome": "a"}},
        {"5": {"tipo": "utente", "nome": "a"}},
        {"5": {"tipo": "canale", "nome": ""}},
        {"5": {"tipo": "canale", "nome": "x" * 101}},
        {"5": "canale"},
        {str(2**63): {"tipo": "canale", "nome": "a"}},
        {str(n): {"tipo": "canale", "nome": "a"} for n in range(1, ct.MAX_RIFERIMENTI + 2)},
    ]
    for brutto in brutti:
        assert ct.errore_riferimenti(brutto) is not None, brutto


def test_un_elenco_vuoto_resta_vuoto():
    g = _guild(2, canali=[(110, "log")], ruoli=[(120, "Staff")])
    esito = ct.rimappa_impostazioni(g, {"spam_trap_staff_role_ids": [], "ticket_support_role_ids": [5]}, None)
    assert esito.settings == {"spam_trap_staff_role_ids": []}

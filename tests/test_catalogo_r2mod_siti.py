"""
tests/test_catalogo_r2mod_siti.py
=================================
Blocco dei siti che catturano l'IP, per adulti o con malware (AMD-031): liste, categorie scelte, whitelist, salvataggio.
"""

import pytest

from core import phishing_logic as ph
from core.automod_advanced_logic import (
    VIOLATION_SITI_PERICOLOSI,
    AutomodAdvancedConfig,
    MessageSignals,
    evaluate_message_violations,
)


# AMD-031
def test_le_liste_di_partenza_ci_sono_e_quella_dei_malware_e_vuota_di_proposito():
    assert "grabify.link" in ph.lista_siti("ip_logger") and "pornhub.com" in ph.lista_siti("adulti")
    assert ph.lista_siti("malware") == frozenset() and ph.lista_siti("altro") == frozenset()


# AMD-031
def test_si_blocca_solo_la_categoria_accesa_anche_dai_sottodomini_e_la_whitelist_vince():
    assert ph.e_sito_pericoloso(["iplogger.org"], ("ip_logger",))
    assert ph.e_sito_pericoloso(["www.pornhub.com"], ("adulti",))
    assert not ph.e_sito_pericoloso(["pornhub.com"], ("ip_logger",))
    assert not ph.e_sito_pericoloso(["iplogger.org"], ())
    assert not ph.e_sito_pericoloso(["iplogger.org"], ("malware",))  # categoria vuota: niente
    assert not ph.e_sito_pericoloso(["iplogger.org"], ("ip_logger",), consentiti=["iplogger.org"])
    assert not ph.e_sito_pericoloso(["esempio.it", "discord.com"], ("ip_logger", "adulti", "malware"))


def _segnali(testo):
    return MessageSignals(content=testo)


# AMD-031
def test_il_filtro_scatta_solo_se_acceso_e_con_il_link_giusto():
    spento = AutomodAdvancedConfig()
    acceso = AutomodAdvancedConfig(phishing_siti=("ip_logger",))
    link = "guarda qui https://grabify.link/ABC123"
    assert VIOLATION_SITI_PERICOLOSI not in evaluate_message_violations(_segnali(link), spento)
    assert VIOLATION_SITI_PERICOLOSI in evaluate_message_violations(_segnali(link), acceso)
    assert VIOLATION_SITI_PERICOLOSI not in evaluate_message_violations(_segnali("ciao https://esempio.it"), acceso)


# AMD-031
def test_le_categorie_si_salvano_e_si_rileggono_e_i_valori_strani_si_scartano():
    import json

    from core.repositories import automod_advanced_repo as repo

    base = repo._default_settings(1)
    settings = repo.AutomodAdvancedSettings(**{**base.__dict__, "config": AutomodAdvancedConfig(phishing_siti=("ip_logger", "adulti"))}) \
        if hasattr(repo, "AutomodAdvancedSettings") else None
    dati = json.loads(repo._to_json(settings))
    assert dati["config"]["phishing_siti"] == ["ip_logger", "adulti"] if "config" in dati else dati["phishing_siti"] == ["ip_logger", "adulti"]
    assert repo._from_json(1, repo._to_json(settings)).config.phishing_siti == ("ip_logger", "adulti")
    sporco = json.loads(repo._to_json(settings))
    (sporco["config"] if "config" in sporco else sporco)["phishing_siti"] = ["adulti", "x", 5]
    assert repo._from_json(1, json.dumps(sporco)).config.phishing_siti == ("adulti",)
    assert repo._from_json(1, repo._to_json(base)).config.phishing_siti == ()

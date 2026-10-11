"""
tests/test_security_fiducia_117.py
==================================
#117 (SIC-001, SIC-018, SIC-019, SIC-020): soglia oraria, due livelli di
fiducia, fiducia limitata a un tipo di azione o a una categoria,
esenzione di un webhook. Logica pura + salvataggio.
"""

import pytest

from core.repositories.security_repo import SecuritySettings, _from_json, _to_json
from core.security_logic import (
    AntiNukeConfig,
    AntiRaidConfig,
    NUKE_CATEGORY_CHANNEL,
    NUKE_CATEGORY_ROLE,
    TrustEntry,
    actor_is_trusted,
    is_extra_owner,
    is_nuke_violation,
)


def _cfg(**kw):
    return AntiNukeConfig(enabled=True, **kw)


class TestSogliaOraria:
    def test_sotto_la_soglia_al_minuto_ma_sopra_quella_oraria_e_violazione(self):
        cfg = _cfg(channel_max=3, channel_hour_max=10)
        assert is_nuke_violation(1, NUKE_CATEGORY_CHANNEL, 2, cfg, count_in_hour=11) is True

    def test_sotto_entrambe_non_e_violazione(self):
        cfg = _cfg(channel_max=3, channel_hour_max=10)
        assert is_nuke_violation(1, NUKE_CATEGORY_CHANNEL, 2, cfg, count_in_hour=10) is False

    def test_soglia_oraria_zero_e_spenta(self):
        cfg = _cfg(channel_max=3, channel_hour_max=0)
        assert is_nuke_violation(1, NUKE_CATEGORY_CHANNEL, 2, cfg, count_in_hour=500) is False


class TestFiducia:
    def test_fidato_semplice_e_esente_da_tutto(self):
        cfg = _cfg(trusted_ids=(5,))
        assert actor_is_trusted(5, NUKE_CATEGORY_ROLE, cfg) is True

    def test_fiducia_limitata_a_una_categoria_di_azione(self):
        cfg = _cfg(trust_entries=(TrustEntry(target_id=7, categories=(NUKE_CATEGORY_CHANNEL,)),))
        assert actor_is_trusted(7, NUKE_CATEGORY_CHANNEL, cfg) is True
        assert actor_is_trusted(7, NUKE_CATEGORY_ROLE, cfg) is False

    def test_fiducia_limitata_a_una_categoria_di_canali(self):
        cfg = _cfg(trust_entries=(TrustEntry(target_id=7, channel_category_id=900),))
        assert actor_is_trusted(7, NUKE_CATEGORY_CHANNEL, cfg, channel_category_id=900) is True
        assert actor_is_trusted(7, NUKE_CATEGORY_CHANNEL, cfg, channel_category_id=901) is False
        assert actor_is_trusted(7, NUKE_CATEGORY_CHANNEL, cfg, channel_category_id=None) is False

    def test_webhook_esente_solo_se_e_il_bersaglio_della_voce(self):
        cfg = _cfg(trust_entries=(TrustEntry(target_id=55, kind="webhook"),))
        assert actor_is_trusted(1, "webhook", cfg, target_id=55) is True
        assert actor_is_trusted(1, "webhook", cfg, target_id=56) is False
        # Un ID di webhook non rende fidato un utente con lo stesso numero.
        assert actor_is_trusted(55, "webhook", cfg, target_id=None) is False

    def test_extra_owner_e_distinto_dal_fidato(self):
        cfg = _cfg(
            trusted_ids=(5,),
            trust_entries=(TrustEntry(target_id=8, level="extra_owner"),),
        )
        assert is_extra_owner(8, cfg) is True
        assert is_extra_owner(5, cfg) is False
        # L'extra owner e' esente come l'owner.
        assert actor_is_trusted(8, NUKE_CATEGORY_ROLE, cfg) is True

    def test_violazione_ignora_chi_e_fidato_per_quella_categoria(self):
        cfg = _cfg(channel_max=1, trust_entries=(TrustEntry(target_id=7, categories=(NUKE_CATEGORY_CHANNEL,)),))
        assert is_nuke_violation(7, NUKE_CATEGORY_CHANNEL, 50, cfg) is False
        assert is_nuke_violation(7, NUKE_CATEGORY_ROLE, 50, cfg) is True


class TestSalvataggio:
    def test_i_campi_nuovi_sopravvivono_al_salvataggio(self):
        nuke = AntiNukeConfig(
            enabled=True,
            channel_hour_max=12,
            punish_action="quarantine",
            trust_entries=(
                TrustEntry(target_id=8, level="extra_owner"),
                TrustEntry(target_id=9, categories=(NUKE_CATEGORY_CHANNEL,), channel_category_id=33),
                TrustEntry(target_id=10, kind="webhook"),
            ),
            role_perm_guard="all",
            member_role_guard=True,
            vanity_guard=True,
            bot_add_guard=True,
        )
        s = SecuritySettings(1, AntiRaidConfig(), nuke, None, None)
        letto = _from_json(1, _to_json(s)).anti_nuke
        assert letto == nuke

    def test_vecchia_riga_senza_i_campi_nuovi_si_legge(self):
        letto = _from_json(1, '{"anti_nuke": {"enabled": true, "trusted_ids": [4], "punish_action": "strip_roles"}}')
        assert letto.anti_nuke.trusted_ids == (4,)
        assert letto.anti_nuke.punish_action == "strip_roles"
        assert letto.anti_nuke.trust_entries == ()
        assert letto.anti_nuke.role_perm_guard == "off"

    def test_il_default_della_punizione_e_la_quarantena(self):
        assert AntiNukeConfig().punish_action == "quarantine"

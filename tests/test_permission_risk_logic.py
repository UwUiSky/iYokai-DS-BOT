"""
tests/test_permission_risk_logic.py
=======================================
Test di core/permission_risk_logic.py — logica pura, nessuna
dipendenza da Discord.
"""

from core.permission_risk_logic import (
    CRITICAL_PERMISSIONS,
    critical_permissions_of,
    is_risky_role,
    newly_gained_critical_permissions,
)


class TestCriticalPermissionsOf:
    def test_nessun_permesso_critico(self):
        flags = {"change_nickname": True, "send_messages": True}
        assert critical_permissions_of(flags) == []

    def test_un_permesso_critico(self):
        flags = {"ban_members": True, "send_messages": True}
        assert critical_permissions_of(flags) == ["ban_members"]

    def test_piu_permessi_critici_nellordine_della_costante(self):
        flags = {"manage_webhooks": True, "administrator": True, "kick_members": True}
        risultato = critical_permissions_of(flags)
        # L'ordine deve seguire CRITICAL_PERMISSIONS, non l'ordine di
        # inserimento nel dizionario in ingresso.
        assert risultato == ["administrator", "kick_members", "manage_webhooks"]

    def test_permesso_critico_assente_dal_dizionario_non_solleva(self):
        # Un dizionario incompleto (non tutti i permessi Discord
        # passati) non deve far fallire la funzione — assente
        # equivale a False.
        assert critical_permissions_of({}) == []

    def test_tutti_i_permessi_critici_insieme(self):
        flags = {p: True for p in CRITICAL_PERMISSIONS}
        assert critical_permissions_of(flags) == CRITICAL_PERMISSIONS


class TestIsRiskyRole:
    def test_ruolo_senza_permessi_critici_non_e_rischioso(self):
        assert is_risky_role({"send_messages": True}) is False

    def test_ruolo_con_un_permesso_critico_e_rischioso(self):
        assert is_risky_role({"manage_roles": True}) is True


class TestNewlyGainedCriticalPermissions:
    def test_ruolo_critico_aggiunto_compare_nel_risultato(self):
        risultato = newly_gained_critical_permissions(
            before_role_ids={1},
            after_role_ids={1, 2},
            role_critical_permissions={2: ["administrator"]},
        )
        assert risultato == {2: ["administrator"]}

    def test_ruolo_aggiunto_senza_permessi_critici_non_compare(self):
        risultato = newly_gained_critical_permissions(
            before_role_ids={1},
            after_role_ids={1, 2},
            role_critical_permissions={2: []},
        )
        assert risultato == {}

    def test_ruolo_rimosso_non_compare_mai_anche_se_critico(self):
        # Caso importante: un ruolo critico RIMOSSO non è un alert
        # (il rischio diminuisce, non aumenta) — solo le AGGIUNTE
        # contano.
        risultato = newly_gained_critical_permissions(
            before_role_ids={1, 2},
            after_role_ids={1},
            role_critical_permissions={2: ["administrator"]},
        )
        assert risultato == {}

    def test_ruolo_gia_posseduto_non_ricompare(self):
        # Il ruolo era già presente PRIMA: non è una nuova acquisizione.
        risultato = newly_gained_critical_permissions(
            before_role_ids={1, 2},
            after_role_ids={1, 2},
            role_critical_permissions={2: ["administrator"]},
        )
        assert risultato == {}

    def test_nessun_cambiamento_risultato_vuoto(self):
        risultato = newly_gained_critical_permissions(
            before_role_ids=set(), after_role_ids=set(), role_critical_permissions={}
        )
        assert risultato == {}

    def test_piu_ruoli_critici_aggiunti_insieme(self):
        risultato = newly_gained_critical_permissions(
            before_role_ids=set(),
            after_role_ids={1, 2},
            role_critical_permissions={1: ["ban_members"], 2: ["administrator"]},
        )
        assert risultato == {1: ["ban_members"], 2: ["administrator"]}

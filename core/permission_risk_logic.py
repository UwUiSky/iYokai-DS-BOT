"""
core/permission_risk_logic.py
================================
Logica pura della Permission Risk Heatmap (SPEC.md §7.4, estensione
del Permission Auditor già previsto — BACKLOG.md §11). Nessuna
dipendenza da discord.py: il chiamante (cogs/security/permission_
heatmap.py) converte i permessi reali di un ruolo in un dizionario
{nome_permesso: bool} prima di passarlo qui.
"""

from __future__ import annotations

# Permessi considerati "critici" per una heatmap — un sottoinsieme
# deliberatamente ristretto dei permessi Discord: non ogni permesso
# è un rischio (es. "change_nickname" non è pericoloso), quelli qui
# sono i permessi che, in mano alla persona sbagliata, danneggiano
# irreversibilmente il server o i suoi membri.
CRITICAL_PERMISSIONS: list[str] = [
    "administrator",
    "ban_members",
    "kick_members",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
]


def critical_permissions_of(permission_flags: dict[str, bool]) -> list[str]:
    """
    Quali permessi critici sono attivi, nell'ordine di
    CRITICAL_PERMISSIONS (non l'ordine del dizionario in ingresso,
    che con discord.Permissions non è garantito essere stabile).
    """
    return [
        name for name in CRITICAL_PERMISSIONS if permission_flags.get(name, False)
    ]


def is_risky_role(permission_flags: dict[str, bool]) -> bool:
    return len(critical_permissions_of(permission_flags)) > 0


def newly_gained_critical_permissions(
    before_role_ids: set[int],
    after_role_ids: set[int],
    role_critical_permissions: dict[int, list[str]],
) -> dict[int, list[str]]:
    """
    Per l'alert automatico "qualcuno ha appena ricevuto un permesso
    critico": quali RUOLI APPENA AGGIUNTI portano permessi critici,
    e quali. role_critical_permissions è {role_id: [permessi critici
    di quel ruolo]} — già calcolato altrove con
    critical_permissions_of(), non ricalcolato qui.

    Un ruolo rimosso, o un ruolo aggiunto senza permessi critici, non
    compare nel risultato — solo i casi che meritano davvero un
    alert.
    """
    aggiunti = after_role_ids - before_role_ids
    risultato = {}
    for role_id in aggiunti:
        critici = role_critical_permissions.get(role_id, [])
        if critici:
            risultato[role_id] = critici
    return risultato

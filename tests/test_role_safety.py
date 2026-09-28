"""
tests/test_role_safety.py
=============================
Test di core/role_safety.py — logica pura, nessuna dipendenza da
Discord reale (usa i finti fedeli di tests/support/discord_fakes.py).
Funzioni coperte: SEC-4/SEC-17.
"""

from __future__ import annotations

import discord
import pytest

from core.role_safety import check_role_assignable
from tests.support.discord_fakes import fake_guild, fake_member, fake_role


def _setup(*, ruolo_bot_posizione: int, ruolo_actor_posizione: int, owner_id: int = 1):
    bot_member = fake_member(user_id=999, name="Yokai Bot", bot=True)
    ruolo_bot = fake_role(role_id=100, name="Yokai Bot", position=ruolo_bot_posizione)
    bot_member.top_role = ruolo_bot

    ruolo_actor = fake_role(role_id=200, name="Staff", position=ruolo_actor_posizione)
    actor = fake_member(user_id=2, name="mod", roles=[ruolo_actor])
    actor.top_role = ruolo_actor

    server = fake_guild(guild_id=1, owner_id=owner_id, me=bot_member)
    return server, actor


def test_rifiuta_everyone():
    server, actor = _setup(ruolo_bot_posizione=10, ruolo_actor_posizione=5)
    everyone = fake_role(role_id=1, name="@everyone", position=0)
    everyone.is_default.return_value = True

    motivo = check_role_assignable(server, everyone, actor, self_service=False)

    assert motivo is not None
    assert "everyone" in motivo.lower()


def test_rifiuta_ruolo_gestito_da_integrazione():
    server, actor = _setup(ruolo_bot_posizione=10, ruolo_actor_posizione=5)
    ruolo = fake_role(role_id=50, name="Booster", position=1, managed=True)

    motivo = check_role_assignable(server, ruolo, actor, self_service=False)

    assert motivo is not None
    assert "integrazione" in motivo.lower()


def test_rifiuta_ruolo_sopra_il_bot():
    server, actor = _setup(ruolo_bot_posizione=10, ruolo_actor_posizione=5)
    ruolo = fake_role(role_id=50, name="Troppo Alto", position=15)

    motivo = check_role_assignable(server, ruolo, actor, self_service=False)

    assert motivo is not None
    assert "bot" in motivo.lower()


def test_rifiuta_ruolo_pari_o_sopra_actor_non_owner():
    server, actor = _setup(ruolo_bot_posizione=20, ruolo_actor_posizione=5)
    ruolo = fake_role(role_id=50, name="Pari", position=5)

    motivo = check_role_assignable(server, ruolo, actor, self_service=False)

    assert motivo is not None
    assert "tuo ruolo" in motivo.lower()


def test_owner_puo_usare_ruolo_sopra_il_proprio():
    server, actor = _setup(ruolo_bot_posizione=20, ruolo_actor_posizione=5, owner_id=2)
    ruolo = fake_role(role_id=50, name="Alto", position=10)

    motivo = check_role_assignable(server, ruolo, actor, self_service=False)

    assert motivo is None


@pytest.mark.parametrize(
    "permesso",
    [
        "administrator",
        "manage_guild",
        "manage_roles",
        "manage_channels",
        "ban_members",
        "kick_members",
        "moderate_members",
        "manage_webhooks",
        "mention_everyone",
    ],
)
def test_self_service_rifiuta_ruolo_con_permesso_pericoloso(permesso):
    server, actor = _setup(ruolo_bot_posizione=20, ruolo_actor_posizione=15)
    permessi = discord.Permissions.none()
    setattr(permessi, permesso, True)
    ruolo = fake_role(role_id=50, name="Pericoloso", position=1, permissions=permessi)

    motivo = check_role_assignable(server, ruolo, actor, self_service=True)

    assert motivo is not None
    assert permesso in motivo


def test_self_service_accetta_ruolo_senza_permessi_pericolosi():
    server, actor = _setup(ruolo_bot_posizione=20, ruolo_actor_posizione=15)
    ruolo = fake_role(
        role_id=50, name="Cosmetico", position=1, permissions=discord.Permissions.none()
    )

    motivo = check_role_assignable(server, ruolo, actor, self_service=True)

    assert motivo is None


def test_non_self_service_accetta_ruolo_con_permesso_pericoloso_se_gerarchia_ok():
    """Un moderatore autorizzato può assegnare a mano un ruolo 'forte'."""
    server, actor = _setup(ruolo_bot_posizione=20, ruolo_actor_posizione=15)
    permessi = discord.Permissions.none()
    permessi.ban_members = True
    ruolo = fake_role(role_id=50, name="Forte ma manuale", position=1, permissions=permessi)

    motivo = check_role_assignable(server, ruolo, actor, self_service=False)

    assert motivo is None

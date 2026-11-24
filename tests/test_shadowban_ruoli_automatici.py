"""
tests/test_shadowban_ruoli_automatici.py
========================================
D136: a chi è in shadowban non si danno ruoli in automatico né su sua richiesta (verifica, menu a tasti, premi,
ruoli di livello, ecc.). Le azioni dello staff restano libere. Un test di struttura impedisce `add_roles` nudo
nei punti automatici. Database vero, Discord finto.
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import moderation_shadowban as sb
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_member

RADICE = Path(__file__).resolve().parent.parent
SERVER, UTENTE = 100, 20

# Punti automatici o su richiesta dell'utente: devono passare da `add_roles_se_libero`.
AUTOMATICI = [
    "cogs/ai/boss.py", "cogs/leveling/leveling.py", "cogs/leveling/inventario.py", "cogs/leveling/ruoli_classifica.py",
    "cogs/leveling/reputazione.py", "cogs/voice_temp/voice_temp.py", "cogs/utility/ruoli_vocali.py",
    "cogs/utility/backup.py", "cogs/utility/invites.py", "cogs/utility/custom_commands.py",
    "cogs/utility/activity_stats.py", "cogs/utility/ruoli_extra.py", "cogs/utility/conteggio.py",
    "cogs/tickets/tickets.py", "core/giveaway_fine.py", "core/live_role_logic.py", "core/birthday_worker.py",
    "core/guild_clan_role_service.py",
]


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)


def _membro():
    m = fake_member(UTENTE)
    m.guild = fake_guild(SERVER)
    m.add_roles = AsyncMock()
    return m


async def _metti_shadowban():
    assert await moderation_repo.prenota_shadowban(SERVER, UTENTE, [11], None, 1)


async def test_chi_e_in_shadowban_non_prende_ruoli_e_gli_altri_si():
    m = _membro()
    assert await sb.add_roles_se_libero(m, MagicMock(), reason="x") is True
    m.add_roles.assert_awaited_once()
    m.add_roles.reset_mock()
    await _metti_shadowban()
    assert await sb.add_roles_se_libero(m, MagicMock(), reason="x") is False
    m.add_roles.assert_not_awaited()


async def test_se_il_database_non_risponde_i_ruoli_passano(monkeypatch):
    monkeypatch.setattr(sb, "in_shadowban", AsyncMock(side_effect=RuntimeError("pool chiuso")))
    m = _membro()
    assert await sb.add_roles_se_libero(m, MagicMock(), reason="x") is True


async def test_la_verifica_non_si_completa_per_chi_e_in_shadowban():
    from cogs.security.verify import VerifyCog

    await _metti_shadowban()
    m = _membro()
    cog = VerifyCog(MagicMock())
    assert await cog.dai_ruoli_di_verifica(m.guild, m, 555) is False
    m.add_roles.assert_not_awaited()


async def test_il_menu_a_tasti_risponde_con_un_rifiuto_e_non_da_ruoli():
    from cogs.utility.role_menus import RoleMenuCog
    from core.role_menu_logic import Decisione

    await _metti_shadowban()
    m = _membro()
    cog = RoleMenuCog(MagicMock())
    decisione = MagicMock(spec=Decisione)
    decisione.aggiungi = [5]
    decisione.togli = []
    esito = await cog._applica(m.guild, m, decisione, "Role menu")
    assert esito and isinstance(esito, str)
    m.add_roles.assert_not_awaited()


@pytest.mark.parametrize("percorso", AUTOMATICI)
def test_nei_punti_automatici_non_resta_add_roles_nudo(percorso):
    testo = (RADICE / percorso).read_text(encoding="utf-8")
    nudi = [r for r in re.findall(r"[\w.]+\.add_roles\(", testo)]
    assert not nudi, f"{percorso}: usa add_roles diretto {nudi}; usare add_roles_se_libero (D136)"

"""
tests/test_anti_raid_117.py
===========================
Catalogo #117 e difetti trovati nell'anti-raid:
- SIC-004  il ruolo di quarantena resta senza permessi;
- SIC-003  chi e' in quarantena ci resta (blocco), si libera con `rilascia`;
- SIC-022  avviso se i ruoli non lasciano lavorare il bot;
- soglie fuori misura rifiutate; quarantena non assegnata detta nell'avviso.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.security.anti_raid as modulo
from core.repositories.security_repo import security_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.test_anti_raid_f1 import (  # noqa: F401  (fixture condivise)
    GUILD_ID,
    _azione,
    _interazione,
    _raid,
    cog,
    db_finto,
    orologio,
    server,
)
from tests.test_anti_nuke_f1 import _voce

ADMIN = discord.Permissions(administrator=True)
NIENTE = discord.Permissions.none()
QID = 7777
AUTORE = 4242


async def _con_quarantena(cog, server, *, blocco=True):
    quarantena = fake_role(role_id=QID, name="Quarantined", permissions=NIENTE)
    quarantena.edit = AsyncMock()
    server.get_role.side_effect = lambda rid: quarantena if rid == QID else None
    settings = await security_repo.get_settings(GUILD_ID)
    await security_repo.save_settings(
        modulo._replace(settings, quarantine_role_id=QID, quarantine_hold=blocco)
    )
    return quarantena


def _registro(server, autore_id, membro_id):
    voce = _voce(discord.AuditLogAction.member_role_update, autore_id, membro_id)

    def _audit_logs(**_kw):
        async def _gen():
            yield voce
        return _gen()

    server.audit_logs.side_effect = _audit_logs


def _membro(server, roles, user_id=31):
    m = fake_member(user_id=user_id, roles=roles)
    m.guild = server
    return m


# ---------------------------------------------------------------- SIC-004
async def test_permessi_dati_al_ruolo_di_quarantena_vengono_tolti(cog, server):
    quarantena = await _con_quarantena(cog, server)
    dopo = fake_role(role_id=QID, name="Quarantined", permissions=ADMIN)
    dopo.guild, dopo.edit = server, AsyncMock()
    await cog.on_guild_role_update(quarantena, dopo)
    dopo.edit.assert_awaited_once()
    assert dopo.edit.call_args.kwargs["permissions"] == NIENTE


async def test_un_altro_ruolo_o_nessun_permesso_non_si_tocca(cog, server):
    await _con_quarantena(cog, server)
    altro = fake_role(role_id=1, name="Mod", permissions=ADMIN)
    altro.guild, altro.edit = server, AsyncMock()
    await cog.on_guild_role_update(altro, altro)
    altro.edit.assert_not_awaited()
    vuoto = fake_role(role_id=QID, permissions=NIENTE)
    vuoto.guild, vuoto.edit = server, AsyncMock()
    await cog.on_guild_role_update(vuoto, vuoto)
    vuoto.edit.assert_not_awaited()


# ---------------------------------------------------------------- SIC-003
async def test_quarantena_tolta_a_mano_da_un_non_fidato_viene_rimessa(cog, server):
    quarantena = await _con_quarantena(cog, server)
    _registro(server, AUTORE, 31)
    prima, dopo = _membro(server, [quarantena]), _membro(server, [])
    await cog.on_member_update(prima, dopo)
    dopo.add_roles.assert_awaited_once()
    assert dopo.add_roles.call_args.args == (quarantena,)
    assert "raid_quarantine_hold" in [r["category"] for r in await security_repo.get_recent_actions(GUILD_ID)]


async def test_ruoli_dati_a_chi_e_in_quarantena_vengono_tolti(cog, server):
    quarantena = await _con_quarantena(cog, server)
    _registro(server, AUTORE, 31)
    mod = fake_role(role_id=9, name="Mod", permissions=NIENTE)
    prima, dopo = _membro(server, [quarantena]), _membro(server, [quarantena, mod])
    await cog.on_member_update(prima, dopo)
    dopo.remove_roles.assert_awaited_once()
    assert dopo.remove_roles.call_args.args == (mod,)


async def test_un_fidato_o_il_proprietario_puo_togliere_la_quarantena(cog, server):
    from cogs.security.anti_nuke import AntiNukeCog  # noqa: F401
    quarantena = await _con_quarantena(cog, server)
    impostazioni = await security_repo.get_settings(GUILD_ID)
    from core.security_logic import AntiNukeConfig
    from dataclasses import replace
    await security_repo.save_settings(
        replace(impostazioni, anti_nuke=AntiNukeConfig(trusted_ids=(AUTORE,)))
    )
    _registro(server, AUTORE, 31)
    prima, dopo = _membro(server, [quarantena]), _membro(server, [])
    await cog.on_member_update(prima, dopo)
    dopo.add_roles.assert_not_awaited()

    _registro(server, 1, 31)  # il proprietario del server di prova ha id 1
    await cog.on_member_update(prima, dopo)
    dopo.add_roles.assert_not_awaited()


async def test_senza_blocco_attivo_non_legge_il_registro(cog, server):
    quarantena = await _con_quarantena(cog, server, blocco=False)
    prima, dopo = _membro(server, [quarantena]), _membro(server, [])
    await cog.on_member_update(prima, dopo)
    server.audit_logs.assert_not_called()


async def test_un_ingresso_in_quarantena_fatto_dal_bot_non_legge_il_registro(cog, server):
    quarantena = await _con_quarantena(cog, server)
    prima, dopo = _membro(server, []), _membro(server, [quarantena])
    await cog.on_member_update(prima, dopo)
    server.audit_logs.assert_not_called()


async def test_rilascia_toglie_la_quarantena_e_la_registra(cog, server):
    quarantena = await _con_quarantena(cog, server)
    membro = _membro(server, [quarantena])
    interazione = _interazione()
    interazione.guild = server
    await cog.rilascia.callback(cog, interazione, membro)
    membro.remove_roles.assert_awaited_once()
    assert "raid_release" in [r["category"] for r in await security_repo.get_recent_actions(GUILD_ID)]

    libero = _membro(server, [])
    altra = _interazione()
    altra.guild = server
    await cog.rilascia.callback(cog, altra, libero)
    assert "non è in quarantena" in altra.response.send_message.call_args.args[0]
    libero.remove_roles.assert_not_awaited()


async def test_comando_blocco_si_salva(cog):
    await cog.quarantine_hold.callback(cog, _interazione(), True)
    assert (await security_repo.get_settings(GUILD_ID)).anti_raid.quarantine_hold is True


# ---------------------------------------------------------------- limiti
def test_soglie_fuori_misura_sono_rifiutate_da_discord():
    import typing

    def _limiti(comando):
        suggerimenti = typing.get_type_hints(comando.callback, include_extras=True)
        return {
            nome: (suggerimenti[nome]._min, suggerimenti[nome]._max)
            for nome in ("max_joins", "seconds") if nome in suggerimenti
        }

    assert _limiti(modulo.AntiRaidCog.join_rate) == {"max_joins": (1, 1000), "seconds": (1, 3600)}
    assert _limiti(modulo.AntiRaidCog.account_age) == {"seconds": (0, 31_536_000)}


# ---------------------------------------------------------------- SIC-022
async def test_enable_avvisa_se_il_ruolo_del_bot_non_basta(cog, server):
    interazione = _interazione()
    interazione.guild = server
    # Il bot non ha Gestisci ruoli e c'e' un ruolo admin sopra al suo.
    server.me.guild_permissions = NIENTE
    server.me.top_role = fake_role(role_id=2, name="Bot", position=3)
    server.me.roles = [server.me.top_role]
    server.roles = [fake_role(role_id=3, name="Admin", position=9, permissions=ADMIN), server.me.top_role]
    await cog.enable.callback(cog, interazione, True)
    testo = interazione.response.send_message.call_args.args[0]
    assert "Gestisci ruoli" in testo and "sopra al mio" in testo


async def test_quarantena_non_assegnata_si_dice_nell_avviso(cog, server):
    await _azione(cog, "quarantine")
    server.create_role.side_effect = discord.HTTPException(MagicMock(status=403), "no")
    server.roles = []
    canale = fake_member  # noqa: F841
    membri = await _raid(cog, server, quanti=3)
    avviso = cog._avvisi.get(GUILD_ID)
    assert any("senza quarantena" in voce for voce in avviso.recenti)

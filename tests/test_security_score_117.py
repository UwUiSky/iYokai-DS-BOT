"""
tests/test_security_score_117.py
================================
Difetti del punteggio di sicurezza e SIC-022:
- la 2FA richiesta non veniva mai riconosciuta (l'enum di discord.py non e'
  un intero): il consiglio non compariva mai, nemmeno senza 2FA;
- il proprietario (e due admin) non sono "troppi amministratori";
- se i ruoli non lasciano lavorare il bot, il punteggio lo dice;
- i consigli stanno nei limiti di un campo dell'embed (1024).
"""

from unittest.mock import AsyncMock, MagicMock

import discord

import cogs.security.security_score as modulo
from core.repositories.security_repo import security_repo
from core.security_logic import ServerSecuritySignals, compute_security_score
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

ADMIN = discord.Permissions(administrator=True)


def _segnali(**kw):
    base = dict(
        mfa_level=1, verification_level="high", admin_member_count=0, total_member_count=100,
        anti_raid_enabled=True, anti_nuke_enabled=True, automod_badwords_active=True,
    )
    base.update(kw)
    return ServerSecuritySignals(**base)


def test_tre_admin_su_cento_non_sono_troppi_ma_tre_su_dieci_si():
    assert compute_security_score(_segnali(admin_member_count=2, total_member_count=10))[0] == 100
    assert compute_security_score(_segnali(admin_member_count=3, total_member_count=10))[0] == 85


def test_i_problemi_dei_ruoli_tolgono_punti_e_diventano_consigli():
    punteggio, consigli = compute_security_score(_segnali(role_problems=("Manca Gestisci ruoli.",)))
    assert punteggio == 90
    assert "Manca Gestisci ruoli." in consigli


async def test_senza_2fa_il_consiglio_compare_con_l_enum_vero(clean_db, monkeypatch):
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(modulo, "db", MagicMock(is_module_active_for_guild=AsyncMock(return_value=True)))
    server = fake_guild(guild_id=5, owner_id=1)
    server.mfa_level = discord.MFALevel.disabled
    server.verification_level = discord.VerificationLevel.high
    server.members = [fake_member(user_id=1)]
    server.chunked = True
    segnali = await modulo._collect_signals(server)
    assert segnali.mfa_level == 0
    assert any("due fattori" in c for c in compute_security_score(segnali)[1])
    server.mfa_level = discord.MFALevel.require_2fa
    assert (await modulo._collect_signals(server)).mfa_level == 1


async def test_il_proprietario_non_conta_tra_gli_amministratori(clean_db, monkeypatch):
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(modulo, "db", MagicMock(is_module_active_for_guild=AsyncMock(return_value=True)))
    server = fake_guild(guild_id=5, owner_id=1)
    server.mfa_level = discord.MFALevel.disabled
    server.verification_level = discord.VerificationLevel.high
    server.chunked = True
    server.members = [
        fake_member(user_id=1, guild_permissions=ADMIN),
        fake_member(user_id=2, guild_permissions=ADMIN),
        fake_member(user_id=3),
    ]
    segnali = await modulo._collect_signals(server)
    assert (segnali.admin_member_count, segnali.total_member_count) == (1, 3)


async def test_server_non_scaricato_viene_scaricato_prima_di_contare(clean_db, monkeypatch):
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(modulo, "db", MagicMock(is_module_active_for_guild=AsyncMock(return_value=True)))
    server = fake_guild(guild_id=5, owner_id=1)
    server.mfa_level = discord.MFALevel.require_2fa
    server.verification_level = discord.VerificationLevel.high
    server.chunked = False
    server.members = []
    server.chunk = AsyncMock()
    await modulo._collect_signals(server)
    server.chunk.assert_awaited_once()


def test_i_consigli_lunghi_si_dividono_in_campi_da_1024():
    consigli = tuple(f"Consiglio numero {n}: " + "x" * 200 for n in range(10))
    embed = modulo._build_embed(10, consigli)
    assert len(embed.fields) >= 2
    assert all(len(campo.value) <= 1024 for campo in embed.fields)
    assert sum(len(c.value) for c in embed.fields) >= 10 * 200

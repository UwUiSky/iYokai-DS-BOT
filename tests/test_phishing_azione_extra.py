"""
tests/test_phishing_azione_extra.py
===================================
SIC-041 (#117): azione in più sul filtro phishing (timeout, kick o ban), spenta di base.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import phishing_azione_logic as pal
from core.automod_advanced_logic import AutomodAdvancedConfig
from core.automod_azioni import Bersaglio, esegui_azioni


def test_SIC_041_spenta_di_base():
    # SIC-041
    assert AutomodAdvancedConfig().phishing_azione_extra == ""
    assert pal.azione_extra("", 600) is None
    assert pal.azione_extra("inventata", 600) is None


def test_SIC_041_azioni_ammesse():
    # SIC-041
    assert pal.azione_extra("timeout", 600).t == "timeout"
    assert pal.azione_extra("timeout", 600).get("secondi") == 600
    assert pal.azione_extra("kick", 600).t == "kick"
    assert pal.azione_extra("ban", 600).t == "ban"


def test_SIC_041_il_timeout_resta_nei_limiti_di_discord():
    # SIC-041
    assert pal.azione_extra("timeout", 99999999).get("secondi") <= 28 * 86400


def test_SIC_041_motivo_al_massimo_512():
    # SIC-041
    m = pal.motivo_extra("x" * 2000)
    assert len(m) <= 512 and "phishing" in pal.motivo_extra("a").lower()


def test_SIC_041_non_duplica_se_la_regola_ha_gia_una_sanzione_uguale():
    # SIC-041
    base = (pal.azione_extra("timeout", 60),)
    assert pal.aggiungi_extra(base, "timeout", 600) == base
    assert len(pal.aggiungi_extra(base, "ban", 600)) == 2
    assert pal.aggiungi_extra(base, "", 600) == base


def test_SIC_041_salva_e_rilegge_dal_json():
    # SIC-041
    from core.repositories.automod_advanced_repo import AutomodAdvancedSettings, _from_json, _to_json

    s = AutomodAdvancedSettings(
        guild_id=1, config=AutomodAdvancedConfig(phishing_azione_extra="kick"), exempt_channel_ids=(),
        exempt_role_ids=(), actions={}, mute_duration_seconds=600, log_channel_id=None,
    )
    assert _from_json(1, _to_json(s)).config.phishing_azione_extra == "kick"
    assert _from_json(1, "{}").config.phishing_azione_extra == ""  # spenta se manca


def _membro(*, admin=False, proprietario=False, top=1):
    m = MagicMock(spec=discord.Member)
    m.id = 5
    m.guild = MagicMock()
    m.guild.owner_id = 99 if not proprietario else 5
    m.guild.me.top_role.position = 10
    m.top_role.position = top
    m.guild_permissions = discord.Permissions(administrator=admin)
    return m


@pytest.mark.asyncio
async def test_SIC_041_mai_su_staff_proprietario_o_chi_sta_sopra_il_bot(monkeypatch):
    # SIC-041: lo scudo del motore unico vale anche per l'azione in più
    import core.automod_azioni as az

    chiamate = AsyncMock(return_value=True)
    monkeypatch.setitem(az._FUNZIONI, "ban", chiamate)
    for membro in (_membro(admin=True), _membro(proprietario=True), _membro(top=10)):
        b = Bersaglio(guild=membro.guild, motivo="x", regola_chiave="anti_phishing", regola_nome="x", membro=membro)
        assert await esegui_azioni((pal.azione_extra("ban", 60),), b) == ()
    chiamate.assert_not_awaited()
    semplice = _membro()
    b = Bersaglio(guild=semplice.guild, motivo="x", regola_chiave="anti_phishing", regola_nome="x", membro=semplice)
    assert await esegui_azioni((pal.azione_extra("ban", 60),), b) == ("ban",)


@pytest.mark.asyncio
async def test_SIC_041_il_caso_va_nel_log_di_moderazione_con_il_motivo(monkeypatch):
    # SIC-041
    import cogs.automod.automod as am
    import cogs.moderation._shared as sh
    from core.repositories.moderation_repo import moderation_repo

    crea = AsyncMock(return_value=7)
    log = AsyncMock()
    monkeypatch.setattr(moderation_repo, "create_case", crea)
    monkeypatch.setattr(sh, "post_to_mod_log", log)
    msg = MagicMock()
    msg.guild.id = 1
    msg.author.id = 5
    await am._registra_caso_extra(msg, "ban", 600)
    kw = crea.await_args.kwargs
    assert kw["action_type"] == "ban" and kw["origine"] == "automod" and "phishing" in kw["reason"] and len(kw["reason"]) <= 512
    log.assert_awaited_once()

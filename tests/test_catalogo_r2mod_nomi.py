"""
tests/test_catalogo_r2mod_nomi.py
=================================
Storico dei nomi (MOD-103) e soprannome / mute vocale ridati a chi rientra (MOD-104). Spenti di base. Database vero.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.nickname import ModerationNicknameCog
from cogs.moderation.opzioni import OpzioniModerazioneCog
from core import moderation_nomi as nomi
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.test_moderation_ordine_azione import ID_SERVER

G, U = ID_SERVER, 4242


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()


def _cog(guild=None):
    bot = MagicMock()
    bot.guilds = [guild] if guild else []
    return ModerationNicknameCog(bot=bot)


def _membro(guild, nick=None, bot=False):
    m = fake_member(U, bot=bot)
    m.guild, m.nick = guild, nick
    m.top_role = fake_role(2, position=5)
    return m


# MOD-103
async def test_spento_di_base_non_si_registra_niente_e_acceso_si():
    guild = fake_guild(G)
    cog = _cog(guild)
    prima, dopo = _membro(guild, "vecchio"), _membro(guild, "nuovo")
    await cog.on_member_update(prima, dopo)
    assert await moderation_repo.elenco_nomi(G, U) == []
    await db.set_guild_setting(G, nomi.SETTING_STORICO_NOMI, True)
    await cog.on_member_update(prima, dopo)
    await cog.on_member_update(dopo, dopo)  # nessun cambio
    await cog.on_member_update(_membro(guild, "a", bot=True), _membro(guild, "b", bot=True))
    voci = await moderation_repo.elenco_nomi(G, U)
    assert [(v["tipo"], v["prima"], v["dopo"]) for v in voci] == [("soprannome", "vecchio", "nuovo")]


# MOD-103
async def test_i_cambi_di_nome_utente_entrano_nei_server_in_comune_che_lo_hanno_acceso():
    uno, due = fake_guild(G), fake_guild(G + 1)
    uno.get_member = lambda uid: object()
    due.get_member = lambda uid: object()
    bot = MagicMock()
    bot.guilds = [uno, due]
    cog = ModerationNicknameCog(bot=bot)
    await db.set_guild_setting(G, nomi.SETTING_STORICO_NOMI, True)
    prima = MagicMock(bot=False, name="x")
    prima.name, prima.global_name = "vecchio", "Vecchio"
    dopo = MagicMock(bot=False)
    dopo.id, dopo.name, dopo.global_name = U, "nuovo", "Vecchio"
    prima.bot = False
    await cog.on_user_update(prima, dopo)
    assert [(v["tipo"], v["dopo"]) for v in await moderation_repo.elenco_nomi(G, U)] == [("nome", "nuovo")]
    assert await moderation_repo.elenco_nomi(G + 1, U) == []


# MOD-103
async def test_per_persona_se_ne_tengono_solo_le_ultime_e_i_testi_lunghi_si_tagliano():
    for i in range(35):
        await moderation_repo.registra_nome(G, U, "soprannome", f"n{i}", "x" * 300)
    voci = await moderation_repo.elenco_nomi(G, U, 100)
    assert len(voci) == 30 and voci[0]["prima"] == "n34" and len(voci[0]["dopo"]) == 100


# MOD-103
def test_le_righe_non_pingano_e_non_rompono_il_markdown():
    r = nomi.riga({"tipo": "nome", "prima": "@everyone", "dopo": "**x**", "quando": datetime.now(timezone.utc)})
    assert "@everyone" not in r.replace("@​everyone", "") and "\\*\\*x\\*\\*" in r


# MOD-103
async def test_il_comando_mostra_lo_storico_solo_se_acceso():
    guild = fake_guild(G)
    cog = _cog(guild)
    i = fake_interaction(guild=guild, user=fake_member(10))
    await cog.nomi_cmd.callback(cog, i, fake_member(U))
    assert "spento" in i.response.send_message.await_args.args[0]
    await db.set_guild_setting(G, nomi.SETTING_STORICO_NOMI, True)
    await moderation_repo.registra_nome(G, U, "soprannome", "a", "b")
    i = fake_interaction(guild=guild, user=fake_member(10))
    await cog.nomi_cmd.callback(cog, i, fake_member(U))
    kw = i.response.send_message.await_args.kwargs
    assert "a → b" in kw["embed"].description and kw["ephemeral"] is True and kw["allowed_mentions"].users is False


# MOD-104
async def test_chi_esce_e_rientra_riprende_il_soprannome_se_acceso():
    guild = fake_guild(G)
    guild.me.guild_permissions = discord.Permissions(manage_nicknames=True)
    guild.me.top_role = fake_role(3, position=50)
    cog = _cog(guild)
    esce = _membro(guild, "Volpe")
    esce.voice = None
    await cog.on_member_remove(esce)
    assert await moderation_repo.leggi_persistenza(G, U) is None  # spento di base
    await db.set_guild_setting(G, nomi.SETTING_PERSISTENZA, True)
    await cog.on_member_remove(esce)
    rientra = _membro(guild, None)
    rientra.edit = AsyncMock()
    await cog.on_member_join(rientra)
    assert rientra.edit.await_args.kwargs["nick"] == "Volpe"
    assert await moderation_repo.leggi_persistenza(G, U) is None  # usato: si cancella


# MOD-104
async def test_il_soprannome_non_si_ridà_se_il_membro_sta_sopra_il_bot_o_manca_il_permesso():
    guild = fake_guild(G)
    guild.me.top_role = fake_role(3, position=50)
    cog = _cog(guild)
    await db.set_guild_setting(G, nomi.SETTING_PERSISTENZA, True)
    await moderation_repo.salva_persistenza(G, U, "Volpe", False, False)
    sopra = _membro(guild)
    sopra.top_role = fake_role(4, position=90)
    sopra.edit = AsyncMock()
    guild.me.guild_permissions = discord.Permissions(manage_nicknames=True)
    await cog.on_member_join(sopra)
    sopra.edit.assert_not_awaited()
    await moderation_repo.salva_persistenza(G, U, "Volpe", False, False)
    senza = _membro(guild)
    senza.edit = AsyncMock()
    guild.me.guild_permissions = discord.Permissions.none()
    await cog.on_member_join(senza)
    senza.edit.assert_not_awaited()
    assert nomi.nick_da_ridare("x" * 40, False) is None and nomi.nick_da_ridare("", False) is None


# MOD-104
async def test_il_mute_vocale_si_ridà_alla_prossima_entrata_in_vocale_e_una_volta_sola():
    guild = fake_guild(G)
    guild.me.guild_permissions = discord.Permissions(mute_members=True, deafen_members=True)
    cog = _cog(guild)
    await db.set_guild_setting(G, nomi.SETTING_PERSISTENZA, True)
    await moderation_repo.salva_persistenza(G, U, None, True, False)
    m = _membro(guild)
    m.edit = AsyncMock()
    fuori, dentro = MagicMock(channel=None), MagicMock(channel=object())
    await cog.on_voice_state_update(m, dentro, dentro)  # era già in vocale: niente
    m.edit.assert_not_awaited()
    await cog.on_voice_state_update(m, fuori, dentro)
    assert m.edit.await_args.kwargs["mute"] is True and "deafen" not in m.edit.await_args.kwargs
    assert await moderation_repo.leggi_persistenza(G, U) is None
    await cog.on_voice_state_update(m, fuori, dentro)
    assert m.edit.await_count == 1


# MOD-103, MOD-104
async def test_il_comando_delle_opzioni_accende_e_spegne_e_serve_gestire_il_server():
    guild = fake_guild(G, owner_id=1)
    cog = OpzioniModerazioneCog(bot=None)
    senza = fake_interaction(guild=guild, user=fake_member(20, guild_permissions=discord.Permissions.none()))
    await cog.memoria.callback(cog, senza, True, True)
    assert not await db.get_guild_setting(G, nomi.SETTING_STORICO_NOMI)
    ok = fake_interaction(guild=guild, user=fake_member(21, guild_permissions=discord.Permissions(manage_guild=True)))
    await cog.memoria.callback(cog, ok, True, None)
    assert await db.get_guild_setting(G, nomi.SETTING_STORICO_NOMI) is True and not await db.get_guild_setting(G, nomi.SETTING_PERSISTENZA)
    ok2 = fake_interaction(guild=guild, user=fake_member(21, guild_permissions=discord.Permissions(manage_guild=True)))
    await cog.memoria.callback(cog, ok2, False, True)
    assert await db.get_guild_setting(G, nomi.SETTING_STORICO_NOMI) is False and await db.get_guild_setting(G, nomi.SETTING_PERSISTENZA) is True

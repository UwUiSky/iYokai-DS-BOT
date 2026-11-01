"""
tests/test_escalation_warn_manuali.py
=====================================
M 1.10 (#57): i warn dati a mano con /mod warn salgono la scala di
escalation, se il server l'ha scelto. Spento di base. Database vero.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.automod.escalation as modulo_escalation
from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.actions import ModerationActionsCog
from core.database import db
from core.repositories.escalation_repo import escalation_repo
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

SERVER = 100
MOD = 444444444444444444
A = 111111111111111111


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(SERVER, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()


def _scena(permessi=None):
    server = fake_guild(SERVER, owner_id=1)
    server.me.top_role = fake_role(role_id=3, position=50)
    server.me.id = 999
    server.get_channel.return_value = None
    moderatore = fake_member(
        MOD, roles=[fake_role(role_id=1, position=40)], guild_permissions=permessi or discord.Permissions.all()
    )
    moderatore.guild = server
    membro = fake_member(A, roles=[fake_role(role_id=2, position=5)])
    membro.guild = server
    server.get_member.side_effect = {MOD: moderatore, A: membro}.get
    return membro, fake_interaction(guild=server, user=moderatore)


def _cog():
    bot = MagicMock()
    bot.user = fake_member(999, bot=True)
    return ModerationActionsCog(bot=bot)


async def _warn(cog, membro, interazione):
    await cog.warn.callback(cog, interazione, membro, "linguaggio")


async def _tipi(uid):
    return sorted(c.action_type for c in await moderation_repo.list_cases_for_user(SERVER, uid))


async def test_di_base_i_warn_manuali_non_contano(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await escalation_repo.set_enabled(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()
    for _ in range(3):
        await _warn(cog, membro, interazione)

    isola.assert_not_awaited()
    assert await _tipi(A) == ["warn"] * 3


async def test_tre_warn_manuali_fanno_scattare_il_gradino(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()

    # Scala di base: 1 warn (nessun warn in più), 2 timeout 10 min, 3 timeout 1 ora.
    await _warn(cog, membro, interazione)
    isola.assert_not_awaited()
    interazione.followup.send.assert_not_awaited()
    assert await _tipi(A) == ["warn"]

    await _warn(cog, membro, interazione)
    await _warn(cog, membro, interazione)

    assert isola.await_count == 2
    assert isola.await_args.args[1].total_seconds() == 3600
    assert "infrazione #3" in interazione.followup.send.await_args.args[0]
    assert await _tipi(A) == ["automod_escalation"] * 2 + ["warn"] * 3


async def test_ogni_gradino_applicato_lascia_una_riga_nel_log_di_moderazione(monkeypatch):
    """§18.7: la scala scrive nel log di moderazione; un log che si rompe non ferma la scala."""
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", AsyncMock())
    log = AsyncMock()
    monkeypatch.setattr(modulo_escalation, "post_to_mod_log", log)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()
    for _ in range(2):
        await _warn(cog, membro, interazione)

    log.assert_awaited_once()
    embed = log.await_args.args[1]
    assert embed.title == "⚖️ Scala di escalation"
    assert {c.name for c in embed.fields} >= {"Utente", "Azione", "Caso", "Motivo"}

    log.side_effect = RuntimeError("log rotto")
    await _warn(cog, membro, interazione)
    assert "La scala ha applicato" in interazione.followup.send.await_args.args[0]


async def test_azione_fallita_lo_dice_e_non_apre_casi(monkeypatch):
    import discord

    isola = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "no"))
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()
    await _warn(cog, membro, interazione)
    await _warn(cog, membro, interazione)

    assert "non ci sono riuscito" in interazione.followup.send.await_args.args[0]
    assert await _tipi(A) == ["warn"] * 2


async def test_il_comando_enable_accende_e_tiene_la_scelta():
    from cogs.automod.escalation import EscalationCog

    cog = EscalationCog(MagicMock())
    server = fake_guild(SERVER, owner_id=1)
    await cog.enable.callback(cog, fake_interaction(guild=server), True)
    assert (await escalation_repo.get_config(SERVER)).conta_warn_manuali

    interazione = fake_interaction(guild=server)
    await cog.enable.callback(cog, interazione)
    assert (await escalation_repo.get_config(SERVER)).conta_warn_manuali
    assert "contano." in interazione.response.send_message.call_args.args[0]


async def _scala_attiva(gradini=None):
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    if gradini:
        for livello, (azione, durata) in enumerate(gradini, start=1):
            await escalation_repo.set_step(SERVER, livello, azione, durata)


async def test_il_gradino_di_timeout_non_accorcia_un_timeout_piu_lungo(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await _scala_attiva()
    cog = _cog()
    membro, interazione = _scena()
    membro.timed_out_until = discord.utils.utcnow() + timedelta(days=7)
    await _warn(cog, membro, interazione)
    await _warn(cog, membro, interazione)  # gradino 2: timeout 10 minuti

    isola.assert_not_awaited()
    assert "timeout più lungo" in interazione.followup.send.await_args.args[0]
    assert await _tipi(A) == ["warn"] * 2


async def test_il_gradino_di_timeout_allunga_un_timeout_piu_corto(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await _scala_attiva()
    cog = _cog()
    membro, interazione = _scena()
    membro.timed_out_until = discord.utils.utcnow() + timedelta(minutes=1)
    await _warn(cog, membro, interazione)
    await _warn(cog, membro, interazione)
    isola.assert_awaited_once()


async def test_automod_non_accorcia_un_timeout_piu_lungo(monkeypatch):
    from cogs.automod.escalation import EscalationCog
    from cogs.automod.automod import MODULE_AUTOMOD

    isola = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await db.set_module_active_for_guild(SERVER, MODULE_AUTOMOD, True)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_step(SERVER, 1, "timeout", 600)
    membro, _ = _scena()
    membro.timed_out_until = discord.utils.utcnow() + timedelta(days=7)
    evento = MagicMock(guild_id=SERVER, user_id=A, rule_id=1, message_id=2, content="x", member=membro)
    cog = EscalationCog(MagicMock())
    await cog.on_automod_action(evento)

    isola.assert_not_awaited()
    assert await _tipi(A) == []


async def test_il_gradino_parte_solo_se_il_moderatore_potrebbe_farlo(monkeypatch):
    espelli = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "espelli", espelli)
    await _scala_attiva([("warn", None), ("kick", None)])
    cog = _cog()
    # Può dare warn e timeout, non espellere.
    membro, interazione = _scena(discord.Permissions(moderate_members=True))
    await _warn(cog, membro, interazione)
    await _warn(cog, membro, interazione)

    espelli.assert_not_awaited()
    assert "non hai il permesso" in interazione.followup.send.await_args.args[0]
    assert await _tipi(A) == ["warn"] * 2


async def test_il_gradino_rispetta_la_gerarchia_del_moderatore(monkeypatch):
    espelli = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "espelli", espelli)
    await _scala_attiva([("kick", None)])
    membro, interazione = _scena()
    # Il bersaglio sale sopra il moderatore dopo il warn: la scala non lo espelle.
    membro.top_role = fake_role(role_id=9, position=45)
    esito = await modulo_escalation.scala_per_warn_manuale(
        _cog().bot, membro, 1, moderatore=interazione.user
    )
    espelli.assert_not_awaited()
    assert "non l'ho applicato" in esito


async def test_warn_in_massa_non_espelle_ne_banna(monkeypatch):
    espelli, banna = AsyncMock(), AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "espelli", espelli)
    monkeypatch.setattr(modulo_escalation.bot_roles, "banna", banna)
    await _scala_attiva([("ban", None)])
    cog = _cog()
    membro, interazione = _scena()
    monkeypatch.setattr(cog, "_prepara_massa", AsyncMock(return_value=[A]))
    monkeypatch.setattr(cog, "_cerca_membro", AsyncMock(return_value=(membro, None)))
    monkeypatch.setattr(cog, "_chiudi_massa", AsyncMock())
    await cog.warn_massa.callback(cog, interazione, str(A), "linguaggio")

    banna.assert_not_awaited()
    espelli.assert_not_awaited()
    fatti = cog._chiudi_massa.await_args.args[4]
    assert "dai warn in massa kick e ban non partono" in fatti[0]
    assert await _tipi(A) == ["warn"]

"""
tests/test_moderation_tempban_modi.py
=====================================
Ban temporaneo con rientro e ban in isolamento (issue #138, SPEC 5.11/5.12).
Logica dei ruoli, stato su database vero e comandi con i finti fedeli di Discord.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.scheduler as modulo_scheduler
from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.actions import ModerationActionsCog
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from core.tempban_logic import (
    MODO_FUORI,
    MODO_ISOLAMENTO,
    MODO_RIENTRO,
    RuoloInfo,
    ruoli_da_ridare,
    ruoli_da_salvare,
    ruoli_da_tenere_in_isolamento,
)
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)

ID_SERVER = 100
ID_BERSAGLIO = 20


# ---------------------------- logica pura ----------------------------

def test_ruoli_da_salvare_salta_everyone_e_gestiti():
    ruoli = [
        RuoloInfo(100, 0, is_default=True),
        RuoloInfo(1, 5),
        RuoloInfo(2, 6, managed=True),
    ]
    assert ruoli_da_salvare(ruoli) == [1]


def test_ruoli_da_ridare_solo_sotto_il_bot_esistenti_e_non_gestiti():
    server = [
        RuoloInfo(1, 5),
        RuoloInfo(2, 60),  # sopra il bot
        RuoloInfo(3, 5, managed=True),
        RuoloInfo(4, 4),
    ]
    # 9 non esiste più
    assert ruoli_da_ridare([1, 2, 3, 4, 9], server, posizione_bot=50) == [1, 4]


def test_ruoli_da_tenere_in_isolamento():
    ruoli = [RuoloInfo(1, 5), RuoloInfo(2, 5, managed=True), RuoloInfo(3, 70), RuoloInfo(100, 0, is_default=True)]
    assert ruoli_da_tenere_in_isolamento(ruoli, posizione_bot=50) == [2, 3]


# ------------------------------ ambiente ------------------------------

@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()


async def test_stato_salvato_letto_e_cancellato():
    fine = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    await moderation_repo.save_tempban_state(ID_SERVER, ID_BERSAGLIO, MODO_RIENTRO, [1, 2], fine, "abc", 7)
    stato = await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO)
    assert stato["ruoli"] == [1, 2] and stato["invito_codice"] == "abc" and not stato["scaduto"]
    await moderation_repo.mark_tempban_state_expired(ID_SERVER, ID_BERSAGLIO)
    assert (await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO))["scaduto"]
    await moderation_repo.delete_tempban_state(ID_SERVER, ID_BERSAGLIO)
    assert await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO) is None


class Scena:
    def __init__(self) -> None:
        self.chiamate: list[str] = []
        self.server = fake_guild(ID_SERVER, owner_id=1)
        self.server.me.top_role = fake_role(role_id=3, position=50)
        self.server.me.id = 999
        self.canale_invito = fake_text_channel(5001, "regole")
        self.server.system_channel = self.canale_invito
        self.invito = MagicMock(spec=discord.Invite)
        self.invito.url = "https://discord.gg/xyz"
        self.invito.code = "xyz"
        self.invito.delete = AsyncMock()
        self.canale_invito.create_invite = AsyncMock(side_effect=self._crea_invito)
        self.server.text_channels = [self.canale_invito]
        self.server.channels = [self.canale_invito]
        self.server.get_channel.return_value = None
        self.server.roles = []

        self.ruolo_a = fake_role(role_id=11, name="A", position=5)
        self.ruolo_alto = fake_role(role_id=12, name="Alto", position=70)
        self.ruolo_gestito = fake_role(role_id=13, name="Bot", position=6, managed=True)
        self.everyone = fake_role(role_id=ID_SERVER, name="@everyone", position=0)
        self.everyone.is_default = MagicMock(return_value=True)
        self.server.roles = [self.everyone, self.ruolo_a, self.ruolo_alto, self.ruolo_gestito]
        self.server.get_role = MagicMock(side_effect=lambda i: next((r for r in self.server.roles if r.id == i), None))
        self.server.default_role = self.everyone

        self.moderatore = fake_member(10, roles=[fake_role(role_id=1, position=40)])
        self.moderatore.guild = self.server
        self.bersaglio = fake_member(
            ID_BERSAGLIO, roles=[self.everyone, self.ruolo_a, self.ruolo_alto, self.ruolo_gestito]
        )
        self.bersaglio.guild = self.server
        self.server.get_member.return_value = self.moderatore
        self.interazione = fake_interaction(guild=self.server, user=self.moderatore)

        self.messaggio_dm = MagicMock(spec=discord.Message)
        self.messaggio_dm.delete = AsyncMock(side_effect=lambda: self.chiamate.append("dm_cancellato"))
        self._annota(self.bersaglio.send, "dm", self.messaggio_dm)
        self._annota(self.bersaglio.ban, "ban")
        self._annota(self.bersaglio.edit, "edit")

    async def _crea_invito(self, **kwargs):
        self.chiamate.append("invito")
        self.kwargs_invito = kwargs
        return self.invito

    def _annota(self, finto, nome, ritorno=None):
        async def _f(*a, **k):
            self.chiamate.append(nome)
            return ritorno

        finto.side_effect = _f


async def _tempban(scena, modo):
    cog = ModerationActionsCog(bot=None)
    await cog.tempban.callback(cog, scena.interazione, scena.bersaglio, "7d", "Spam ripetuto", modo)
    return cog


async def test_rientro_invito_e_dm_prima_del_ban_e_ruoli_salvati(monkeypatch):
    pianificate = []

    async def _pianifica(**kw):
        pianificate.append(kw)

    monkeypatch.setattr(modulo_scheduler.scheduler, "schedule", _pianifica)
    scena = Scena()

    await _tempban(scena, MODO_RIENTRO)

    assert scena.chiamate == ["invito", "dm", "ban"]
    # L'invito vale oltre la scadenza: non scade e si usa una volta.
    assert scena.kwargs_invito["max_age"] == 0 and scena.kwargs_invito["max_uses"] == 1
    embed = scena.bersaglio.send.call_args.kwargs["embed"]
    testo = " ".join(f.value for f in embed.fields) + (embed.description or "")
    assert "https://discord.gg/xyz" in testo and "<t:" in testo
    stato = await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO)
    assert stato["modo"] == MODO_RIENTRO and stato["ruoli"] == [11, 12]
    assert pianificate[0]["payload"]["modo"] == MODO_RIENTRO


async def test_rientro_ban_fallito_cancella_dm_invito_e_stato(monkeypatch):
    scena = Scena()

    async def _fallisce(*a, **k):
        raise discord.HTTPException(MagicMock(status=400, reason="x"), "x")

    scena.bersaglio.ban.side_effect = _fallisce
    await _tempban(scena, MODO_RIENTRO)

    assert "dm_cancellato" in scena.chiamate
    scena.invito.delete.assert_awaited()
    assert await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO) is None
    assert await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO) == []


async def test_modo_fuori_non_crea_invito_ne_stato():
    scena = Scena()
    await _tempban(scena, MODO_FUORI)
    assert scena.chiamate == ["dm", "ban"]
    assert await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO) is None


async def test_scadenza_rientro_sbanna_e_al_rientro_ridona_i_ruoli():
    scena = Scena()
    cog = await _tempban(scena, MODO_RIENTRO)
    caso = (await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO))[0]
    cog.bot = MagicMock()
    cog.bot.get_guild.return_value = scena.server
    cog.bot.user.id = 999
    scena.server.unban = AsyncMock()

    await cog.handle_tempban_expire(
        ID_SERVER, ID_BERSAGLIO, {"case_number": caso.case_number, "modo": MODO_RIENTRO}
    )

    scena.server.unban.assert_awaited()
    assert (await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO))["scaduto"]

    # Il utente rientra: riprende i ruoli sotto il bot (11), non quello alto (12).
    nuovo = fake_member(ID_BERSAGLIO, roles=[scena.everyone])
    nuovo.guild = scena.server
    nuovo.add_roles = AsyncMock()
    await cog.on_member_join(nuovo)
    ridati = nuovo.add_roles.call_args.args
    assert [r.id for r in ridati] == [11]
    assert await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO) is None


async def test_rientro_non_ancora_scaduto_non_ridona_ruoli():
    scena = Scena()
    cog = await _tempban(scena, MODO_RIENTRO)
    nuovo = fake_member(ID_BERSAGLIO, roles=[scena.everyone])
    nuovo.guild = scena.server
    nuovo.add_roles = AsyncMock()
    await cog.on_member_join(nuovo)
    nuovo.add_roles.assert_not_awaited()


def _prepara_isolamento(scena):
    """Server finto che sa creare ruolo e canale di isolamento."""
    ruolo_iso = fake_role(role_id=900, name="Isolamento", position=2)
    canale_iso = fake_text_channel(901, "isolamento")
    canale_iso.send = AsyncMock()
    scena.server.create_role = AsyncMock(return_value=ruolo_iso)
    scena.server.create_text_channel = AsyncMock(return_value=canale_iso)
    for canale in scena.server.channels:
        canale.set_permissions = AsyncMock()
        canale.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
    canale_iso.set_permissions = AsyncMock()
    return ruolo_iso, canale_iso


async def test_isolamento_non_banna_toglie_i_ruoli_e_avvisa_nel_canale(monkeypatch):
    pianificate = []

    async def _pianifica(**kw):
        pianificate.append(kw)

    monkeypatch.setattr(modulo_scheduler.scheduler, "schedule", _pianifica)
    scena = Scena()
    ruolo_iso, canale_iso = _prepara_isolamento(scena)

    await _tempban(scena, MODO_ISOLAMENTO)

    assert "ban" not in scena.chiamate
    # Un'unica modifica dei ruoli: restano gestito e alto (non rimovibili) + isolamento.
    ruoli_finali = scena.bersaglio.edit.call_args.kwargs["roles"]
    assert {r.id for r in ruoli_finali} == {12, 13, 900}
    # Il ruolo non vede nessun canale tranne quello di isolamento.
    scena.canale_invito.set_permissions.assert_awaited()
    sovrascrittura = scena.canale_invito.set_permissions.call_args.kwargs["overwrite"]
    assert sovrascrittura.view_channel is False
    canale_iso.send.assert_awaited()
    assert "<t:" in canale_iso.send.call_args.args[0] or "<t:" in str(canale_iso.send.call_args)
    stato = await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO)
    assert stato["modo"] == MODO_ISOLAMENTO and stato["ruoli"] == [11]
    caso = (await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO))[0]
    assert caso.action_type == "isolamento"
    assert pianificate[0]["payload"]["modo"] == MODO_ISOLAMENTO


async def test_scadenza_isolamento_ridona_i_ruoli_e_toglie_il_ruolo():
    scena = Scena()
    ruolo_iso, _ = _prepara_isolamento(scena)
    cog = await _tempban(scena, MODO_ISOLAMENTO)
    caso = (await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO))[0]
    cog.bot = MagicMock()
    cog.bot.get_guild.return_value = scena.server
    cog.bot.user.id = 999
    scena.server.get_member.return_value = scena.bersaglio
    scena.bersaglio.roles = [scena.everyone, scena.ruolo_alto, scena.ruolo_gestito, ruolo_iso]
    scena.server.get_role = MagicMock(side_effect=lambda i: ruolo_iso if i == 900 else next((r for r in scena.server.roles if r.id == i), None))
    scena.bersaglio.remove_roles = AsyncMock()
    scena.bersaglio.add_roles = AsyncMock()

    await cog.handle_tempban_expire(
        ID_SERVER, ID_BERSAGLIO, {"case_number": caso.case_number, "modo": MODO_ISOLAMENTO}
    )

    scena.bersaglio.remove_roles.assert_awaited()
    assert [r.id for r in scena.bersaglio.add_roles.call_args.args] == [11]
    assert await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO) is None


async def test_canale_nuovo_riceve_il_divieto_dell_isolamento():
    scena = Scena()
    ruolo_iso, _ = _prepara_isolamento(scena)
    cog = await _tempban(scena, MODO_ISOLAMENTO)
    cog.bot = MagicMock()
    nuovo = fake_text_channel(777, "nuovo")
    nuovo.guild = scena.server
    nuovo.set_permissions = AsyncMock()
    nuovo.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
    scena.server.get_role = MagicMock(side_effect=lambda i: ruolo_iso if i == 900 else None)

    await cog.on_guild_channel_create(nuovo)

    nuovo.set_permissions.assert_awaited()


async def test_unban_libera_chi_e_in_isolamento_senza_sbannare():
    scena = Scena()
    ruolo_iso, _ = _prepara_isolamento(scena)
    cog = await _tempban(scena, MODO_ISOLAMENTO)
    scena.server.get_member.return_value = scena.bersaglio
    scena.bersaglio.roles = [scena.everyone, ruolo_iso]
    scena.server.get_role = MagicMock(side_effect=lambda i: ruolo_iso if i == 900 else next((r for r in scena.server.roles if r.id == i), None))
    scena.bersaglio.remove_roles = AsyncMock()
    scena.bersaglio.add_roles = AsyncMock()
    scena.server.unban = AsyncMock()

    await cog.unban.callback(cog, scena.interazione, str(ID_BERSAGLIO), "Basta così")

    scena.server.unban.assert_not_awaited()
    scena.bersaglio.remove_roles.assert_awaited()
    caso = (await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO))[0]
    assert caso.active is False
    assert await moderation_repo.get_tempban_state(ID_SERVER, ID_BERSAGLIO) is None

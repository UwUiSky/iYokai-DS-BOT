"""
tests/test_restore_consenso.py
==============================
M 12.12 e 12.14 (#68): a fine verifica la proposta di consenso; il restore
manda DM solo a chi ha accettato (o ha già dato il consenso OAuth).
Funzioni coperte: SPEC §11.12, M 12.12, M 12.14
"""

from __future__ import annotations

import dataclasses

import pytest

import cogs.utility.restore as restore_module
from cogs.security.verify import proponi_consenso_restore
from cogs.utility.restore import (
    BottoneConsensoRestore,
    ConsensoRestoreView,
    RestoreCog,
    proposta_consenso_restore,
)
from tests.test_restore_cog_behavior import (  # noqa: F401  (fixture database)
    CHIAVE_TEST,
    _FakeBot,
    _FakeInteraction,
    _FakeUser,
    _patch_repos,
    database,
)


@pytest.fixture
async def ambiente(database, monkeypatch):
    snap, oauth, _v, backup = _patch_repos(monkeypatch, database)
    monkeypatch.setattr(restore_module, "db", database)
    monkeypatch.setattr(
        restore_module, "config",
        dataclasses.replace(restore_module.config, OAUTH_ENCRYPTION_KEY=CHIAVE_TEST),
    )

    async def niente(_s):
        return None

    monkeypatch.setattr(restore_module, "_pausa", niente)
    return database, snap, oauth, backup


async def test_nessuna_proposta_senza_backup(ambiente):
    assert await proposta_consenso_restore(100, 1) is None


async def test_proposta_con_backup_e_bottoni(ambiente):
    _db, _s, oauth, backup = ambiente
    await backup.define_main(100)
    testo, view = await proposta_consenso_restore(100, 1)
    assert "DM" in testo and "oauth2/authorize" not in testo
    assert isinstance(view, ConsensoRestoreView)
    await oauth.salva_consenso(100, 1)
    assert await proposta_consenso_restore(100, 1) is None


async def test_modalita_oauth_alla_verifica_mostra_il_link(ambiente):
    """M 12.14: anche senza coppia, la modalità «OAuth alla verifica» mostra il link."""
    database, *_ = ambiente
    await database.set_guild_setting(100, restore_module.SETTING_RESTORE_MODE, restore_module.MODE_VERIFY_OAUTH)
    testo, _view = await proposta_consenso_restore(100, 1)
    assert "oauth2/authorize" in testo


async def test_ritirare_il_consenso(ambiente):
    _db, _s, oauth, _b = ambiente
    await oauth.salva_consenso(100, 1)
    assert await oauth.ha_consenso(100, 1)
    await oauth.ritira_consenso(100, 1)
    assert not await oauth.ha_consenso(100, 1)


async def test_senza_consenso_nessun_dm(ambiente):
    """M 12.12: utente senza consenso, nessun DM; con consenso, DM."""
    _db, snap, oauth, backup = ambiente
    await backup.define_main(100)
    await backup.define_backup(100, 200)
    await snap.save_snapshot(100, [(1, "U1", None), (2, "U2", None)])
    await oauth.salva_consenso(100, 2)
    u1, u2 = _FakeUser(1), _FakeUser(2)
    cog = RestoreCog(bot=_FakeBot({1: u1, 2: u2}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert u1.messaggi_ricevuti == []
    assert len(u2.messaggi_ricevuti) == 1
    assert "nessun consenso ai DM): 1" in interaction.followup.sent_messages[0][0]


class _Esito:
    def __init__(self, success: bool) -> None:
        self.success = success


class _Ogg:
    def __init__(self, id_: int) -> None:
        self.id = id_


async def test_verifica_riuscita_propone_il_consenso(ambiente):
    _db, _s, _o, backup = ambiente
    await backup.define_main(100)
    inviati = []

    async def invia(testo, view=None):
        inviati.append((testo, view))

    await proponi_consenso_restore(invia, _Ogg(100), _Ogg(1), _Esito(False))
    assert inviati == []
    await proponi_consenso_restore(invia, _Ogg(100), _Ogg(1), _Esito(True))
    assert len(inviati) == 1 and isinstance(inviati[0][1], ConsensoRestoreView)


async def test_invito_classico_rifiutato_da_discord_si_spiega(ambiente):
    """M 12.16 (LIM-36): server a 1000 inviti, nessun DM con un invito che non c'è."""
    import discord

    database, snap, oauth, backup = ambiente
    await database.set_guild_setting(200, restore_module.SETTING_RESTORE_MODE, restore_module.MODE_CLASSIC_INVITE)
    await backup.define_main(100)
    await backup.define_backup(100, 200)
    await snap.save_snapshot(100, [(1, "U1", None)])
    await oauth.salva_consenso(100, 1)
    utente = _FakeUser(1)
    cog = RestoreCog(bot=_FakeBot({1: utente}))
    interaction = _FakeInteraction(guild_id=200)

    class _Pieno:
        status = 400
        reason = "Bad Request"

    async def rifiuta(**kw):
        raise discord.HTTPException(_Pieno(), "Maximum number of invites reached (1000)")

    interaction.channel.create_invite = rifiuta
    await cog.restore_users.callback(cog, interaction, "100")
    assert utente.messaggi_ricevuti == []
    assert "Invito non creato, utenti non contattati: 1" in interaction.followup.sent_messages[0][0]


class _Clic:
    """Interazione finta di un clic, dopo un riavvio: il bot non ha più la view."""

    def __init__(self, user_id: int) -> None:
        self.user = _Ogg(user_id)
        self.modifiche = []
        self.response = self

    async def edit_message(self, **kw):
        self.modifiche.append(kw)


async def test_bottoni_del_consenso_persistenti_dopo_un_riavvio(ambiente):
    """M 12.12: custom_id fissi con il server, nessun timeout; ricostruiti dal solo custom_id."""
    _db, _s, oauth, backup = ambiente
    await backup.define_main(100)
    _testo, view = await proposta_consenso_restore(100, 1)
    assert view.timeout is None
    custom_id = [b.custom_id for b in view.children]
    assert custom_id == ["restore:consenso:100:si", "restore:consenso:100:no"]

    schema = BottoneConsensoRestore.__discord_ui_compiled_template__
    clic = _Clic(1)
    si = await BottoneConsensoRestore.from_custom_id(clic, None, schema.fullmatch(custom_id[0]))
    await si.callback(clic)
    assert await oauth.ha_consenso(100, 1)
    assert clic.modifiche[0]["view"] is None
    no = await BottoneConsensoRestore.from_custom_id(clic, None, schema.fullmatch(custom_id[1]))
    await no.callback(clic)
    assert not await oauth.ha_consenso(100, 1)

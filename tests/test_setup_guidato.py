"""
tests/test_setup_guidato.py
===========================
UTL-121 (D124): setup guidato, primo setup e modifica. Niente scritto prima della conferma, solo ciò che è
cambiato, ruolo admin controllato prima di scrivere, permesso tolto a metà.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.utility.setup_guidato as cog
from core import setup_guidato_logic as logica
from core.procedura_guidata import Fase, StatoProcedura, VistaGuidata
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


def test_modo_primo_o_modifica():
    assert logica.modo_setup({"a": None}, {"m": False}) == "primo"
    assert logica.modo_setup({"a": 5}, {"m": False}) == "modifica"
    assert logica.modo_setup({"a": None}, {"m": True}) == "modifica"


def test_solo_i_cambi():
    assert logica.ruoli_cambiati({"a": 1, "b": None}, {"a": 1, "b": 2}) == [("b", 2)]
    assert logica.moduli_cambiati({"x": True, "y": False}, {"x": True, "y": True}) == [("y", True)]


@pytest.fixture
def mondo(monkeypatch):
    imposta_ruolo = AsyncMock()
    imposta_modulo = AsyncMock()
    monkeypatch.setattr(cog, "imposta_ruolo", imposta_ruolo)
    monkeypatch.setattr(cog, "imposta_modulo", imposta_modulo)
    monkeypatch.setattr(cog, "puo_usare", AsyncMock(return_value=True))
    monkeypatch.setattr(cog, "lingua_interazione", AsyncMock(return_value="it"))
    monkeypatch.setattr(cog, "leggi_ruolo", AsyncMock(return_value=None))
    monkeypatch.setattr(cog, "ruolo_valido_per_server", lambda g, r: True)
    guild = fake_guild()
    guild.get_role = MagicMock(return_value=MagicMock())
    return imposta_ruolo, imposta_modulo, guild


def _dati(**extra):
    base = {
        "iniziali_ruoli": {"admin_role_id": None, "mod_role_id": None, "modban_role_id": None},
        "ruoli": {"admin_role_id": None, "mod_role_id": None, "modban_role_id": None},
        "iniziali_moduli": {"fun": False, "music": True},
        "moduli": {"fun": True, "music": True},
    }
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_conferma_scrive_solo_i_cambiamenti(mondo):
    imposta_ruolo, imposta_modulo, guild = mondo
    dati = _dati()
    dati["ruoli"]["mod_role_id"] = 55
    inter = fake_interaction(guild=guild, user=fake_member(user_id=7))
    inter.user.guild_permissions.administrator = True
    testo = await cog.scrivi_setup(inter, dati)
    assert imposta_ruolo.await_count == 1
    assert imposta_modulo.await_count == 1 and imposta_modulo.await_args.args[2:4] == ("fun", True)
    assert "1 ruoli e 1 moduli" in testo


@pytest.mark.asyncio
async def test_ruolo_admin_senza_permesso_non_scrive_niente(mondo):
    imposta_ruolo, imposta_modulo, guild = mondo
    dati = _dati()
    dati["ruoli"]["mod_role_id"] = 55
    dati["ruoli"]["admin_role_id"] = 66
    inter = fake_interaction(guild=guild, user=fake_member(user_id=7))
    inter.user.guild_permissions.administrator = False
    guild.owner_id = 999
    with pytest.raises(ValueError):
        await cog.scrivi_setup(inter, dati)
    imposta_ruolo.assert_not_awaited()
    imposta_modulo.assert_not_awaited()


@pytest.mark.asyncio
async def test_permesso_tolto_a_meta(mondo, monkeypatch):
    imposta_ruolo, imposta_modulo, guild = mondo
    monkeypatch.setattr(cog, "puo_usare", AsyncMock(return_value=False))
    with pytest.raises(ValueError):
        await cog.scrivi_setup(fake_interaction(guild=guild), _dati())
    imposta_modulo.assert_not_awaited()


@pytest.mark.asyncio
async def test_annulla_non_scrive(mondo):
    imposta_ruolo, imposta_modulo, guild = mondo
    stato = StatoProcedura(7, (cog.Passo(cog.PASSO_RUOLI),), _dati())
    vista = VistaGuidata(
        stato, titolo="t", lingua="it", permesso=cog.permesso, costruttori={cog.PASSO_RUOLI: lambda v: []},
        testi={cog.PASSO_RUOLI: lambda v: ""}, riepilogo=lambda v: "", conferma=cog.scrivi_setup,
    )
    await vista._annulla(fake_interaction(guild=guild, user=fake_member(user_id=7)))
    assert stato.fase is Fase.ANNULLATA
    imposta_ruolo.assert_not_awaited()
    imposta_modulo.assert_not_awaited()


def test_riepilogo_senza_cambi():
    d = _dati()
    d["moduli"] = dict(d["iniziali_moduli"])
    assert "Nessun cambiamento" in cog.testo_riepilogo(d, {}, "it")


def test_riepilogo_con_cambi():
    d = _dati()
    moduli = {"fun": SimpleNamespace(display_name="Fun"), "music": SimpleNamespace(display_name="Musica")}
    assert "Si accende: Fun" in cog.testo_riepilogo(d, moduli, "it")

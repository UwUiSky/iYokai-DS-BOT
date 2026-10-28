"""
tests/test_user_app_supporto_cog.py
===================================
SPEC B.9 (#107): `/supporto` di iYokai App e l'ascolto dei thread dello staff sul bot principale.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import cogs.user_app.supporto as sup
import cogs.user_app.supporto_staff as staff
from core.repositories.user_app_repo import UserAppRepository
from core.support_service import RichiestaNonTrovata, SupportoNonAttivo, TroppeRichieste
from tests.support.discord_fakes import fake_interaction, fake_member, fake_message


@pytest.fixture
def cog(monkeypatch, clean_db):
    monkeypatch.setattr(sup, "user_app_repo", UserAppRepository(pool_provider=lambda: clean_db))
    bot = MagicMock(tree=MagicMock())
    bot.bot_principale = MagicMock()
    return sup.SupportoCog(bot)


def _i(user_id=7):
    return fake_interaction(user=fake_member(user_id=user_id))


def _risposta(i):
    return i.followup.send.await_args.args[0]


async def test_apri_conferma_con_il_numero(cog):
    i = _i()
    with patch.object(sup, "apri_richiesta", AsyncMock(return_value=SimpleNamespace(numero=5, thread_id=1))) as apri:
        await cog.apri.callback(cog, i, "Problema", "Il bot non risponde più")
    assert "`5`" in _risposta(i) and apri.await_args.args[2] == 7


@pytest.mark.parametrize("errore, parte", [(TroppeRichieste(), "3 richieste"), (SupportoNonAttivo(), "non è attiva")])
async def test_apri_errori(cog, errore, parte):
    i = _i()
    with patch.object(sup, "apri_richiesta", AsyncMock(side_effect=errore)):
        await cog.apri.callback(cog, i, "Problema", "Il bot non risponde più")
    assert parte in _risposta(i)


async def test_senza_bot_principale_rimanda_al_supporto(cog):
    cog.bot.bot_principale = None
    i = _i()
    await cog.apri.callback(cog, i, "Problema", "Il bot non risponde più")
    assert "non è attiva" in _risposta(i)


async def test_rispondi_e_richiesta_non_trovata(cog):
    i = _i()
    with patch.object(sup, "risposta_dell_utente", AsyncMock()) as r:
        await cog.rispondi.callback(cog, i, 5, "ecco il log")
    assert "inviato" in _risposta(i) and r.await_args.args[1:] == (7, 5, "ecco il log")
    i = _i()
    with patch.object(sup, "risposta_dell_utente", AsyncMock(side_effect=RichiestaNonTrovata())):
        await cog.rispondi.callback(cog, i, 5, "ecco il log")
    assert "Non trovo" in _risposta(i)


async def test_elenco_delle_richieste(cog):
    i = _i()
    await cog.elenco.callback(cog, i)
    assert "Non hai" in i.response.send_message.await_args.args[0]
    await sup.user_app_repo.apri_richiesta(7, "Problema grosso", "testo")
    i = _i()
    await cog.elenco.callback(cog, i)
    assert "Problema grosso" in i.response.send_message.await_args.kwargs["embed"].description


async def test_staff_inoltra_solo_dal_canale_dell_assistenza(monkeypatch):
    cog = staff.SupportoStaffCog(MagicMock())
    inoltra = AsyncMock()
    monkeypatch.setattr(staff, "inoltra_risposta_staff", inoltra)
    monkeypatch.setattr(staff, "config", SimpleNamespace(SUPPORT_CHANNEL_ID=55))
    altro = fake_message(1, content="x")
    altro.channel = SimpleNamespace(parent_id=99)
    await cog.on_message(altro)
    inoltra.assert_not_awaited()
    giusto = fake_message(2, content="x")
    giusto.channel = SimpleNamespace(parent_id=55)
    await cog.on_message(giusto)
    inoltra.assert_awaited_once()
    inoltra.side_effect = RuntimeError("db giù")
    await cog.on_message(giusto)  # non solleva


async def test_thread_archiviato_chiude_la_richiesta(monkeypatch):
    cog = staff.SupportoStaffCog(MagicMock())
    chiudi = AsyncMock()
    monkeypatch.setattr(staff, "chiudi_se_archiviato", chiudi)
    monkeypatch.setattr(staff, "config", SimpleNamespace(SUPPORT_CHANNEL_ID=55))
    prima, dopo = SimpleNamespace(archived=False, parent_id=55), SimpleNamespace(archived=True, parent_id=55)
    await cog.on_thread_update(prima, dopo)
    chiudi.assert_awaited_once()
    await cog.on_thread_update(dopo, dopo)  # già archiviato: niente
    assert chiudi.await_count == 1


async def test_il_cog_dello_staff_si_carica_solo_sul_principale():
    principale, app = MagicMock(spec=["add_cog"]), MagicMock(spec=["add_cog", "istanza"])
    principale.add_cog = AsyncMock()
    app.add_cog, app.istanza = AsyncMock(), "app"
    await staff.setup(principale)
    await staff.setup(app)
    principale.add_cog.assert_awaited_once()
    app.add_cog.assert_not_awaited()

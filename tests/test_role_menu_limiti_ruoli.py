"""
tests/test_role_menu_limiti_ruoli.py
====================================
Menu dei ruoli (#123): tetto e minimo di ruoli (RUO-062, 063), posti limitati (RUO-065),
liste di accesso svuotabili (RUO-068). Archivio su PostgreSQL vero, cog con finti Discord.
"""

import pytest

from tests.test_role_menu_modalita import _Scena, _ruoli_di


@pytest.mark.asyncio
async def test_RUO_062_bottoni_rispettano_il_tetto_di_ruoli(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.repo.update_menu(s.menu_id, max_selectable=2)
    u = s.utente(1000, 1001)
    i = s.interazione(u)
    await s.cog._handle_button_click(i, s.menu_id, 1002)
    u.add_roles.assert_not_awaited()
    assert "al massimo 2" in i.followup.send.await_args.args[0]
    u2 = s.utente(1000)
    await s.cog._handle_button_click(s.interazione(u2), s.menu_id, 1002)
    assert _ruoli_di(u2.add_roles.await_args) == {1002}


@pytest.mark.asyncio
async def test_RUO_063_il_minimo_non_lascia_togliere_l_ultimo(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.repo.update_menu(s.menu_id, min_roles=1)
    u = s.utente(1000)
    i = s.interazione(u)
    await s.cog._handle_button_click(i, s.menu_id, 1000)
    u.remove_roles.assert_not_awaited()
    assert "almeno 1" in i.followup.send.await_args.args[0]
    u2 = s.utente(1000, 1001)
    await s.cog._handle_button_click(s.interazione(u2), s.menu_id, 1000)
    u2.remove_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_RUO_065_posti_finiti_per_un_ruolo(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu(opzioni=())
    await s.repo.add_option(s.menu_id, 1000, "🎮", "A", max_members=1)
    s.ruoli[1000].members = [s.utente()]  # un posto solo, già preso
    u = s.utente()
    i = s.interazione(u)
    await s.cog._handle_button_click(i, s.menu_id, 1000)
    u.add_roles.assert_not_awaited()
    assert "posti" in i.followup.send.await_args.args[0]
    s.ruoli[1000].members = []
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    u.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_RUO_062_RUO_063_il_comando_modifica_salva_e_controlla(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, massimo=3, minimo=1)
    menu = await s.repo.get_menu(s.menu_id)
    assert (menu.max_selectable, menu.min_roles) == (3, 1)
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, massimo=1, minimo=2)  # minimo > massimo
    assert (await s.repo.get_menu(s.menu_id)).min_roles == 1
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, massimo=0, minimo=0)
    menu = await s.repo.get_menu(s.menu_id)
    assert (menu.max_selectable, menu.min_roles) == (None, None)


@pytest.mark.asyncio
async def test_RUO_068_svuota_gli_elenchi_di_accesso(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.repo.set_access_lists(s.menu_id, [1005, 1006], [1007])
    i = s.interazione(s.utente())
    await s.cog.access_cmd.callback(s.cog, i, menu_id=s.menu_id, elenco="ammesso", azione="svuota")
    menu = await s.repo.get_menu(s.menu_id)
    assert menu.allowed_role_ids == () and menu.excluded_role_ids == (1007,)
    await s.cog.access_cmd.callback(s.cog, i, menu_id=s.menu_id, elenco="escluso", azione="svuota")
    assert (await s.repo.get_menu(s.menu_id)).excluded_role_ids == ()

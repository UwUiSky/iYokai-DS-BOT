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


# ------------------------------------------------- aspetto e risposte (RUO-052, 081, 082, 085, 086)
def test_RUO_082_risposta_con_il_ruolo_e_tagliata():
    from core.role_menu_logic import MAX_RISPOSTA, risposta_personale

    assert risposta_personale("Ecco {ruolo}!", "<@&5>") == "Ecco <@&5>!"
    assert len(risposta_personale("x" * 500, "<@&5>")) == MAX_RISPOSTA


@pytest.mark.asyncio
async def test_RUO_052_colore_del_messaggio_e_ritorno_al_predefinito(clean_db, monkeypatch):
    from cogs.utility.role_menus import _build_embed

    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, colore="#C24A3A")
    menu = await s.repo.get_menu(s.menu_id)
    assert menu.color == 0xC24A3A and _build_embed(menu, []).color.value == 0xC24A3A
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, colore="rosso-forte")
    assert (await s.repo.get_menu(s.menu_id)).color == 0xC24A3A  # non valido: resta com'era
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, colore="predefinito")
    assert (await s.repo.get_menu(s.menu_id)).color is None


@pytest.mark.asyncio
async def test_RUO_085_colore_del_bottone(clean_db, monkeypatch):
    import discord

    s = _Scena(clean_db, monkeypatch)
    await s.menu(opzioni=())
    await s.repo.add_option(s.menu_id, 1000, "🎮", "A", button_style="danger")
    await s.repo.add_option(s.menu_id, 1001, "🎮", "B")
    vista = s.cog._build_button_view(s.menu_id, await s.repo.get_options(s.menu_id))
    assert [b.style for b in vista.children] == [discord.ButtonStyle.danger, discord.ButtonStyle.secondary]


@pytest.mark.asyncio
async def test_RUO_086_tendina_con_testo_guida_e_descrizione(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="select")
    await s.menu(opzioni=())
    await s.repo.add_option(s.menu_id, 1000, None, "A", description="La prima")
    vista = s.cog._build_select_view(s.menu_id, await s.repo.get_options(s.menu_id), None, "Scegli il gioco")
    tendina = vista.children[0]
    assert tendina.placeholder == "Scegli il gioco" and tendina.options[0].description == "La prima"


@pytest.mark.asyncio
async def test_RUO_081_RUO_082_avviso_spento_e_risposta_propria(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i0 = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i0, menu_id=s.menu_id, risposta="Hai preso {ruolo}!")
    u = s.utente()
    i = s.interazione(u)
    await s.cog._handle_button_click(i, s.menu_id, 1000)
    assert i.followup.send.await_args.args[0] == f"Hai preso {s.ruoli[1000].mention}!"
    await s.cog.edit_cmd.callback(s.cog, i0, menu_id=s.menu_id, avvisa=False)
    u2 = s.utente()
    i2 = s.interazione(u2)
    await s.cog._handle_button_click(i2, s.menu_id, 1001)
    u2.add_roles.assert_awaited_once()  # il ruolo si dà lo stesso
    i2.followup.send.assert_not_awaited()
    i2.delete_original_response.assert_awaited_once()


# ------------------------------------------------- gestione dei menu (RUO-076, 077, 079, 080, 087)
def test_RUO_077_sposta_ruolo_al_posto_scelto():
    from core.role_menu_logic import sposta_ruolo

    assert sposta_ruolo([1, 2, 3, 4], 4, 1) == [4, 1, 2, 3]
    assert sposta_ruolo([1, 2, 3, 4], 1, 3) == [2, 3, 1, 4]
    assert sposta_ruolo([1, 2, 3], 1, 25) == [2, 3, 1]


@pytest.mark.asyncio
async def test_RUO_076_RUO_077_opzione_cambia_emoji_e_posto(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.option_edit_cmd.callback(
        s.cog, i, menu_id=s.menu_id, ruolo=s.ruoli[1002], emoji="🔥", etichetta="Nuova", posto=1
    )
    opzioni = await s.repo.get_options(s.menu_id)
    assert [o.role_id for o in opzioni] == [1002, 1000, 1001]
    assert (opzioni[0].emoji, opzioni[0].label) == ("🔥", "Nuova")


@pytest.mark.asyncio
async def test_RUO_076_ruolo_non_del_menu_e_emoji_falsa_rifiutati(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.option_edit_cmd.callback(s.cog, i, menu_id=s.menu_id, ruolo=s.ruoli[1008], etichetta="X")
    assert "non è in questo menu" in i.followup.send.await_args.args[0]
    await s.cog.option_edit_cmd.callback(s.cog, i, menu_id=s.menu_id, ruolo=s.ruoli[1000], emoji="non-emoji")
    assert [o.emoji for o in await s.repo.get_options(s.menu_id)] == ["🎮"] * 3


@pytest.mark.asyncio
async def test_RUO_079_elimina_tenendo_il_messaggio(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.repo.set_menu_message(s.menu_id, 555)
    i = s.interazione(s.utente())
    await s.cog.delete_cmd.callback(s.cog, i, menu_id=s.menu_id, tieni_messaggio=True)
    assert await s.repo.get_menu(s.menu_id) is None
    s.messaggio.edit.assert_awaited_once_with(view=None)
    s.messaggio.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_080_svuota_chiede_conferma_e_poi_elimina_tutto(clean_db, monkeypatch):
    import cogs.utility.role_menus as rm

    monkeypatch.setattr(rm, "PAUSA_SVUOTA_SECONDI", 0)
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.purge_cmd.callback(s.cog, i)
    assert len(await s.repo.list_menus_for_guild(1)) == 2  # senza conferma non si tocca nulla
    assert "2" in i.response.send_message.await_args.args[0]
    await s.cog.purge_cmd.callback(s.cog, i, conferma=True)
    assert await s.repo.list_menus_for_guild(1) == []


@pytest.mark.asyncio
async def test_RUO_087_voce_togli_tutti_i_ruoli_nella_tendina(clean_db, monkeypatch):
    from core.role_menu_logic import VALORE_AZZERA

    s = _Scena(clean_db, monkeypatch, mode="select")
    await s.menu()
    i0 = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i0, menu_id=s.menu_id, voce_azzera=True)
    menu = await s.repo.get_menu(s.menu_id)
    vista = s.cog._build_select_view(menu.id, await s.repo.get_options(menu.id), None, "", menu.reset_option)
    assert vista.children[0].options[-1].value == VALORE_AZZERA
    u = s.utente(1000, 1001)
    i = s.interazione(u)
    tendina = vista.children[0]
    tendina._values = [VALORE_AZZERA]
    await s.cog._handle_select(i, s.menu_id, tendina)
    assert _ruoli_di(u.remove_roles.await_args) == {1000, 1001}

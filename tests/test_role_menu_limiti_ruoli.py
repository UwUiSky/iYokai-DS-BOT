"""
tests/test_role_menu_limiti_ruoli.py
====================================
Menu dei ruoli (#123): tetto e minimo di ruoli (RUO-062, 063), posti limitati (RUO-065),
liste di accesso svuotabili (RUO-068). Archivio su PostgreSQL vero, cog con finti Discord.
"""

import pytest

from tests.support.discord_fakes import fake_role

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


# ------------------------------------------------- coppie in un colpo (RUO-048, 049)
@pytest.mark.asyncio
async def test_RUO_049_aggiungi_molti_su_un_menu_esistente(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu(opzioni=())
    s.guild.roles = list(s.ruoli.values())
    i = s.interazione(s.utente())
    i.user.top_role = fake_role_alto()
    await s.cog.add_many_cmd.callback(s.cog, i, s.menu_id, f"🎮 <@&1000>; 🎨 R1001")
    assert [o.role_id for o in await s.repo.get_options(s.menu_id)] == [1000, 1001]
    assert "Aggiunte 2" in i.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_RUO_049_se_una_coppia_non_va_non_si_aggiunge_niente(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu(opzioni=())
    s.guild.roles = list(s.ruoli.values())
    i = s.interazione(s.utente())
    i.user.top_role = fake_role_alto()
    await s.cog.add_many_cmd.callback(s.cog, i, s.menu_id, "🎮 <@&1000>; 🎨 Inventato")
    assert await s.repo.get_options(s.menu_id) == []
    assert "Non trovo" in i.followup.send.await_args.args[0]
    await s.cog.add_many_cmd.callback(s.cog, i, s.menu_id, "<@&1000>")  # bottoni: serve l'emoji
    assert await s.repo.get_options(s.menu_id) == [] and "emoji" in i.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_RUO_048_crea_con_le_coppie_pubblica_subito(clean_db, monkeypatch):
    import discord

    s = _Scena(clean_db, monkeypatch)
    s.guild.roles = list(s.ruoli.values())
    i = s.interazione(s.utente())
    i.user.top_role = fake_role_alto()
    modo = discord.app_commands.Choice(name="Button", value="button")
    s.canale.__class__ = discord.TextChannel  # il comando vuole un canale di testo vero
    await s.cog.create_cmd.callback(s.cog, i, "Titolo", modo, channel=s.canale, coppie="🎮 <@&1000>; 🎨 <@&1001>")
    menu = (await s.repo.list_menus_for_guild(1))[0]
    assert len(await s.repo.get_options(menu.id)) == 2
    s.canale.send.assert_awaited()  # il messaggio è uscito


def fake_role_alto():
    from tests.support.discord_fakes import fake_role

    return fake_role(role_id=5000, name="Admin", position=45)


# ------------------------------------------------- RUO-072..075: messaggi e reazioni
@pytest.mark.asyncio
async def test_RUO_072_RUO_073_il_menu_si_aggancia_a_un_messaggio_di_altri(clean_db, monkeypatch):
    import discord

    import cogs.utility.role_menus as rm

    monkeypatch.setattr(rm, "PAUSA_REAZIONI_SECONDI", 0)
    s = _Scena(clean_db, monkeypatch, mode="reaction")
    await s.menu()
    s.canale.__class__ = discord.TextChannel
    altrui = s.messaggio
    altrui.id = 4242
    altrui.author = MagicMockId(1)  # non è il bot (999)
    i = s.interazione(s.utente())
    await s.cog.move_cmd.callback(s.cog, i, s.menu_id, "4242", s.canale)
    menu = await s.repo.get_menu(s.menu_id)
    assert (menu.message_id, menu.external) == (4242, True)
    altrui.edit.assert_not_awaited()  # il messaggio di altri non si tocca
    assert altrui.add_reaction.await_count == 3


@pytest.mark.asyncio
async def test_RUO_072_eliminare_un_menu_esterno_non_cancella_il_messaggio(clean_db, monkeypatch):
    import discord

    s = _Scena(clean_db, monkeypatch, mode="reaction")
    await s.menu()
    await s.repo.update_menu(s.menu_id, message_id=4242, external=True)
    s.canale.__class__ = discord.TextChannel
    i = s.interazione(s.utente())
    await s.cog.delete_cmd.callback(s.cog, i, menu_id=s.menu_id)
    s.messaggio.delete.assert_not_awaited()
    assert await s.repo.get_menu(s.menu_id) is None


@pytest.mark.asyncio
async def test_RUO_074_ripara_rimette_le_reazioni_mancanti(clean_db, monkeypatch):
    import discord

    import cogs.utility.role_menus as rm

    monkeypatch.setattr(rm, "PAUSA_REAZIONI_SECONDI", 0)
    s = _Scena(clean_db, monkeypatch, mode="reaction")
    await s.menu()
    await s.repo.set_menu_message(s.menu_id, 555)
    s.canale.__class__ = discord.TextChannel
    i = s.interazione(s.utente())
    await s.cog.repair_cmd.callback(s.cog, i, s.menu_id)
    assert s.messaggio.add_reaction.await_count >= 1
    assert "a posto" in i.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_RUO_075_emoji_di_un_altro_server_si_accetta_e_la_mette_l_admin(clean_db, monkeypatch):
    import discord

    s = _Scena(clean_db, monkeypatch, mode="reaction")
    await s.menu(opzioni=())
    s.canale.__class__ = discord.TextChannel
    s.guild.me.guild_permissions = discord.Permissions.all()
    ammin = s.utente()
    ammin.top_role = fake_role_alto()
    i = s.interazione(ammin)
    estranea = "<:altro:123456789012345678>"
    await s.cog.add_option_cmd.callback(s.cog, i, s.menu_id, s.ruoli[1000], estranea)
    assert await s.repo.get_options(s.menu_id) == []  # senza il permesso esplicito si rifiuta
    await s.cog.add_option_cmd.callback(s.cog, i, s.menu_id, s.ruoli[1000], estranea, emoji_esterna=True)
    assert [o.emoji for o in await s.repo.get_options(s.menu_id)] == [estranea]
    s.messaggio.add_reaction.assert_not_awaited()  # il bot non la può mettere
    assert "metti tu la reazione" in i.followup.send.await_args.args[0]


class MagicMockId:
    def __init__(self, id_):
        self.id = id_


# ------------------------------------------------- RUO-070, 071, 088, 089
@pytest.mark.asyncio
async def test_RUO_070_scadenza_pianificata_e_menu_cancellato_allo_scatto(clean_db, monkeypatch):
    import discord
    from datetime import datetime, timedelta, timezone

    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.repo.set_menu_message(s.menu_id, 555)
    s.canale.__class__ = discord.TextChannel
    s.bot.get_guild.return_value = s.guild
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, scade_tra_ore=2)
    azione = s.scheduler.schedule.await_args
    assert azione.args[2] == "rolemenu_expire" and azione.args[4] == {"menu_id": s.menu_id}
    menu = await s.repo.get_menu(s.menu_id)
    assert menu.expires_at - datetime.now(timezone.utc) > timedelta(hours=1, minutes=55)
    await s.cog.handle_rolemenu_scade(1, 0, {"menu_id": s.menu_id})  # troppo presto: la scadenza non è arrivata
    assert await s.repo.get_menu(s.menu_id) is not None
    await s.repo.update_menu(s.menu_id, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    await s.cog.handle_rolemenu_scade(1, 0, {"menu_id": s.menu_id})
    assert await s.repo.get_menu(s.menu_id) is None
    s.messaggio.delete.assert_awaited()


@pytest.mark.asyncio
async def test_RUO_070_scadenza_tolta_con_zero(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, scade_tra_ore=5)
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, scade_tra_ore=0)
    assert (await s.repo.get_menu(s.menu_id)).expires_at is None


@pytest.mark.asyncio
async def test_RUO_088_cambia_il_tipo_del_menu_e_tiene_le_opzioni(clean_db, monkeypatch):
    import discord

    s = _Scena(clean_db, monkeypatch, mode="reaction")
    await s.menu()
    await s.repo.set_menu_message(s.menu_id, 555)
    s.canale.__class__ = discord.TextChannel
    nuovo_msg = MagicMockMsg(999)
    s.canale.send.return_value = nuovo_msg
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, tipo="button")
    menu = await s.repo.get_menu(s.menu_id)
    assert (menu.mode, menu.message_id) == ("button", 999)
    assert [o.label for o in await s.repo.get_options(s.menu_id)] == ["L1000", "L1001", "L1002"]
    s.messaggio.delete.assert_awaited()  # il vecchio messaggio è sparito


@pytest.mark.asyncio
async def test_RUO_088_senza_emoji_non_si_passa_alle_reazioni(clean_db, monkeypatch):
    import discord

    s = _Scena(clean_db, monkeypatch, mode="select")
    await s.menu(opzioni=())
    await s.repo.add_option(s.menu_id, 1000, None, "Solo etichetta")
    s.canale.__class__ = discord.TextChannel
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, tipo="reaction")
    assert (await s.repo.get_menu(s.menu_id)).mode == "select"
    assert "manca l'emoji" in i.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_RUO_089_modello_verifica_crea_un_menu_con_un_bottone_verde(clean_db, monkeypatch):
    import discord

    s = _Scena(clean_db, monkeypatch)
    s.guild.roles = list(s.ruoli.values())
    s.canale.__class__ = discord.TextChannel
    admin = s.utente()
    admin.top_role = fake_role_alto()
    i = s.interazione(admin)
    i.channel = s.canale
    await s.cog.template_cmd.callback(s.cog, i, "verifica", "<@&1000>")
    menu = (await s.repo.list_menus_for_guild(1))[0]
    assert (menu.mode, menu.behavior, menu.title) == ("button", "verify", "Verifica")
    opzione = (await s.repo.get_options(menu.id))[0]
    assert opzione.button_style == "success" and opzione.emoji  # emoji data dal modello
    i2 = s.interazione(admin)
    i2.channel = s.canale
    await s.cog.template_cmd.callback(s.cog, i2, "verifica", "<@&1000>; <@&1001>")  # il modello vuole un ruolo solo
    assert len(await s.repo.list_menus_for_guild(1)) == 1


@pytest.mark.asyncio
async def test_RUO_071_canale_dei_ruoli_si_legge_ma_non_si_scrive(clean_db, monkeypatch):
    import discord
    from unittest.mock import AsyncMock

    s = _Scena(clean_db, monkeypatch)
    s.guild.me.guild_permissions = discord.Permissions(manage_channels=True)
    s.guild.channels = []
    s.guild.default_role = fake_role(role_id=1, name="@everyone", position=0)
    s.guild.create_text_channel = AsyncMock(return_value=MagicMockMsg(77, mention="<#77>", name="ruoli"))
    staff = s.utente()
    staff.guild_permissions = discord.Permissions(manage_channels=True)
    i = s.interazione(staff)
    await s.cog.channel_cmd.callback(s.cog, i)
    sovr = s.guild.create_text_channel.await_args.kwargs["overwrites"]
    tutti = sovr[s.guild.default_role]
    assert tutti.view_channel is True and tutti.send_messages is False and tutti.add_reactions is False
    # chi non può gestire i canali non lo fa creare tramite il bot
    s.guild.create_text_channel.reset_mock()
    semplice = s.utente()
    semplice.guild_permissions = discord.Permissions()
    await s.cog.channel_cmd.callback(s.cog, s.interazione(semplice))
    s.guild.create_text_channel.assert_not_awaited()


class MagicMockMsg:
    def __init__(self, id_, **altro):
        from unittest.mock import AsyncMock, MagicMock

        self.id = id_
        self.reactions = []
        self.edit = AsyncMock()
        self.delete = AsyncMock()
        self.add_reaction = AsyncMock()
        self.clear_reaction = AsyncMock()
        self.author = MagicMock(id=999)
        for k, v in altro.items():
            setattr(self, k, v)


# ------------------------------------------------- RUO-084: numeri nelle etichette
@pytest.mark.asyncio
async def test_RUO_084_i_numeri_si_vedono_in_embed_bottoni_e_tendina(clean_db, monkeypatch):
    from cogs.utility.role_menus import _build_embed

    s = _Scena(clean_db, monkeypatch)
    await s.menu(opzioni=(1000,))
    opzioni = await s.repo.get_options(s.menu_id)
    menu = await s.repo.get_menu(s.menu_id)
    assert "(7)" in _build_embed(menu, opzioni, {1000: 7}).fields[0].value
    assert "(" not in _build_embed(menu, opzioni).fields[0].value  # spenti: niente numeri
    assert s.cog._build_button_view(s.menu_id, opzioni, {1000: 7}).children[0].label == "L1000 (7)"
    assert "(7)" in s.cog._build_select_view(s.menu_id, opzioni, None, "", False, {1000: 7}).children[0].options[0].label


@pytest.mark.asyncio
async def test_RUO_084_il_messaggio_si_aggiorna_dopo_un_uso_ma_non_piu_di_una_volta_ogni_5_minuti(clean_db, monkeypatch):
    import asyncio
    import discord

    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.repo.set_menu_message(s.menu_id, 555)
    await s.repo.update_menu(s.menu_id, show_counts=True)
    s.canale.__class__ = discord.TextChannel
    s.ruoli[1000].members = [object(), object()]
    u = s.utente()
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    await asyncio.gather(*list(s.cog._compiti))
    assert s.messaggio.edit.await_count == 1
    assert "(2)" in s.messaggio.edit.await_args.kwargs["embed"].fields[0].value
    u2 = s.utente()
    await s.cog._handle_button_click(s.interazione(u2), s.menu_id, 1001)
    await asyncio.gather(*list(s.cog._compiti))
    assert s.messaggio.edit.await_count == 1  # troppo presto: nessun secondo aggiornamento

"""
tests/test_ruoli_extra_cog.py
=============================
#123 (r2ben): RUO-083 (più ruoli per opzione), RUO-069 (gruppo di menu), RUO-053 (immagine nel menu),
RUO-046 (colore del nome), RUO-047 (creazione guidata), RUO-045 (ruolo personale), RUO-012 (immagini del benvenuto).
Archivio su PostgreSQL vero, cog con finti Discord.
"""

import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

import cogs.utility.ruoli_extra as rx
from cogs.utility.ruoli_extra import CreazioneGuidata, RuoliExtraCog
from core.repositories.role_menu_repo import RoleMenuRepository
from core.repositories.ruoli_extra_repo import RuoliExtraRepository
from core.ruoli_guidata_logic import StatoGuidato
from tests.support.discord_fakes import fake_interaction, fake_member, fake_role
from tests.test_role_menu_modalita import _Scena, _ruoli_di


def _png(w=20, h=10):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (9, 9, 200)).save(b, "PNG")
    return b.getvalue()


def _staff(scena):
    u = fake_member(user_id=1, name="staff", roles=[fake_role(role_id=7, name="Mod", position=60)],
                    guild_permissions=discord.Permissions(manage_guild=True))
    u.guild = scena.guild
    return u


def _comando(scena, monkeypatch):
    monkeypatch.setattr(rx, "role_menu_repo", scena.repo)
    cog = RuoliExtraCog(scena.bot)
    scena.bot.get_cog.return_value = scena.cog
    return cog


# ------------------------------------------------------------------ RUO-083
@pytest.mark.asyncio
async def test_RUO_083_una_opzione_da_piu_ruoli(clean_db, monkeypatch):
    # RUO-083
    s = _Scena(clean_db, monkeypatch)
    await s.menu(opzioni=(1000,))
    await RuoliExtraRepository(lambda: clean_db).aggiungi_extra(s.menu_id, 1000, 1005)
    u = s.utente()
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    assert _ruoli_di(u.add_roles.await_args) == {1000, 1005}
    u2 = s.utente(1000, 1005)
    await s.cog._handle_button_click(s.interazione(u2), s.menu_id, 1000)
    assert _ruoli_di(u2.remove_roles.await_args) == {1000, 1005}


@pytest.mark.asyncio
async def test_RUO_083_ogni_ruolo_passa_da_check_role_assignable(clean_db, monkeypatch):
    # RUO-083: un ruolo in più diventato pericoloso non si dà, gli altri sì
    s = _Scena(clean_db, monkeypatch)
    await s.menu(opzioni=(1000,))
    await RuoliExtraRepository(lambda: clean_db).aggiungi_extra(s.menu_id, 1000, 1005)
    s.ruoli[1005].permissions = discord.Permissions(ban_members=True)
    u = s.utente()
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    assert _ruoli_di(u.add_roles.await_args) == {1000}


@pytest.mark.asyncio
async def test_RUO_083_comando_rifiuta_ruoli_pericolosi_e_oltre_cinque(clean_db, monkeypatch):
    # RUO-083
    s = _Scena(clean_db, monkeypatch)
    await s.menu(opzioni=(1000,))
    cmd = _comando(s, monkeypatch)
    staff = _staff(s)
    peric = fake_role(role_id=1008, name="Admin", position=1, permissions=discord.Permissions(administrator=True))
    i = fake_interaction(guild=s.guild, user=staff)
    await cmd.ruoli_extra.callback(cmd, i, s.menu_id, s.ruoli[1000], peric)
    assert "administrator" in i.response.send_message.await_args.args[0]
    for rid in (1001, 1002, 1003, 1004):
        i = fake_interaction(guild=s.guild, user=staff)
        await cmd.ruoli_extra.callback(cmd, i, s.menu_id, s.ruoli[1000], s.ruoli[rid])
    assert len((await RuoliExtraRepository(lambda: clean_db).extra_del_menu(s.menu_id))[1000]) == 4
    i = fake_interaction(guild=s.guild, user=staff)
    await cmd.ruoli_extra.callback(cmd, i, s.menu_id, s.ruoli[1000], s.ruoli[1005])
    assert "al massimo 5" in i.response.send_message.await_args.args[0]


# ------------------------------------------------------------------ RUO-069
async def _due_menu_in_gruppo(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    a = await s.menu(opzioni=(1000, 1001))
    b = await s.menu(opzioni=(1002, 1003))
    repo = RuoliExtraRepository(lambda: clean_db)
    assert await repo.imposta_gruppo(a, 1, "colori") is None
    assert await repo.imposta_gruppo(b, 1, "colori") is None
    return s, a, b


@pytest.mark.asyncio
async def test_RUO_069_il_ruolo_vecchio_si_toglie_in_una_sola_richiesta(clean_db, monkeypatch):
    # RUO-069
    s, a, b = await _due_menu_in_gruppo(clean_db, monkeypatch)
    u = s.utente(1000)
    await s.cog._handle_button_click(s.interazione(u), b, 1002)
    u.edit.assert_awaited_once()
    finali = {r.id for r in u.edit.await_args.kwargs["roles"]}
    assert finali == {1002}  # niente 1000
    u.add_roles.assert_not_awaited()
    u.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_069_fuori_dal_gruppo_non_si_tocca_nulla(clean_db, monkeypatch):
    # RUO-069
    s, a, b = await _due_menu_in_gruppo(clean_db, monkeypatch)
    u = s.utente(1000, 1009)  # 1009 non è di nessun menu
    await s.cog._handle_button_click(s.interazione(u), b, 1002)
    assert 1009 in {r.id for r in u.edit.await_args.kwargs["roles"]}


@pytest.mark.asyncio
async def test_RUO_069_il_tetto_dei_menu_del_gruppo(clean_db, monkeypatch):
    # RUO-069
    s = _Scena(clean_db, monkeypatch)
    repo = RuoliExtraRepository(lambda: clean_db)
    for _ in range(10):
        m = await s.menu(opzioni=())
        assert await repo.imposta_gruppo(m, 1, "x") is None
    m = await s.menu(opzioni=())
    assert await repo.imposta_gruppo(m, 1, "x") is not None
    assert await repo.imposta_gruppo(m, 1, None) is None


@pytest.mark.asyncio
async def test_RUO_069_comando_gruppo_pulisce_il_nome(clean_db, monkeypatch):
    # RUO-069
    s = _Scena(clean_db, monkeypatch)
    m = await s.menu()
    cmd = _comando(s, monkeypatch)
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.gruppo.callback(cmd, i, m, "  @everyone Colori ")
    assert (await s.repo.get_menu(m)).gruppo == "everyone colori"
    await cmd.gruppo.callback(cmd, fake_interaction(guild=s.guild, user=_staff(s)), m, "")
    assert (await s.repo.get_menu(m)).gruppo is None


@pytest.mark.asyncio
async def test_RUO_069_un_menu_di_un_altro_server_non_si_tocca(clean_db, monkeypatch):
    # RUO-069
    s = _Scena(clean_db, monkeypatch)
    altro = await s.repo.create_menu(guild_id=2, channel_id=1, mode="button", toggle=True, max_selectable=None, title="x", description="")
    cmd = _comando(s, monkeypatch)
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.gruppo.callback(cmd, i, altro, "x")
    assert (await s.repo.get_menu(altro)).gruppo is None


# ------------------------------------------------------------------ RUO-053
@pytest.mark.asyncio
async def test_RUO_053_immagine_da_allegato_solo_ricodificata(clean_db, monkeypatch):
    # RUO-053
    s = _Scena(clean_db, monkeypatch)
    m = await s.menu()
    await s.repo.set_menu_message(m, 555)
    s.messaggio.attachments = []
    cmd = _comando(s, monkeypatch)
    originale = _png()
    allegato = MagicMock(spec=discord.Attachment)
    allegato.size = len(originale)
    allegato.read = AsyncMock(return_value=originale)
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.immagine.callback(cmd, i, m, allegato, "", False)
    salvata = await RuoliExtraRepository(lambda: clean_db).immagine_menu(m)
    assert salvata is not None and Image.open(io.BytesIO(salvata)).size == (20, 10)
    kw = s.messaggio.edit.await_args.kwargs
    assert kw["attachments"][0].filename == "menu.png"
    assert kw["embed"].image.url == "attachment://menu.png"


@pytest.mark.asyncio
async def test_RUO_053_allegato_troppo_pesante_o_non_immagine(clean_db, monkeypatch):
    # RUO-053
    s = _Scena(clean_db, monkeypatch)
    m = await s.menu()
    cmd = _comando(s, monkeypatch)
    pesante = MagicMock(spec=discord.Attachment)
    pesante.size = 50 * 1024 * 1024
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.immagine.callback(cmd, i, m, pesante, "", False)
    falso = MagicMock(spec=discord.Attachment)
    falso.size = 10
    falso.read = AsyncMock(return_value=b"<svg onload=alert(1)>")
    i2 = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.immagine.callback(cmd, i2, m, falso, "", False)
    assert await RuoliExtraRepository(lambda: clean_db).immagine_menu(m) is None
    assert i2.followup.send.await_count == 1


@pytest.mark.asyncio
async def test_RUO_053_indirizzo_passa_da_safe_http(clean_db, monkeypatch):
    # RUO-053
    s = _Scena(clean_db, monkeypatch)
    m = await s.menu()
    cmd = _comando(s, monkeypatch)
    sicuro = AsyncMock(return_value=False)
    scarica = AsyncMock(return_value=(_png(), "image/png"))
    monkeypatch.setattr(rx, "url_e_sicuro", sicuro)
    monkeypatch.setattr(rx, "safe_richiesta_byte", scarica)
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.immagine.callback(cmd, i, m, None, "http://192.168.1.1/x.png", False)
    scarica.assert_not_awaited()  # rete privata: mai scaricata
    assert await RuoliExtraRepository(lambda: clean_db).immagine_menu(m) is None
    sicuro.return_value = True
    await cmd.immagine.callback(cmd, fake_interaction(guild=s.guild, user=_staff(s)), m, None, "https://esempio.org/x.png", False)
    scarica.assert_awaited_once()
    assert await RuoliExtraRepository(lambda: clean_db).immagine_menu(m) is not None


@pytest.mark.asyncio
async def test_RUO_053_serve_una_sola_fonte(clean_db, monkeypatch):
    # RUO-053
    s = _Scena(clean_db, monkeypatch)
    m = await s.menu()
    cmd = _comando(s, monkeypatch)
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.immagine.callback(cmd, i, m, None, "", False)
    assert i.response.send_message.await_count == 1


@pytest.mark.asyncio
async def test_RUO_053_pubblicazione_manda_il_file(clean_db, monkeypatch):
    # RUO-053
    s = _Scena(clean_db, monkeypatch)
    m = await s.menu()
    await RuoliExtraRepository(lambda: clean_db).imposta_immagine_menu(m, _png())
    menu = await s.repo.get_menu(m)
    await s.cog._pubblica_menu(s.guild, menu, await s.repo.get_options(m))
    kw = s.canale.send.await_args.kwargs
    assert kw["file"].filename == "menu.png" and kw["embed"].image.url == "attachment://menu.png"


# ------------------------------------------------------------------ RUO-046
async def _tavolozza(clean_db, monkeypatch, comportamento="unique"):
    s = _Scena(clean_db, monkeypatch, comportamento=comportamento)
    m = await s.menu(opzioni=(1000, 1001, 1002))
    await RuoliExtraRepository(lambda: clean_db).imposta_colori(m, 1, True)
    return s, m


@pytest.mark.asyncio
async def test_RUO_046_colore_cambia_in_una_richiesta_e_non_tocca_il_resto(clean_db, monkeypatch):
    # RUO-046
    s, m = await _tavolozza(clean_db, monkeypatch)
    cmd = _comando(s, monkeypatch)
    u = s.utente(1000, 1009)
    await cmd.colore.callback(cmd, s.interazione(u), "1001", False)
    finali = {r.id for r in u.edit.await_args.kwargs["roles"]}
    assert finali == {1001, 1009}


@pytest.mark.asyncio
async def test_RUO_046_solo_ruoli_della_tavolozza(clean_db, monkeypatch):
    # RUO-046: un ID che non è in tavolozza (anche se è un ruolo vero) si rifiuta
    s, m = await _tavolozza(clean_db, monkeypatch)
    cmd = _comando(s, monkeypatch)
    u = s.utente()
    i = s.interazione(u)
    await cmd.colore.callback(cmd, i, "1005", False)
    u.add_roles.assert_not_awaited()
    u.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_046_ruolo_colore_con_permessi_non_si_da(clean_db, monkeypatch):
    # RUO-046: check_role_assignable con self_service=True
    s, m = await _tavolozza(clean_db, monkeypatch)
    s.ruoli[1001].permissions = discord.Permissions(manage_roles=True)
    cmd = _comando(s, monkeypatch)
    u = s.utente()
    i = s.interazione(u)
    await cmd.colore.callback(cmd, i, "1001", False)
    u.add_roles.assert_not_awaited()
    assert "manage_roles" in i.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_RUO_046_togli_il_colore(clean_db, monkeypatch):
    # RUO-046
    s, m = await _tavolozza(clean_db, monkeypatch)
    cmd = _comando(s, monkeypatch)
    u = s.utente(1002, 1009)
    await cmd.colore.callback(cmd, s.interazione(u), "", True)
    assert _ruoli_di(u.remove_roles.await_args) == {1002}


@pytest.mark.asyncio
async def test_RUO_046_senza_tavolozza_o_con_menu_chiuso(clean_db, monkeypatch):
    # RUO-046
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    cmd = _comando(s, monkeypatch)
    u = s.utente()
    await cmd.colore.callback(cmd, s.interazione(u), "1000", False)
    u.add_roles.assert_not_awaited()
    s2, m = await _tavolozza(clean_db, monkeypatch)
    await s2.repo.update_menu(m, behavior="lock")
    u2 = s2.utente()
    await cmd.colore.callback(cmd, s2.interazione(u2), "1000", False)
    u2.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_046_solo_un_menu_unique_puo_essere_tavolozza(clean_db, monkeypatch):
    # RUO-046
    s = _Scena(clean_db, monkeypatch, comportamento="normal")
    m = await s.menu()
    cmd = _comando(s, monkeypatch)
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.colori.callback(cmd, i, m, True)
    assert (await s.repo.get_menu(m)).colori is False


@pytest.mark.asyncio
async def test_RUO_046_completamento_massimo_25(clean_db, monkeypatch):
    # RUO-046
    s = _Scena(clean_db, monkeypatch, comportamento="unique")
    for rid in range(2000, 2040):
        s.ruoli[rid] = fake_role(role_id=rid, name=f"Colore {rid}", position=1)
    m = await s.menu(opzioni=())
    for rid in range(2000, 2030):
        await s.repo.add_option(m, rid, None, f"Colore {rid}")
    await RuoliExtraRepository(lambda: clean_db).imposta_colori(m, 1, True)
    monkeypatch.setattr(rx, "role_menu_repo", s.repo)
    i = fake_interaction(guild=s.guild)
    scelte = await rx._completa_colori(i, "")
    assert len(scelte) == 25
    assert len(await rx._completa_colori(i, "2029")) == 1


# ------------------------------------------------------------------ RUO-047
def test_RUO_047_solo_chi_ha_avviato_e_con_tempo_massimo():
    # RUO-047
    vista = CreazioneGuidata(MagicMock(), fake_member(user_id=1), "it")
    assert vista.timeout == 600
    assert vista.stato.autore_id == 1


@pytest.mark.asyncio
async def test_RUO_047_un_altro_utente_o_senza_permesso_viene_respinto():
    # RUO-047
    vista = CreazioneGuidata(MagicMock(), fake_member(user_id=1), "it")
    altro = fake_member(user_id=2, guild_permissions=discord.Permissions(manage_guild=True))
    i = fake_interaction(user=altro)
    assert await vista.autorizza(i) is False
    senza = fake_member(user_id=1)  # è lui, ma non gestisce più il server
    assert await vista.autorizza(fake_interaction(user=senza)) is False
    lui = fake_member(user_id=1, guild_permissions=discord.Permissions(manage_guild=True))
    assert await vista.autorizza(fake_interaction(user=lui)) is True


@pytest.mark.asyncio
async def test_RUO_047_i_componenti_di_ogni_passo():
    # RUO-047
    vista = CreazioneGuidata(MagicMock(), fake_member(user_id=1), "it")
    vista.disegna()
    assert isinstance(vista.children[0], discord.ui.Select)
    vista.stato.modalita, vista.stato.titolo = "button", "T"
    vista.disegna()
    assert isinstance(vista.children[0], discord.ui.ChannelSelect)
    vista.stato.canale_id = 700
    vista.disegna()
    assert isinstance(vista.children[0], discord.ui.RoleSelect)
    assert vista.children[0].max_values == 25


@pytest.mark.asyncio
async def test_RUO_047_crea_il_menu_e_pubblica(clean_db, monkeypatch):
    # RUO-047
    s = _Scena(clean_db, monkeypatch)
    cmd = _comando(s, monkeypatch)
    staff = _staff(s)
    stato = StatoGuidato(autore_id=1, modalita="button", titolo="Giochi", descrizione="d", canale_id=700,
                         ruoli=[1000, 1001], emoji=["🎮", None], emoji_fatte=True)
    s.canale.__class__ = discord.TextChannel
    esito = await cmd.crea_menu_guidato(s.guild, staff, stato)
    menu_ids = [m.id for m in await s.repo.list_menus_for_guild(1)]
    assert len(menu_ids) == 1, esito
    assert "Menu creato" in esito
    assert {o.role_id for o in await s.repo.get_options(menu_ids[0])} == {1000, 1001}


@pytest.mark.asyncio
async def test_RUO_047_un_ruolo_pericoloso_annulla_tutto(clean_db, monkeypatch):
    # RUO-047: il menu non resta a metà
    s = _Scena(clean_db, monkeypatch)
    s.ruoli[1001].permissions = discord.Permissions(kick_members=True)
    cmd = _comando(s, monkeypatch)
    stato = StatoGuidato(autore_id=1, modalita="select", titolo="T", canale_id=700, ruoli=[1000, 1001], emoji=[None, None], emoji_fatte=True)
    s.canale.__class__ = discord.TextChannel
    esito = await cmd.crea_menu_guidato(s.guild, _staff(s), stato)
    assert "kick_members" in esito
    assert await s.repo.list_menus_for_guild(1) == []


# ------------------------------------------------------------------ RUO-045
async def _scena_personale(clean_db, monkeypatch, concesso=True):
    s = _Scena(clean_db, monkeypatch)
    cmd = _comando(s, monkeypatch)
    repo = RuoliExtraRepository(lambda: clean_db)
    nuovo = fake_role(role_id=500, name="x", position=1)
    s.guild.create_role = AsyncMock(return_value=nuovo)
    s.guild.roles = [fake_role(role_id=i) for i in range(10)]
    u = s.utente()
    u.roles = []
    if concesso:
        assert await repo.concedi_ruolo_personale(1, 50, 1) is None
    return s, cmd, repo, nuovo, u


@pytest.mark.asyncio
async def test_RUO_045_senza_permesso_dello_staff_niente(clean_db, monkeypatch):
    # RUO-045
    s, cmd, repo, nuovo, u = await _scena_personale(clean_db, monkeypatch, concesso=False)
    await cmd.ruolo_mio.callback(cmd, s.interazione(u), "Nome", "", False)
    s.guild.create_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_045_ruolo_creato_con_permessi_vuoti_sotto_il_bot(clean_db, monkeypatch):
    # RUO-045
    s, cmd, repo, nuovo, u = await _scena_personale(clean_db, monkeypatch)
    i = s.interazione(u)
    await cmd.ruolo_mio.callback(cmd, i, "@everyone <@&5> Volpe​", "#C24A3A", False)
    kw = s.guild.create_role.await_args.kwargs
    assert kw["permissions"] == discord.Permissions.none()
    assert kw["name"] == "everyone Volpe" and kw["colour"].value == 0xC24A3A
    assert kw["hoist"] is False and kw["mentionable"] is False
    nuovo.edit.assert_awaited_once()
    assert nuovo.edit.await_args.kwargs["position"] == 49  # sotto il ruolo del bot (50)
    u.add_roles.assert_awaited_once()
    assert (await repo.ruolo_personale(1, 50))["role_id"] == 500


@pytest.mark.asyncio
async def test_RUO_045_pausa_tra_le_modifiche(clean_db, monkeypatch):
    # RUO-045
    s, cmd, repo, nuovo, u = await _scena_personale(clean_db, monkeypatch)
    await cmd.ruolo_mio.callback(cmd, s.interazione(u), "Uno", "", False)
    s.guild.get_role.side_effect = lambda rid: nuovo if rid == 500 else s.ruoli.get(rid)
    nuovo.edit.reset_mock()
    i = s.interazione(u)
    await cmd.ruolo_mio.callback(cmd, i, "Due", "", False)
    assert s.guild.create_role.await_count == 1
    nuovo.edit.assert_not_awaited()
    assert "secondi" in i.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_RUO_045_modifica_rimette_i_permessi_a_zero(clean_db, monkeypatch):
    # RUO-045: anche se qualcuno aveva dato permessi al ruolo
    s, cmd, repo, nuovo, u = await _scena_personale(clean_db, monkeypatch)
    await repo.segna_ruolo_personale(1, 50, 500, discord.utils.utcnow() - __import__("datetime").timedelta(hours=1))
    s.guild.get_role.side_effect = lambda rid: nuovo if rid == 500 else s.ruoli.get(rid)
    nuovo.permissions = discord.Permissions(administrator=True)
    i = s.interazione(u)
    await cmd.ruolo_mio.callback(cmd, i, "Nuovo", "", False)
    assert nuovo.edit.await_args.kwargs["permissions"] == discord.Permissions.none()
    u.add_roles.assert_not_awaited()  # con permessi veri check_role_assignable non lo lascia dare
    assert "administrator" in i.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_RUO_045_nome_e_colore_non_validi(clean_db, monkeypatch):
    # RUO-045
    s, cmd, repo, nuovo, u = await _scena_personale(clean_db, monkeypatch)
    for nome, colore in (("<@123>", ""), ("ok", "rosso")):
        i = s.interazione(u)
        await cmd.ruolo_mio.callback(cmd, i, nome, colore, False)
    s.guild.create_role.assert_not_awaited()
    assert (await repo.ruolo_personale(1, 50))["ultima_modifica"] is None  # il turno non si consuma


@pytest.mark.asyncio
async def test_RUO_045_tetto_250(clean_db, monkeypatch):
    # RUO-045
    s, cmd, repo, nuovo, u = await _scena_personale(clean_db, monkeypatch)
    await clean_db.execute(
        "INSERT INTO ruoli_personali (guild_id, user_id, role_id, concesso_da) SELECT 1, g, g, 1 FROM generate_series(1000, 1248) g"
    )  # 249 con ruolo + quello di prova (50) = 250 righe
    assert await repo.concedi_ruolo_personale(1, 51, 1) is not None  # il 251° permesso non si concede
    await clean_db.execute("INSERT INTO ruoli_personali (guild_id, user_id, role_id, concesso_da) VALUES (1, 9999, 9999, 1)")
    assert await repo.conta_ruoli_personali(1) == 250
    i = s.interazione(u)
    await cmd.ruolo_mio.callback(cmd, i, "Nome", "", False)
    s.guild.create_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_045_revoca_cancella_il_ruolo(clean_db, monkeypatch):
    # RUO-045
    s, cmd, repo, nuovo, u = await _scena_personale(clean_db, monkeypatch)
    await repo.segna_ruolo_personale(1, 50, 500, discord.utils.utcnow())
    s.guild.get_role.side_effect = lambda rid: nuovo if rid == 500 else s.ruoli.get(rid)
    membro = fake_member(user_id=50, name="m")
    await cmd.personale.callback(cmd, fake_interaction(guild=s.guild, user=_staff(s)), membro, True)
    nuovo.delete.assert_awaited_once()
    assert await repo.ruolo_personale(1, 50) is None


@pytest.mark.asyncio
async def test_RUO_045_chi_esce_perde_il_ruolo(clean_db, monkeypatch):
    # RUO-045
    s, cmd, repo, nuovo, u = await _scena_personale(clean_db, monkeypatch)
    await repo.segna_ruolo_personale(1, 50, 500, discord.utils.utcnow())
    s.guild.get_role.side_effect = lambda rid: nuovo if rid == 500 else s.ruoli.get(rid)
    u.guild = s.guild
    await cmd.on_member_remove(u)
    nuovo.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_RUO_045_prenota_modifica_e_atomica(clean_db):
    # RUO-045: due richieste insieme, una sola passa
    import asyncio
    from datetime import datetime, timezone

    repo = RuoliExtraRepository(lambda: clean_db)
    await repo.concedi_ruolo_personale(1, 50, 1)
    ora = datetime.now(timezone.utc)
    esiti = await asyncio.gather(*(repo.prenota_modifica(1, 50, ora, 300) for _ in range(5)))
    assert esiti.count(True) == 1


# ------------------------------------------------------------------ RUO-012
@pytest.mark.asyncio
async def test_RUO_012_massimo_dieci_immagini_anche_in_parallelo(clean_db):
    # RUO-012
    import asyncio

    repo = RuoliExtraRepository(lambda: clean_db)
    esiti = await asyncio.gather(*(repo.aggiungi_immagine_benvenuto(1, b"x", 1) for _ in range(14)))
    assert sum(e is not None for e in esiti) == 10
    assert len(await repo.id_immagini_benvenuto(1)) == 10
    assert await repo.aggiungi_immagine_benvenuto(2, b"y", 1) is not None  # un altro server ha i suoi 10


@pytest.mark.asyncio
async def test_RUO_012_si_salva_solo_la_copia_ricodificata(clean_db, monkeypatch):
    # RUO-012
    s = _Scena(clean_db, monkeypatch)
    cmd = _comando(s, monkeypatch)
    originale = _png(3000, 2000)
    allegato = MagicMock(spec=discord.Attachment)
    allegato.size = len(originale)
    allegato.read = AsyncMock(return_value=originale)
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.immagini.callback(cmd, i, "aggiungi", allegato, None)
    repo = RuoliExtraRepository(lambda: clean_db)
    [iid] = await repo.id_immagini_benvenuto(1)
    salvata = await repo.immagine_benvenuto(1, iid)
    assert salvata != originale and Image.open(io.BytesIO(salvata)).format == "JPEG"
    # un file che non è un'immagine non entra
    falso = MagicMock(spec=discord.Attachment)
    falso.size = 5
    falso.read = AsyncMock(return_value=b"MZ\x90\x00 exe")
    await cmd.immagini.callback(cmd, fake_interaction(guild=s.guild, user=_staff(s)), "aggiungi", falso, None)
    assert len(await repo.id_immagini_benvenuto(1)) == 1


@pytest.mark.asyncio
async def test_RUO_012_elenco_e_togli(clean_db, monkeypatch):
    # RUO-012
    s = _Scena(clean_db, monkeypatch)
    cmd = _comando(s, monkeypatch)
    repo = RuoliExtraRepository(lambda: clean_db)
    iid = await repo.aggiungi_immagine_benvenuto(1, b"x", 1)
    i = fake_interaction(guild=s.guild, user=_staff(s))
    await cmd.immagini.callback(cmd, i, "elenco", None, None)
    assert str(iid) in i.response.send_message.await_args.args[0]
    await cmd.immagini.callback(cmd, fake_interaction(guild=s.guild, user=_staff(s)), "togli", None, iid + 1)  # un altro numero: niente
    assert len(await repo.id_immagini_benvenuto(1)) == 1
    await cmd.immagini.callback(cmd, fake_interaction(guild=s.guild, user=_staff(s)), "togli", None, iid)
    assert await repo.id_immagini_benvenuto(1) == []


@pytest.mark.asyncio
async def test_RUO_012_il_benvenuto_sceglie_a_caso_e_usa_la_copia(clean_db, monkeypatch):
    # RUO-012
    import cogs.utility.greetings as gr
    from core.repositories.greetings_repo import GreetingsRepository

    gr_repo = GreetingsRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(gr, "greetings_repo", gr_repo)
    repo = RuoliExtraRepository(lambda: clean_db)
    for dati in (b"AAA", b"BBB", b"CCC"):
        await repo.aggiungi_immagine_benvenuto(1, dati, 1)
    visti = {await gr._immagine_a_caso(1) for _ in range(60)}
    assert visti == {b"AAA", b"BBB", b"CCC"}
    assert await gr._immagine_a_caso(2) is None
    # biglietto spento: l'immagine si allega così com'è
    config = MagicMock(welcome_image_enabled=False)
    membro = fake_member(user_id=5)
    membro.guild = MagicMock(id=1)
    file = await gr._file_benvenuto(config, membro)
    assert file is not None and file.filename == "benvenuto.jpg"
    # biglietto acceso: l'immagine fa da sfondo
    catturato = {}
    monkeypatch.setattr(gr, "render_welcome_image", lambda dati, avatar, sfondo: catturato.setdefault("sfondo", sfondo) or b"png")
    config = MagicMock(
        welcome_image_enabled=True, welcome_image_has_background=False, welcome_image_title="", welcome_image_template="x",
        welcome_image_shape="tondo", welcome_image_color="", welcome_image_opacity=65, welcome_image_text="",
        welcome_image_align="sinistra", welcome_image_name_color="",
    )
    membro.guild.member_count = 3
    membro.display_avatar.replace.return_value.read = AsyncMock(return_value=b"")
    await gr._file_benvenuto(config, membro)
    assert catturato["sfondo"] in (b"AAA", b"BBB", b"CCC")


@pytest.mark.asyncio
async def test_RUO_012_senza_immagini_il_benvenuto_resta_com_era(clean_db, monkeypatch):
    # RUO-012
    import cogs.utility.greetings as gr
    from core.repositories.greetings_repo import GreetingsRepository

    monkeypatch.setattr(gr, "greetings_repo", GreetingsRepository(pool_provider=lambda: clean_db))
    membro = fake_member(user_id=5)
    membro.guild = MagicMock(id=1)
    assert await gr._file_benvenuto(MagicMock(welcome_image_enabled=False), membro) is None

"""
tests/test_role_menu_modalita.py
================================
NF-14 / M 10.8 (#85, #66): comportamento dei menu di ruoli (unique, verify, drop, reversed,
binding, temp, lock), ruoli ammessi o esclusi; RUO-050/051 (#123): elenco dei menu con gli ID
e modifica di titolo e descrizione di un menu già pubblicato.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.role_menus as rm
from cogs.utility.role_menus import RoleMenuCog
from core.repositories.role_menu_repo import RoleMenuRepository
from core.role_menu_logic import (
    COMPORTAMENTI,
    Decisione,
    comportamento_ammesso,
    decidi_azione,
    decidi_selezione,
    membro_ammesso,
)
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
)
from tests.support.percorsi import comando_nel_gruppo

MENU = {1, 2, 3}


def _d(comportamento, ruolo=1, membro=(), attiva=True, reazione=False, toggle=True, temp=None):
    return decidi_azione(
        comportamento, attiva=attiva, via_reazione=reazione, ruolo_id=ruolo, ruoli_menu=MENU,
        ruoli_membro=set(membro), toggle=toggle, temp_secondi=temp,
    )


# ---------------------------------------------------------------- logica pura
def test_normal_prende_e_toglie():
    assert _d("normal") == Decisione(aggiungi=(1,))
    assert _d("normal", membro={1}) == Decisione(togli=(1,))
    assert _d("normal", membro={1}, toggle=False).rifiuto
    assert _d("normal", membro={1}, reazione=True) == Decisione()
    assert _d("normal", membro={1}, attiva=False, reazione=True) == Decisione(togli=(1,))
    assert _d("normal", membro={1}, attiva=False, reazione=True, toggle=False) == Decisione()


def test_unique_toglie_gli_altri_del_menu():
    assert _d("unique", membro={2, 9}) == Decisione(aggiungi=(1,), togli=(2,))  # il 9 non è del menu
    assert _d("unique", membro={1}) == Decisione(togli=(1,))


def test_verify_non_toglie_mai():
    assert _d("verify") == Decisione(aggiungi=(1,))
    assert _d("verify", membro={1}).rifiuto
    assert _d("verify", membro={1}, attiva=False, reazione=True) == Decisione()


def test_drop_toglie_soltanto():
    assert _d("drop", membro={1}) == Decisione(togli=(1,))
    assert _d("drop").rifiuto and not _d("drop").aggiungi
    assert _d("drop", attiva=False, reazione=True) == Decisione()


def test_reversed_inverte_la_reazione():
    assert _d("reversed", membro={1}, reazione=True) == Decisione(togli=(1,))
    assert _d("reversed", attiva=False, reazione=True) == Decisione(aggiungi=(1,))
    assert _d("reversed", membro={1}, attiva=False, reazione=True) == Decisione()


def test_binding_una_scelta_per_sempre():
    assert _d("binding") == Decisione(aggiungi=(1,))
    assert _d("binding", membro={2}).rifiuto
    assert _d("binding", membro={1}).rifiuto
    assert _d("binding", membro={1}, attiva=False, reazione=True) == Decisione()


def test_temp_porta_la_durata():
    assert _d("temp", temp=600) == Decisione(aggiungi=(1,), temporaneo_secondi=600)
    assert _d("temp", membro={1}, temp=600) == Decisione(togli=(1,))


def test_lock_blocca_tutto():
    for attiva in (True, False):
        assert _d("lock", attiva=attiva, reazione=True).rifiuto


def test_selezione_per_comportamento():
    kw = dict(ruoli_menu=MENU, ruoli_membro={1}, scelti={2})
    assert decidi_selezione("normal", **kw) == Decisione(aggiungi=(2,), togli=(1,))
    assert decidi_selezione("verify", **kw) == Decisione(aggiungi=(2,))
    assert decidi_selezione("binding", **kw).rifiuto
    assert decidi_selezione("lock", **kw).rifiuto
    assert decidi_selezione("unique", **dict(kw, scelti={2, 3})).rifiuto
    assert decidi_selezione("temp", **dict(kw, scelti={2}), temp_secondi=60).temporaneo_secondi == 60


def test_comportamenti_ammessi_per_modalita():
    assert all(comportamento_ammesso("reaction", c) for c in COMPORTAMENTI)
    assert not comportamento_ammesso("button", "reversed")
    assert not comportamento_ammesso("select", "drop") and not comportamento_ammesso("select", "reversed")
    assert not comportamento_ammesso("button", "inventato")


def test_accesso_ammessi_ed_esclusi():
    assert membro_ammesso([], [], {1}) is None
    assert membro_ammesso([5], [], {1}) is not None
    assert membro_ammesso([5], [], {5}) is None
    assert membro_ammesso([5], [6], {5, 6}) is not None  # l'esclusione vince


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return RoleMenuRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_menu_nuovo_e_normale_e_poi_cambia(repo):
    mid = await repo.create_menu(1, 700, "button", True, None, "T", "")
    menu = await repo.get_menu(mid)
    assert menu.behavior == "normal" and menu.allowed_role_ids == () and menu.temp_seconds is None
    assert await repo.update_menu(mid, behavior="temp", temp_seconds=600, title="Nuovo") is True
    await repo.set_access_lists(mid, [5], [6, 7])
    menu = await repo.get_menu(mid)
    assert (menu.behavior, menu.temp_seconds, menu.title) == ("temp", 600, "Nuovo")
    assert menu.allowed_role_ids == (5,) and menu.excluded_role_ids == (6, 7)


@pytest.mark.asyncio
async def test_update_rifiuta_campi_sconosciuti(repo):
    mid = await repo.create_menu(1, 700, "button", True, None, "T", "")
    with pytest.raises(ValueError):
        await repo.update_menu(mid, guild_id=5)


@pytest.mark.asyncio
async def test_elenco_dei_menu_del_server(repo):
    a = await repo.create_menu(1, 700, "button", True, None, "A", "")
    await repo.create_menu(2, 700, "button", True, None, "B", "")
    assert [m.id for m in await repo.list_menus_for_guild(1)] == [a]


# -------------------------------------------------------------------------- cog
class _Scena:
    def __init__(self, clean_db, monkeypatch, mode="button", comportamento="normal", toggle=True, temp=None):
        self.repo = RoleMenuRepository(pool_provider=lambda: clean_db)
        monkeypatch.setattr(rm, "role_menu_repo", self.repo)
        monkeypatch.setattr(rm.db, "is_module_active_for_guild", AsyncMock(return_value=True))
        self.scheduler = MagicMock(schedule=AsyncMock(return_value=1), cancel=AsyncMock(), list_pending_for_user=AsyncMock(return_value=[]))
        monkeypatch.setattr(rm, "scheduler", self.scheduler)
        bot_member = fake_member(user_id=999, name="Yokai Bot", bot=True)
        bot_member.top_role = fake_role(role_id=100, name="Bot", position=50)
        self.guild = fake_guild(guild_id=1, owner_id=1, me=bot_member)
        self.ruoli = {rid: fake_role(role_id=rid, name=f"R{rid}", position=1) for rid in range(1000, 1010)}
        self.guild.get_role.side_effect = self.ruoli.get
        self.canale = fake_text_channel(channel_id=700)
        self.messaggio = fake_message(message_id=555)
        self.messaggio.reactions = []
        self.canale.send.return_value = self.messaggio
        self.canale.fetch_message = AsyncMock(return_value=self.messaggio)
        self.guild.get_channel.return_value = self.canale
        self.bot = MagicMock()
        self.bot.get_emoji.return_value = None
        self.cog = RoleMenuCog(self.bot)
        self.mode, self.comportamento, self.toggle, self.temp = mode, comportamento, toggle, temp

    async def menu(self, opzioni=(1000, 1001, 1002)):
        self.menu_id = await self.repo.create_menu(
            guild_id=1, channel_id=700, mode=self.mode, toggle=self.toggle, max_selectable=None,
            title="Menu", description="", behavior=self.comportamento, temp_seconds=self.temp,
        )
        for rid in opzioni:
            await self.repo.add_option(self.menu_id, rid, "🎮", f"L{rid}")
        return self.menu_id

    def utente(self, *ruoli_id):
        ruoli = [self.ruoli[r] for r in ruoli_id]
        u = fake_member(user_id=50, roles=ruoli)
        u.guild = self.guild
        u.add_roles = AsyncMock()
        u.remove_roles = AsyncMock()
        return u

    def interazione(self, utente):
        self.guild.fetch_member = AsyncMock(return_value=utente)
        return fake_interaction(guild=self.guild, user=utente, channel=self.canale)


def _ruoli_di(chiamata):
    return {r.id for r in chiamata.args}


@pytest.mark.asyncio
async def test_bottone_unique_da_il_nuovo_e_toglie_l_altro(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, comportamento="unique")
    await s.menu()
    u = s.utente(1001)
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    assert _ruoli_di(u.add_roles.await_args) == {1000}
    assert _ruoli_di(u.remove_roles.await_args) == {1001}


@pytest.mark.asyncio
async def test_bottone_verify_non_toglie(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, comportamento="verify")
    await s.menu()
    u = s.utente(1000)
    i = s.interazione(u)
    await s.cog._handle_button_click(i, s.menu_id, 1000)
    u.remove_roles.assert_not_awaited()
    assert "non si" in i.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_bottone_drop_toglie_ma_non_da(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, comportamento="drop")
    await s.menu()
    u = s.utente()
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    u.add_roles.assert_not_awaited()
    u2 = s.utente(1000)
    await s.cog._handle_button_click(s.interazione(u2), s.menu_id, 1000)
    u2.remove_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_bottone_binding_blocca_il_cambio(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, comportamento="binding")
    await s.menu()
    u = s.utente(1001)
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    u.add_roles.assert_not_awaited()
    u.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_bottone_lock(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, comportamento="lock")
    await s.menu()
    u = s.utente()
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    u.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_bottone_temp_programma_la_rimozione(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, comportamento="temp", temp=900)
    await s.menu()
    u = s.utente()
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    u.add_roles.assert_awaited_once()
    s.scheduler.schedule.assert_awaited_once()
    assert s.scheduler.schedule.await_args.args[2] == rm.ROLEMENU_TEMP_ACTION_TYPE
    assert s.scheduler.schedule.await_args.args[4] == {"role_id": 1000}


@pytest.mark.asyncio
async def test_ruoli_ammessi_ed_esclusi(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.repo.set_access_lists(s.menu_id, [1005], [1006])
    senza = s.utente()
    i = s.interazione(senza)
    await s.cog._handle_button_click(i, s.menu_id, 1000)
    senza.add_roles.assert_not_awaited()
    assert "riservato" in i.followup.send.await_args.args[0]
    escluso = s.utente(1005, 1006)
    await s.cog._handle_button_click(s.interazione(escluso), s.menu_id, 1000)
    escluso.add_roles.assert_not_awaited()
    ok = s.utente(1005)
    await s.cog._handle_button_click(s.interazione(ok), s.menu_id, 1000)
    ok.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_select_verify_non_toglie(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="select", comportamento="verify")
    await s.menu()
    u = s.utente(1001)
    sel = MagicMock(values=["1000"])
    await s.cog._handle_select(s.interazione(u), s.menu_id, sel)
    u.remove_roles.assert_not_awaited()
    assert _ruoli_di(u.add_roles.await_args) == {1000}


def _payload(user_id=50, emoji="🎮", member=None):
    p = MagicMock()
    p.guild_id, p.message_id, p.user_id = 1, 555, user_id
    p.emoji = emoji
    p.member = member
    return p


@pytest.mark.asyncio
async def test_reazione_reversed_toglie_quando_si_mette(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="reaction", comportamento="reversed")
    mid = await s.menu()
    await s.repo.set_menu_message(mid, 555)
    monkeypatch.setattr(rm.blacklist_repo, "is_user_blacklisted", AsyncMock(return_value=False))
    s.bot.get_guild.return_value = s.guild
    u = s.utente(1000)
    s.guild.get_member = lambda uid: u
    s.guild.fetch_member = AsyncMock(return_value=u)
    await s.cog.on_raw_reaction_add(_payload(member=u))
    u.remove_roles.assert_awaited_once()
    u2 = s.utente()
    s.guild.get_member = lambda uid: u2
    s.guild.fetch_member = AsyncMock(return_value=u2)
    await s.cog.on_raw_reaction_remove(_payload())
    u2.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_reazione_verify_tolta_non_toglie_il_ruolo(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="reaction", comportamento="verify")
    mid = await s.menu()
    await s.repo.set_menu_message(mid, 555)
    s.bot.get_guild.return_value = s.guild
    u = s.utente(1000)
    s.guild.get_member = lambda uid: u
    await s.cog.on_raw_reaction_remove(_payload())
    u.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_temp_toglie_il_ruolo_se_il_membro_c_e_ancora(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    u = s.utente(1000)
    s.bot.get_guild.return_value = s.guild
    s.guild.get_member = lambda uid: u
    await s.cog.handle_rolemenu_temp(1, 50, {"role_id": 1000})
    u.remove_roles.assert_awaited_once()
    u2 = s.utente()
    s.guild.get_member = lambda uid: u2
    await s.cog.handle_rolemenu_temp(1, 50, {"role_id": 1000})
    u2.remove_roles.assert_not_awaited()


# ---------------------------------------------------------------------- comandi
@pytest.mark.asyncio
async def test_crea_rifiuta_comportamento_incompatibile(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    i = s.interazione(s.utente())
    mode = MagicMock(value="button")
    await s.cog.create_cmd.callback(s.cog, i, title="T", mode=mode, comportamento="reversed")
    assert await s.repo.list_menus_for_guild(1) == []
    assert "reazion" in i.response.send_message.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_crea_temp_senza_durata_rifiutato(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    i = s.interazione(s.utente())
    await s.cog.create_cmd.callback(s.cog, i, title="T", mode=MagicMock(value="button"), comportamento="temp")
    assert await s.repo.list_menus_for_guild(1) == []


@pytest.mark.asyncio
async def test_crea_unique_in_tendina_fissa_un_solo_valore(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    i = s.interazione(s.utente())
    await s.cog.create_cmd.callback(s.cog, i, title="T", mode=MagicMock(value="select"), comportamento="unique")
    menu = (await s.repo.list_menus_for_guild(1))[0]
    assert menu.behavior == "unique" and menu.max_selectable == 1


@pytest.mark.asyncio
async def test_elenco_mostra_id_canale_e_opzioni(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.list_cmd.callback(s.cog, i)
    testo = i.response.send_message.await_args.kwargs["embed"].description
    assert f"`{s.menu_id}`" in testo and "<#700>" in testo and "3" in testo


@pytest.mark.asyncio
async def test_modifica_titolo_ripubblica_il_messaggio_e_poi_salva(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, titolo="Nuovo titolo")
    assert (await s.repo.get_menu(s.menu_id)).title == "Nuovo titolo"
    s.canale.send.assert_awaited_once()
    assert s.canale.send.await_args.kwargs["embed"].title == "Nuovo titolo"  # il messaggio porta i valori NUOVI


@pytest.mark.asyncio
async def test_modifica_comportamento_si_vede_nel_messaggio(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, comportamento="verify")
    assert "verify" in s.canale.send.await_args.kwargs["embed"].footer.text
    assert (await s.repo.get_menu(s.menu_id)).behavior == "verify"


@pytest.mark.asyncio
async def test_modifica_durata_su_menu_non_temp_e_rifiutata(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, durata_minuti=10)
    assert "temp" in i.response.send_message.await_args.args[0]
    assert (await s.repo.get_menu(s.menu_id)).temp_seconds is None
    s.canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_modifica_con_pubblicazione_fallita_non_salva(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    s.canale.send.side_effect = discord.HTTPException(MagicMock(status=400, reason="x"), "no")
    i = s.interazione(s.utente())
    await s.cog.edit_cmd.callback(s.cog, i, menu_id=s.menu_id, titolo="Nuovo titolo")
    assert (await s.repo.get_menu(s.menu_id)).title == "Menu"


@pytest.mark.asyncio
async def test_accesso_aggiunge_e_toglie_ruoli(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    i = s.interazione(s.utente())
    await s.cog.access_cmd.callback(s.cog, i, menu_id=s.menu_id, ruolo=s.ruoli[1005], elenco="ammesso", azione="aggiungi")
    await s.cog.access_cmd.callback(s.cog, i, menu_id=s.menu_id, ruolo=s.ruoli[1006], elenco="escluso", azione="aggiungi")
    menu = await s.repo.get_menu(s.menu_id)
    assert menu.allowed_role_ids == (1005,) and menu.excluded_role_ids == (1006,)
    await s.cog.access_cmd.callback(s.cog, i, menu_id=s.menu_id, ruolo=s.ruoli[1005], elenco="ammesso", azione="togli")
    assert (await s.repo.get_menu(s.menu_id)).allowed_role_ids == ()


@pytest.mark.asyncio
async def test_albero_dei_comandi_nuovi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    from core.database import db

    await db.connect()
    try:
        await rm.setup(bot)
    finally:
        await db.close()
    for nome in ("menu-elenco", "menu-modifica", "menu-accesso"):
        assert comando_nel_gruppo("gestione", f"ruoli {nome}") is not None
    crea = {o["name"]: o for o in comando_nel_gruppo("gestione", "ruoli menu-crea").to_dict(bot.tree)["options"]}
    assert len(crea["comportamento"]["choices"]) == len(COMPORTAMENTI)


@pytest.mark.asyncio
async def test_due_clic_insieme_su_binding_danno_un_solo_ruolo(clean_db, monkeypatch):
    """L'interazione porta i ruoli di prima del clic: senza blocco per membro e rilettura
    entrambi i clic vedono 'nessun ruolo' e se ne prendono due."""
    s = _Scena(clean_db, monkeypatch, comportamento="binding")
    await s.menu()
    u = s.utente()
    vivi = []

    async def dai(*ruoli, reason=None):
        await asyncio.sleep(0.01)
        vivi.extend(ruoli)
        u.roles = list(vivi)

    u.add_roles = AsyncMock(side_effect=dai)
    stale = [s.interazione(u), s.interazione(u)]
    await asyncio.gather(
        s.cog._handle_button_click(stale[0], s.menu_id, 1000),
        s.cog._handle_button_click(stale[1], s.menu_id, 1001),
    )
    assert len(vivi) == 1


@pytest.mark.asyncio
async def test_ruolo_a_tempo_ripreso_annulla_la_vecchia_rimozione(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, comportamento="temp", temp=600)
    await s.menu()
    s.scheduler.list_pending_for_user.return_value = [
        {"id": 7, "guild_id": 1, "payload": {"role_id": 1000}},
        {"id": 8, "guild_id": 1, "payload": {"role_id": 1001}},
    ]
    u = s.utente()
    await s.cog._handle_button_click(s.interazione(u), s.menu_id, 1000)
    s.scheduler.cancel.assert_awaited_once_with(7)
    s.scheduler.schedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_l_istantanea_vecchia_dell_interazione_viene_riletta(clean_db, monkeypatch):
    """interaction.user porta i ruoli di prima; quelli veri (fetch_member) hanno già una scelta binding."""
    s = _Scena(clean_db, monkeypatch, comportamento="binding")
    await s.menu()
    vivo = s.utente(1000)
    vecchio = fake_member(user_id=50, roles=[])
    vecchio.guild = s.guild
    vecchio.add_roles = AsyncMock()
    s.guild.fetch_member = AsyncMock(return_value=vivo)
    i = fake_interaction(guild=s.guild, user=vecchio, channel=s.canale)
    await s.cog._handle_button_click(i, s.menu_id, 1001)
    vivo.add_roles.assert_not_awaited()
    vecchio.add_roles.assert_not_awaited()
    assert "definitiva" in i.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_si_prenota_la_risposta_prima_delle_chiamate_a_discord(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    eventi = []
    u = s.utente()
    i = s.interazione(u)
    i.response.defer = AsyncMock(side_effect=lambda **k: eventi.append("defer"))

    async def rileggi(_id):
        eventi.append("fetch_member")
        return u

    s.guild.fetch_member = AsyncMock(side_effect=rileggi)
    u.add_roles = AsyncMock(side_effect=lambda *a, **k: eventi.append("add_roles"))
    await s.cog._handle_button_click(i, s.menu_id, 1000)
    assert eventi == ["defer", "fetch_member", "add_roles"]
    i.response.send_message.assert_not_awaited()
    i.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_la_tendina_prenota_la_risposta_per_prima(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="select")
    await s.menu()
    eventi = []
    u = s.utente()
    i = s.interazione(u)
    i.response.defer = AsyncMock(side_effect=lambda **k: eventi.append("defer"))
    s.guild.fetch_member = AsyncMock(side_effect=lambda _id: (eventi.append("fetch_member"), u)[1])
    select = MagicMock()
    select.values = ["1000"]
    await s.cog._handle_select(i, s.menu_id, select)
    assert eventi[:2] == ["defer", "fetch_member"]
    i.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_accesso_ha_un_tetto_di_20_ruoli(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.repo.set_access_lists(s.menu_id, list(range(2000, 2020)), [])
    i = s.interazione(s.utente())
    await s.cog.access_cmd.callback(s.cog, i, menu_id=s.menu_id, ruolo=s.ruoli[1005], elenco="ammesso", azione="aggiungi")
    assert len((await s.repo.get_menu(s.menu_id)).allowed_role_ids) == 20
    assert "20" in i.response.send_message.await_args.args[0]

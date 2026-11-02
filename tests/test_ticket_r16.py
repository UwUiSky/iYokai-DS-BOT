"""
tests/test_ticket_r16.py
========================
#120 (D66), blocco T1: motivi pronti per pannello (TKT-006), menu «Apri ticket» (TKT-009),
livelli addetto/admin (TKT-045), ticket solo admin (TKT-046). Database vero; Discord finto.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.tickets.opzioni as opzioni_cog
import cogs.tickets.tickets as modulo
from core import ticket_form_logic as form
from core import ticket_logic as logica
from core.database import db
from core.repositories.ticket_form_repo import TroppiMotivi, ticket_form_repo
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

GUILD = 100
UTENTE = 20
CATEGORIA = 900


# ====================================================================
# Regole pure
# ====================================================================
def test_motivo_valido_taglia_e_rifiuta():
    assert form.motivo_valido("  Acquisto  ", " ") == ("Acquisto", None)
    assert form.motivo_valido("A" * 80, "t" * 512) == ("A" * 80, "t" * 512)
    for etichetta, testo in (("", None), ("A" * 81, None), ("A", "t" * 513)):
        with pytest.raises(form.ErroreConfigurazione):
            form.motivo_valido(etichetta, testo)


def test_il_menu_dei_motivi_sta_in_25_voci_con_altro():
    motivi = [SimpleNamespace(id=i, etichetta=f"M{i}", emoji=None) for i in range(1, 25)]
    opzioni = form.opzioni_motivi(motivi)
    assert len(opzioni) == 25 and opzioni[-1][0] == form.VALORE_ALTRO
    assert all(len(v) <= 100 and len(e) <= 100 for v, e, _ in opzioni)


def test_admin_dei_ticket_senza_ruoli_admin_vale_ogni_staff():
    # Base «addetto = come oggi»: finché nessun ruolo è admin, ogni membro dello staff può tutto.
    assert logica.e_admin_ticket(False, {1}, {1, 2}, set())
    assert not logica.e_admin_ticket(False, {3}, {1, 2}, set())  # non è staff


def test_admin_dei_ticket_con_ruoli_admin_gli_addetti_non_bastano():
    assert not logica.e_admin_ticket(False, {1}, {1, 2}, {2})
    assert logica.e_admin_ticket(False, {2}, {1, 2}, {2})
    assert logica.e_admin_ticket(True, set(), {1, 2}, {2})  # «Gestisci server» passa sempre


def test_solo_admin_lascia_nel_canale_solo_i_ruoli_admin():
    assert logica.ruoli_con_accesso([1, 2, 3], {2}, solo_admin=True) == [2]
    assert logica.ruoli_con_accesso([1, 2, 3], {2}, solo_admin=False) == [1, 2, 3]
    # Senza ruoli admin «solo admin» non toglie nessuno (resta chi ha «Gestisci server»).
    assert logica.ruoli_con_accesso([1, 2], set(), solo_admin=True) == [1, 2]


# ====================================================================
# Repository
# ====================================================================
@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    ticket_opzioni_repo._cache.clear()
    await db.set_module_active_for_guild(GUILD, modulo.MODULE_TICKETS, True)
    yield
    database_module.db._modules_cache.clear()


async def _pannello(nome="Supporto"):
    return await ticket_form_repo.crea_pannello(GUILD, nome, CATEGORIA, nome)


async def test_motivi_il_25esimo_e_rifiutato_e_le_posizioni_scorrono():
    p = await _pannello()
    for i in range(1, 25):
        await ticket_form_repo.aggiungi_motivo(p.id, f"M{i}")
    with pytest.raises(TroppiMotivi):
        await ticket_form_repo.aggiungi_motivo(p.id, "M25")
    assert await ticket_form_repo.rimuovi_motivo(p.id, 2)
    motivi = await ticket_form_repo.elenca_motivi(p.id)
    assert [m.posizione for m in motivi] == list(range(1, 24)) and motivi[1].etichetta == "M3"
    assert not await ticket_form_repo.rimuovi_motivo(p.id, 99)


async def test_eliminare_il_pannello_toglie_i_motivi(clean_db):
    p = await _pannello()
    await ticket_form_repo.aggiungi_motivo(p.id, "Acquisto", testo="Ho un problema con un acquisto")
    assert await ticket_form_repo.rimuovi_pannello(GUILD, "supporto")
    assert await clean_db.fetchval("SELECT count(*) FROM ticket_panel_motivi") == 0


async def test_livelli_dei_ruoli():
    assert await ticket_repo.ruoli_admin(GUILD) == []
    await ticket_repo.imposta_livello_ruolo(GUILD, 5, "admin")
    await ticket_repo.imposta_livello_ruolo(GUILD, 6, "addetto")
    assert await ticket_repo.ruoli_admin(GUILD) == [5]
    assert await ticket_repo.livelli_ruoli(GUILD) == {5: "admin", 6: "addetto"}
    await ticket_repo.imposta_livello_ruolo(GUILD, 5, "addetto")
    assert await ticket_repo.ruoli_admin(GUILD) == []
    await ticket_repo.togli_livello_ruolo(GUILD, 6)
    assert await ticket_repo.livelli_ruoli(GUILD) == {5: "addetto"}


async def test_solo_admin_del_ticket_e_del_pannello():
    p = await _pannello()
    await ticket_repo.create_ticket(GUILD, UTENTE, 555, ticket_number=1)
    assert not (await ticket_repo.get_ticket_by_channel(555)).solo_admin
    assert await ticket_repo.set_solo_admin(555, True)
    assert (await ticket_repo.get_ticket_by_channel(555)).solo_admin
    assert not (await ticket_opzioni_repo.opzioni(p.id)).solo_admin
    assert (await ticket_opzioni_repo.imposta(p.id, solo_admin=True)).solo_admin


# ====================================================================
# Cog
# ====================================================================
class Server:
    def __init__(self) -> None:
        self.guild = fake_guild(GUILD)
        self.guild.default_role = fake_role(role_id=GUILD, name="@everyone", position=0)
        self.categoria = create_autospec(discord.CategoryChannel, instance=True)
        self.categoria.id = CATEGORIA
        self.categoria.channels = []
        self.canali: list = []
        self.categoria.create_text_channel.side_effect = self._crea
        self.guild.get_channel.side_effect = lambda cid: self.categoria if cid == CATEGORIA else None
        self.guild.get_role.side_effect = lambda rid: fake_role(role_id=rid, name=f"r{rid}")

    async def _crea(self, name, **kwargs):
        c = fake_text_channel(1000 + len(self.canali), name)
        c.guild = self.guild
        c.kwargs = kwargs
        self.canali.append(c)
        return c

    def interazione(self, user_id=UTENTE, permessi=None, ruoli=()):
        m = fake_member(user_id, roles=list(ruoli), guild_permissions=permessi or discord.Permissions())
        m.guild = self.guild
        return fake_interaction(guild=self.guild, user=m)


@pytest.fixture
def scheduler_di_test(monkeypatch):
    monkeypatch.setattr(modulo, "scheduler", Scheduler())


async def test_pannello_con_motivi_mostra_il_menu_e_non_apre_il_ticket(scheduler_di_test):
    p = await _pannello()
    await ticket_form_repo.aggiungi_motivo(p.id, "Acquisto", testo="Problema con un acquisto")
    s = Server()
    i = s.interazione()
    await modulo.apri_da_pannello(i, p.id)
    i.response.send_message.assert_awaited_once()
    vista = i.response.send_message.await_args.kwargs["view"]
    select = vista.children[0]
    assert [o.label for o in select.options] == ["Acquisto", "Altro"]
    assert s.canali == []


async def test_scegliere_un_motivo_apre_il_ticket_con_il_testo_del_motivo(scheduler_di_test):
    p = await _pannello()
    m = await ticket_form_repo.aggiungi_motivo(p.id, "Acquisto", testo="Problema con un acquisto")
    s = Server()
    i = s.interazione()
    vista = modulo.VistaMotivi(p, await ticket_form_repo.elenca_motivi(p.id))
    vista.children[0]._values = [str(m.id)]
    await vista.children[0].callback(i)
    assert len(s.canali) == 1
    embed = s.canali[0].send.await_args.kwargs["embed"]
    assert "Problema con un acquisto" in [f.value for f in embed.fields]


async def test_scegliere_altro_apre_la_finestra_del_motivo(scheduler_di_test):
    p = await _pannello()
    await ticket_form_repo.aggiungi_motivo(p.id, "Acquisto")
    s = Server()
    i = s.interazione()
    vista = modulo.VistaMotivi(p, await ticket_form_repo.elenca_motivi(p.id))
    vista.children[0]._values = [form.VALORE_ALTRO]
    await vista.children[0].callback(i)
    i.response.send_modal.assert_awaited_once()
    assert s.canali == []


async def test_pannello_senza_motivi_si_comporta_come_prima(scheduler_di_test):
    p = await _pannello()
    s = Server()
    i = s.interazione()
    await modulo.apri_da_pannello(i, p.id)
    assert len(s.canali) == 1


async def test_solo_admin_del_pannello_nega_il_canale_agli_addetti(scheduler_di_test):
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, solo_admin=True)
    await ticket_repo.imposta_livello_ruolo(GUILD, 7, "admin")
    await db.set_guild_setting(GUILD, modulo.SETTING_SUPPORT_ROLES, [7, 8])
    s = Server()
    i = s.interazione()
    await modulo.apri_da_pannello(i, p.id)
    ruoli_nel_canale = {getattr(k, "id", None) for k in s.canali[0].kwargs["overwrites"]}
    assert 7 in ruoli_nel_canale and 8 not in ruoli_nel_canale
    assert (await ticket_repo.get_ticket_by_channel(s.canali[0].id)).solo_admin


@pytest.fixture
async def cog(monkeypatch):
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    c = bot.get_cog("TicketsCog")
    c._elimina_canale = AsyncMock()
    yield c
    await bot.close()


async def test_forceclose_con_ruoli_admin_rifiuta_l_addetto(cog):
    await ticket_repo.imposta_livello_ruolo(GUILD, 7, "admin")
    await db.set_guild_setting(GUILD, modulo.SETTING_SUPPORT_ROLES, [7, 8])
    await ticket_repo.create_ticket(GUILD, UTENTE, 200, ticket_number=1)
    s = Server()
    i = s.interazione(user_id=30, ruoli=[fake_role(role_id=8, name="addetto")])
    i.channel = fake_text_channel(200)
    await cog.forceclose.callback(cog, i, None)
    assert (await ticket_repo.get_ticket_by_channel(200)).status == "open"
    i2 = s.interazione(user_id=31, ruoli=[fake_role(role_id=7, name="admin")])
    i2.channel = fake_text_channel(200)
    await cog.forceclose.callback(cog, i2, None)
    assert (await ticket_repo.get_ticket_by_channel(200)).status == "closed"


async def test_menu_apri_ticket_esiste_con_nome_valido():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await opzioni_cog.setup(bot)
    try:
        menu = [c for c in bot.tree.get_commands(type=discord.AppCommandType.message)]
        assert [m.name for m in menu] == ["Apri ticket"]
    finally:
        await bot.close()

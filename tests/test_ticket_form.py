"""
tests/test_ticket_form.py
=========================
NF-13 (#84): pannelli multipli, modulo di domande, voto alla chiusura.

Regole pure, repository veri (clean_db) e il codice di produzione del cog
(`apri_da_pannello`, `ModuloTicket`, `BottoneVoto`). Di Discord ci sono solo i
finti fedeli di tests/support/discord_fakes.py.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.tickets.tickets as modulo
from core import ticket_form_logic as form
from core.database import db
from core.repositories.ticket_form_repo import (
    PannelloGiaEsistente,
    TroppeDomande,
    TroppiPannelli,
    ticket_form_repo,
)
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

ID_SERVER = 100
ID_UTENTE = 20
ID_CATEGORIA = 900


# ====================================================================
# Regole pure
# ====================================================================
def test_domanda_di_46_caratteri_rifiutata_e_di_45_accettata():
    with pytest.raises(form.ErroreConfigurazione):
        form.domanda_valida("x" * 46, None)
    assert form.domanda_valida("x" * 45, "  ")[1] is None


def test_segnaposto_oltre_100_rifiutato():
    with pytest.raises(form.ErroreConfigurazione):
        form.domanda_valida("Nome", "y" * 101)


def test_campi_delle_risposte_tagliati_e_sotto_il_limite_dell_embed():
    domande = [SimpleNamespace(label="D" * 300, required=True) for _ in range(5)]
    campi = form.campi_risposte(domande, ["R" * 5000] * 5)
    assert all(len(n) <= 256 and len(v) <= 1024 for n, v in campi)
    assert sum(len(n) + len(v) for n, v in campi) <= 6000


def test_risposta_facoltativa_vuota_saltata_e_obbligatoria_mancante_segnalata():
    domande = [SimpleNamespace(label="A", required=True), SimpleNamespace(label="B", required=False)]
    assert form.risposte_mancanti(domande, ["", ""]) == ["A"]
    assert form.campi_risposte(domande, ["ok", "  "]) == [("A", "ok")]


def test_bottoni_di_un_messaggio_al_massimo_25():
    assert form.righe_di_bottoni(7) == [5, 2]
    with pytest.raises(form.ErroreConfigurazione):
        form.righe_di_bottoni(26)


def test_elenco_di_pannelli_senza_doppioni():
    assert form.nomi_da_elenco("Supporto, supporto ,Candidature,,") == ["Supporto", "Candidature"]


def test_minuti_di_chiusura_automatica():
    assert form.minuti_chiusura_validi(0) is None
    assert form.minuti_chiusura_validi(60) == 60
    for fuori in (1, 4, 43201):
        with pytest.raises(form.ErroreConfigurazione):
            form.minuti_chiusura_validi(fuori)


def test_prossimo_controllo():
    adesso = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert form.prossimo_controllo(adesso - timedelta(minutes=30), adesso, 30) is None
    assert form.prossimo_controllo(adesso - timedelta(minutes=10), adesso, 30) == adesso + timedelta(minutes=20)


# ====================================================================
# Repository
# ====================================================================
@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, modulo.MODULE_TICKETS, True)
    yield
    database_module.db._modules_cache.clear()


async def _pannello(nome="Supporto", **kw):
    return await ticket_form_repo.crea_pannello(ID_SERVER, nome, ID_CATEGORIA, nome, **kw)


async def test_il_26esimo_pannello_e_rifiutato_e_il_nome_e_unico():
    for i in range(form.MAX_PANNELLI_PER_SERVER):
        await _pannello(f"P{i}")
    with pytest.raises(TroppiPannelli):
        await _pannello("P-extra")
    await ticket_form_repo.crea_pannello(ID_SERVER + 1, "P0", 1, "x")
    with pytest.raises(PannelloGiaEsistente):
        await ticket_form_repo.crea_pannello(ID_SERVER + 1, "p0", 1, "x")


async def test_la_sesta_domanda_e_rifiutata_e_le_posizioni_scorrono():
    p = await _pannello()
    for i in range(1, 6):
        await ticket_form_repo.aggiungi_domanda(p.id, f"D{i}")
    with pytest.raises(TroppeDomande):
        await ticket_form_repo.aggiungi_domanda(p.id, "D6")
    assert await ticket_form_repo.rimuovi_domanda(p.id, 2)
    domande = await ticket_form_repo.elenca_domande(p.id)
    assert [(d.position, d.label) for d in domande] == [(1, "D1"), (2, "D3"), (3, "D4"), (4, "D5")]
    assert not await ticket_form_repo.rimuovi_domanda(p.id, 9)


async def test_eliminare_il_pannello_toglie_le_domande(clean_db):
    p = await _pannello()
    await ticket_form_repo.aggiungi_domanda(p.id, "D1")
    assert await ticket_form_repo.rimuovi_pannello(ID_SERVER, "supporto")
    assert await clean_db.fetchval("SELECT count(*) FROM ticket_form_questions") == 0


async def test_il_voto_vale_una_volta_solo_per_chi_ha_aperto_e_a_ticket_chiuso():
    await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, 555, ticket_number=1)
    t = await ticket_repo.get_ticket_by_channel(555)
    assert not await ticket_repo.set_rating(t.id, ID_UTENTE, 5)  # ancora aperto
    await ticket_repo.close_ticket(555, 1)
    assert not await ticket_repo.set_rating(t.id, ID_UTENTE + 1, 5)  # non è suo
    assert await ticket_repo.set_rating(t.id, ID_UTENTE, 4)
    assert not await ticket_repo.set_rating(t.id, ID_UTENTE, 1)  # già votato
    assert await ticket_repo.get_rating_summary(ID_SERVER) == (4.0, 1)


# ====================================================================
# Cog: bottone del pannello, finestra, ticket
# ====================================================================
class Server:
    def __init__(self) -> None:
        self.guild = fake_guild(ID_SERVER)
        self.guild.default_role = fake_role(role_id=ID_SERVER, name="@everyone", position=0)
        self.categoria = create_autospec(discord.CategoryChannel, instance=True)
        self.categoria.id = ID_CATEGORIA
        self.canali: list = []
        self.categoria.create_text_channel.side_effect = self._crea
        self.guild.get_channel.side_effect = lambda cid: self.categoria if cid == ID_CATEGORIA else None

    async def _crea(self, name, **kwargs):
        c = fake_text_channel(1000 + len(self.canali), name)
        c.guild = self.guild
        self.canali.append(c)
        return c

    def interazione(self, user_id=ID_UTENTE):
        m = fake_member(user_id, roles=[], guild_permissions=discord.Permissions())
        m.guild = self.guild
        return fake_interaction(guild=self.guild, user=m)


@pytest.fixture
def scheduler_di_test(monkeypatch):
    nuovo = Scheduler()
    monkeypatch.setattr(modulo, "scheduler", nuovo)
    return nuovo


async def test_pannello_con_domande_apre_la_finestra_e_non_il_ticket(scheduler_di_test):
    p = await _pannello()
    await ticket_form_repo.aggiungi_domanda(p.id, "Qual è il problema?", "descrivi", True, True)
    s = Server()
    i = s.interazione()
    await modulo.apri_da_pannello(i, p.id)
    i.response.send_modal.assert_awaited_once()
    finestra = i.response.send_modal.await_args.args[0]
    assert len(finestra.children) == 1
    assert finestra.children[0].style is discord.TextStyle.paragraph
    assert s.canali == []  # il ticket nasce solo all'invio


async def test_invio_del_modulo_crea_il_ticket_con_le_risposte(scheduler_di_test):
    p = await _pannello(welcome_text="Ciao {utente}!")
    await ticket_form_repo.aggiungi_domanda(p.id, "Nick in gioco")
    await ticket_form_repo.aggiungi_domanda(p.id, "Note", required=False)
    s = Server()
    i = s.interazione()
    finestra = modulo.ModuloTicket(p, await ticket_form_repo.elenca_domande(p.id))
    finestra.children[0]._value = "Yokai"
    finestra.children[1]._value = ""
    i.guild = s.guild
    await finestra.on_submit(i)

    assert len(s.canali) == 1
    embed = s.canali[0].send.await_args.kwargs["embed"]
    assert [(f.name, f.value) for f in embed.fields] == [("Categoria", "Supporto"), ("Nick in gioco", "Yokai")]
    assert embed.description.startswith("Ciao ")
    t = await ticket_repo.get_ticket_by_channel(s.canali[0].id)
    assert t.panel_id == p.id


async def test_domanda_obbligatoria_vuota_non_apre_nessun_ticket(scheduler_di_test):
    p = await _pannello()
    await ticket_form_repo.aggiungi_domanda(p.id, "Nick")
    s = Server()
    i = s.interazione()
    finestra = modulo.ModuloTicket(p, await ticket_form_repo.elenca_domande(p.id))
    finestra.children[0]._value = "   "
    await finestra.on_submit(i)
    assert s.canali == []
    i.response.send_message.assert_awaited_once()


async def test_pannello_senza_domande_apre_subito_e_pianifica_la_chiusura_automatica(scheduler_di_test, clean_db):
    p = await _pannello()
    await ticket_form_repo.imposta_chiusura_automatica(p.id, 30)
    s = Server()
    i = s.interazione()
    await modulo.apri_da_pannello(i, p.id)
    assert len(s.canali) == 1
    azioni = await clean_db.fetch(
        "SELECT * FROM scheduled_actions WHERE action_type = $1", modulo.TICKET_AUTOCLOSE_ACTION_TYPE
    )
    assert len(azioni) == 1


async def test_utente_con_ticket_aperto_non_vede_la_finestra(scheduler_di_test):
    p = await _pannello()
    await ticket_form_repo.aggiungi_domanda(p.id, "Nick")
    await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, 777, ticket_number=1)
    s = Server()
    i = s.interazione()
    await modulo.apri_da_pannello(i, p.id)
    i.response.send_modal.assert_not_awaited()
    assert modulo.MESSAGGIO_TICKET_GIA_APERTO in i.response.send_message.await_args.args[0]


async def test_pannello_di_un_altro_server_o_cancellato_non_si_apre(scheduler_di_test):
    p = await _pannello()
    s = Server()
    i = s.interazione()
    i.guild = fake_guild(ID_SERVER + 5)
    # Il modulo è acceso anche nell'altro server: a fermare l'apertura è il pannello, non il modulo spento.
    await db.set_module_active_for_guild(ID_SERVER + 5, modulo.MODULE_TICKETS, True)
    await modulo.apri_da_pannello(i, p.id)
    assert s.canali == []
    assert "non è più disponibile" in i.response.send_message.await_args.args[0]
    await modulo.apri_da_pannello(s.interazione(), p.id + 999)
    assert s.canali == []


# ====================================================================
# Bottoni persistenti
# ====================================================================
def test_i_bottoni_dei_pannelli_hanno_custom_id_stabile_e_la_view_non_scade():
    pannelli = [SimpleNamespace(id=i, button_label=f"P{i}", button_emoji=None) for i in range(1, 8)]
    vista = modulo.vista_pannelli(pannelli)
    assert vista.timeout is None
    ids = [b.item.custom_id for b in vista.children]
    assert ids == [f"tkt:pan:{i}" for i in range(1, 8)]
    assert all(len(c) <= 100 for c in ids)


def test_oltre_25_pannelli_in_un_messaggio_e_rifiutato():
    pannelli = [SimpleNamespace(id=i, button_label="x", button_emoji=None) for i in range(26)]
    with pytest.raises(form.ErroreConfigurazione):
        modulo.vista_pannelli(pannelli)


async def test_setup_registra_i_bottoni_dinamici_e_i_comandi_stanno_nei_limiti():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    try:
        assert bot._connection._view_store._dynamic_items  # BottonePannello, BottoneVoto
        from tests.support.percorsi import percorsi_del_gruppo

        gestione = {p for p in percorsi_del_gruppo("admin") if p.startswith("ticket ")}
        assert {"ticket pannello-crea", "ticket pannello-pubblica", "ticket modulo-aggiungi",
                "ticket chiusura-auto", "ticket voto"} <= gestione
        assert len(gestione) <= 25
    finally:
        for cog in list(bot.cogs):
            await bot.remove_cog(cog)


async def test_il_clic_sul_voto_registra_le_stelle_una_volta_sola():
    await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, 555, ticket_number=1)
    await ticket_repo.close_ticket(555, 1)
    t = await ticket_repo.get_ticket_by_channel(555)
    bottone = modulo.BottoneVoto(t.id, 5)
    i = fake_interaction(user=fake_member(ID_UTENTE))
    await bottone.callback(i)
    i.response.edit_message.assert_awaited_once()
    assert (await ticket_repo.get_ticket_by_channel(555)).rating == 5
    i2 = fake_interaction(user=fake_member(ID_UTENTE))
    await bottone.callback(i2)
    i2.response.send_message.assert_awaited_once()
    assert (await ticket_repo.get_ticket_by_channel(555)).rating == 5


async def test_voto_chiesto_in_dm_solo_se_acceso_nel_pannello(scheduler_di_test):
    p = await _pannello()
    await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, 555, ticket_number=1, panel_id=p.id)
    t = await ticket_repo.get_ticket_by_channel(555)
    utente = fake_member(ID_UTENTE)
    utente.send = AsyncMock()
    guild = fake_guild(ID_SERVER)
    guild.get_member.return_value = utente
    cog = modulo.TicketsCog(MagicMock())
    await cog._richiedi_voto(guild, t)
    utente.send.assert_not_awaited()
    await ticket_form_repo.imposta_voto(p.id, True)
    await cog._richiedi_voto(guild, t)
    utente.send.assert_awaited_once()
    assert len(utente.send.await_args.kwargs["view"].children) == 5


# ====================================================================
# Comandi di /gestione ticket
# ====================================================================
async def _cog():
    return modulo.TicketsCog(MagicMock())


def _testo(i) -> str:
    c = i.response.send_message.await_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


async def test_comando_modulo_aggiungi_rifiuta_la_sesta_domanda_con_un_messaggio():
    p = await _pannello()
    for n in range(5):
        await ticket_form_repo.aggiungi_domanda(p.id, f"D{n}")
    s = Server()
    i = s.interazione()
    cog = await _cog()
    await cog.modulo_aggiungi.callback(cog, i, "Supporto", "Sesta")
    assert "massimo di Discord" in _testo(i)
    assert len(await ticket_form_repo.elenca_domande(p.id)) == 5


async def test_comando_pannello_crea_rifiuta_nome_con_virgola_ed_emoji_finta():
    s = Server()
    cog = await _cog()
    i = s.interazione()
    await cog.pannello_crea.callback(cog, i, "A,B", s.categoria)
    assert "virgole" in _testo(i)
    i = s.interazione()
    await cog.pannello_crea.callback(cog, i, "Ok", s.categoria, emoji="non-emoji")
    assert "emoji" in _testo(i)
    assert await ticket_form_repo.elenca_pannelli(ID_SERVER) == []


async def test_comando_chiusura_auto_fuori_intervallo_e_spegnimento():
    p = await _pannello()
    s = Server()
    cog = await _cog()
    i = s.interazione()
    await cog.chiusura_auto.callback(cog, i, "Supporto", 3)
    assert "5 minuti" in _testo(i)
    await cog.chiusura_auto.callback(cog, s.interazione(), "Supporto", 90)
    assert (await ticket_form_repo.pannello_per_id(p.id)).autoclose_minutes == 90
    await cog.chiusura_auto.callback(cog, s.interazione(), "Supporto", 0)
    assert (await ticket_form_repo.pannello_per_id(p.id)).autoclose_minutes is None


async def test_pubblica_con_un_pannello_inesistente_non_manda_nulla():
    await _pannello()
    s = Server()
    i = s.interazione()
    cog = await _cog()
    await cog.pannello_pubblica.callback(cog, i, "Supporto, Fantasma")
    assert "Fantasma" in _testo(i)
    assert "view" not in i.response.send_message.await_args.kwargs


async def test_pubblica_due_pannelli_in_un_solo_messaggio():
    await _pannello("Supporto")
    await _pannello("Candidature")
    s = Server()
    i = s.interazione()
    cog = await _cog()
    await cog.pannello_pubblica.callback(cog, i, "Supporto, candidature")
    vista = i.response.send_message.await_args.kwargs["view"]
    assert [b.item.label for b in vista.children] == ["Supporto", "Candidature"]

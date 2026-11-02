"""
tests/test_ticket_gestione.py
=============================
#120 (D66), blocco T3: etichette colorate (TKT-068), spostamento in un altro pannello (TKT-067) e articoli
della base di conoscenza (TKT-079). Regole pure, repository (database vero), menu «Gestisci» con Discord finto.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import discord
import pytest

import cogs.tickets.modmail as modmail
import cogs.tickets.tickets as modulo
from core import ticket_gestione_logic as g
from core.database import db
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_gestione_repo import (
    EtichettaGiaEsistente, TroppeEtichette, TroppiArticoli, ticket_gestione_repo as repo,
)
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.repositories.ticket_repo import ticket_repo
from core.ticket_form_logic import ErroreConfigurazione
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

GUILD = 100


# ====================================================================
# Regole pure
# ====================================================================
def test_colore_e_nomi():
    assert g.colore_valido("#E67E22") == 0xE67E22 and g.colore_valido("e67e22") == 0xE67E22
    assert g.colore_valido(None) == g.COLORE_BASE
    for brutto in ("rosso", "#12345", "#GGGGGG"):
        with pytest.raises(ErroreConfigurazione):
            g.colore_valido(brutto)
    assert g.etichetta_valida("  Urgente ") == "Urgente"
    for nome in ("", "x" * 33):
        with pytest.raises(ErroreConfigurazione):
            g.etichetta_valida(nome)


def test_articolo_valido_e_valore_di_completamento():
    assert g.articolo_valido(" T ", " testo ") == ("T", "testo")
    for t, x in (("", "a"), ("a" * 101, "a"), ("a", ""), ("a", "x" * 4001)):
        with pytest.raises(ErroreConfigurazione):
            g.articolo_valido(t, x)
    assert g.id_articolo(g.valore_articolo(123)) == 123
    assert g.id_articolo("ciao") is None and g.id_articolo("a:x") is None
    assert len(g.valore_articolo(2**31)) <= 100


def test_menu_sposta_sta_in_25_voci_e_salta_il_pannello_attuale():
    pannelli = [SimpleNamespace(id=i, name=f"P{i}") for i in range(1, 31)]
    voci = g.voci_sposta(pannelli, 3)
    assert len(voci) == 25 and voci[-1][0] == g.VALORE_ALTRI and "3" not in [v for v, _ in voci]
    assert len(g.voci_sposta(pannelli[:5], 1)) == 4


def test_etichette_sull_embed():
    e = discord.Embed(title="t", color=1)
    g.applica_etichette(e, [("Urgente", 0xFF0000), ("Vip", 0x00FF00)], "Etichette")
    assert e.color.value == 0xFF0000 and e.fields[0].value == "Urgente · Vip"
    g.applica_etichette(e, [("Vip", 0x00FF00)], "Etichette")
    assert len(e.fields) == 1 and e.fields[0].value == "Vip"
    g.applica_etichette(e, [], "Etichette")
    assert e.fields == []


def test_l_articolo_giusto_risponde_alla_richiesta():
    a1 = SimpleNamespace(id=1, parole=g.parole_articolo("Rimborso acquisto", "Per un rimborso scrivi la ricevuta dell'acquisto"), usi=0)
    a2 = SimpleNamespace(id=2, parole=g.parole_articolo("Verifica account", "Come completare la verifica con il captcha"), usi=0)
    assert g.scegli_articolo([a1, a2], "vorrei un rimborso per il mio acquisto").id == 1
    assert g.scegli_articolo([a1, a2], "non riesco a fare la verifica del captcha").id == 2
    assert g.scegli_articolo([a1, a2], "ciao a tutti") is None


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


async def test_etichette_tetto_duplicati_e_assegnazione():
    for i in range(25):
        await repo.aggiungi_etichetta(GUILD, f"E{i}", 1, None)
    with pytest.raises(TroppeEtichette):
        await repo.aggiungi_etichetta(GUILD, "extra", 1, None)
    assert await repo.togli_etichetta(GUILD, "e0")
    with pytest.raises(EtichettaGiaEsistente):
        await repo.aggiungi_etichetta(GUILD, "E1", 1, None)
    await ticket_repo.create_ticket(GUILD, 20, 555, ticket_number=1)
    t = await ticket_repo.get_ticket_by_channel(555)
    tutte = await repo.elenca_etichette(GUILD)
    assert [e.nome for e in await repo.assegna_etichette(t.id, GUILD, [tutte[0].id, tutte[1].id])] == ["E1", "E2"]
    await repo.assegna_etichette(t.id, GUILD, [tutte[1].id, 999999])  # una di un altro server o inesistente: ignorata
    assert [e.nome for e in await repo.etichette_del_ticket(t.id)] == ["E2"]
    await repo.togli_etichetta(GUILD, "E2")
    assert await repo.etichette_del_ticket(t.id) == []


async def test_articoli_tetto_modifica_ricerca_e_confini_del_server():
    a = await repo.salva_articolo(GUILD, "Rimborso", "Testo", g.parole_articolo("Rimborso", "Testo"), 1)
    assert (await repo.salva_articolo(GUILD, "Rimborso 2", "T", "", 1, articolo_id=a.id)).titolo == "Rimborso 2"
    assert await repo.salva_articolo(GUILD + 1, "x", "y", "", 1, articolo_id=a.id) is None  # non di quel server
    assert [x.titolo for x in await repo.cerca_articoli(GUILD, "rimb")] == ["Rimborso 2"]
    assert await repo.cerca_articoli(GUILD + 1, "") == []
    await repo.conta_uso(a.id)
    assert (await repo.articolo(GUILD, a.id)).usi == 1
    for i in range(199):
        await repo.salva_articolo(GUILD, f"A{i}", "t", "", 1)
    with pytest.raises(TroppiArticoli):
        await repo.salva_articolo(GUILD, "troppo", "t", "", 1)
    assert not await repo.elimina_articolo(GUILD + 1, a.id) and await repo.elimina_articolo(GUILD, a.id)


async def test_modmail_sostituisce_il_valore_di_completamento_con_il_testo():
    a = await repo.salva_articolo(GUILD, "Rimborso", "Scrivi alla ricevuta", "", 1)
    assert await modmail.testo_da_articolo(GUILD, g.valore_articolo(a.id)) == "Scrivi alla ricevuta"
    assert (await repo.articolo(GUILD, a.id)).usi == 1
    assert await modmail.testo_da_articolo(GUILD, "testo libero") == "testo libero"
    assert await modmail.testo_da_articolo(GUILD, g.valore_articolo(a.id + 50)) is None


# ====================================================================
# Cog: sposta, etichette, suggerimento
# ====================================================================
class Server:
    def __init__(self) -> None:
        self.guild = fake_guild(GUILD)
        self.guild.default_role = fake_role(role_id=GUILD, name="@everyone", position=0)
        self.cat = {}
        self.guild.get_channel.side_effect = lambda cid: self.cat.get(cid)
        self.guild.get_role.side_effect = lambda rid: fake_role(role_id=rid, name=f"r{rid}")

    def categoria(self, cid, canali=0):
        c = create_autospec(discord.CategoryChannel, instance=True)
        c.id, c.channels = cid, [object()] * canali
        self.cat[cid] = c
        return c


async def _ticket_in_pannello(panel):
    await ticket_repo.create_ticket(GUILD, 20, 777, ticket_number=1, panel_id=panel.id)
    return await ticket_repo.get_ticket_by_channel(777)


async def test_sposta_cambia_categoria_permessi_e_pannello():
    vecchio = await ticket_form_repo.crea_pannello(GUILD, "Vecchio", 900, "v")
    nuovo = await ticket_form_repo.crea_pannello(GUILD, "Nuovo", 901, "n")
    await ticket_opzioni_repo.imposta(vecchio.id, ruoli_staff=[11])
    await ticket_opzioni_repo.imposta(nuovo.id, ruoli_staff=[22])
    s = Server()
    s.categoria(901)
    canale = fake_text_channel(777)
    t = await _ticket_in_pannello(vecchio)
    esito = await modulo.sposta_ticket(canale, s.guild, t, nuovo)
    assert esito is None
    assert canale.edit.await_args.kwargs["category"] is s.cat[901]
    toccati = {c.args[0].id: c.kwargs for c in canale.set_permissions.await_args_list}
    assert toccati[11]["overwrite"] is None and toccati[22]["overwrite"].view_channel is True
    assert (await ticket_repo.get_ticket_by_channel(777)).panel_id == nuovo.id


async def test_sposta_con_categoria_piena_non_cambia_niente():
    vecchio = await ticket_form_repo.crea_pannello(GUILD, "Vecchio", 900, "v")
    nuovo = await ticket_form_repo.crea_pannello(GUILD, "Nuovo", 901, "n")
    s = Server()
    s.categoria(901, canali=50)
    canale = fake_text_channel(777)
    t = await _ticket_in_pannello(vecchio)
    assert await modulo.sposta_ticket(canale, s.guild, t, nuovo) == "categoria_piena"
    canale.edit.assert_not_awaited()
    assert (await ticket_repo.get_ticket_by_channel(777)).panel_id == vecchio.id
    assert await modulo.sposta_ticket(canale, s.guild, t, SimpleNamespace(id=nuovo.id, category_id=12345)) == "categoria_mancante"


async def test_scegliere_le_etichette_colora_il_benvenuto():
    urgente = await repo.aggiungi_etichetta(GUILD, "Urgente", 0xFF0000, None)
    pan = await ticket_form_repo.crea_pannello(GUILD, "P", 900, "p")
    t = await _ticket_in_pannello(pan)
    messaggio = SimpleNamespace(embeds=[discord.Embed(title="Ticket", color=1)], edit=AsyncMock())
    vista = modulo.VistaEtichette(t, messaggio, await repo.elenca_etichette(GUILD), "Etichette")
    vista.children[0]._values = [str(urgente.id)]
    i = fake_interaction(guild=Server().guild, user=fake_member(30))
    await vista.children[0].callback(i)
    embed = messaggio.edit.await_args.kwargs["embeds"][0]
    assert embed.color.value == 0xFF0000 and embed.fields[0].value == "Urgente"
    assert [e.nome for e in await repo.etichette_del_ticket(t.id)] == ["Urgente"]


async def test_il_ticket_aperto_riceve_l_articolo_che_risponde_alla_richiesta():
    await repo.salva_articolo(GUILD, "Rimborso acquisto", "Scrivi la ricevuta", g.parole_articolo("Rimborso acquisto", "Scrivi la ricevuta"), 1)
    canale = fake_text_channel(777)
    await modulo.suggerisci_articolo(canale, GUILD, "vorrei un rimborso per il mio acquisto", [])
    embed = canale.send.await_args.kwargs["embed"]
    assert "Rimborso acquisto" in embed.title and "ricevuta" in embed.description
    canale.send.reset_mock()
    await modulo.suggerisci_articolo(canale, GUILD, "ciao", [("Nick", "mario")])
    canale.send.assert_not_awaited()

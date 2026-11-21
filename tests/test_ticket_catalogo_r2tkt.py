"""
tests/test_ticket_catalogo_r2tkt.py
===================================
#120, controllo delle voci del catalogo ticket: aspetto dei pannelli (TKT-002, 003, 004, 005, 036),
campi del modulo (TKT-011, 012, 014), e le voci che si sono trovate già fatte e senza prova.
Regole pure, repository veri (clean_db) e codice di produzione dei cog; Discord finto.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.tickets.tickets as modulo
from core import ticket_form_logic as form
from core.database import db
from core.repositories.saved_embed_repo import saved_embed_repo
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

ID_SERVER = 100
ID_UTENTE = 20
ID_CATEGORIA = 900


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(saved_embed_repo, "_pool_provider", lambda: clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, modulo.MODULE_TICKETS, True)
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    yield
    database_module.db._modules_cache.clear()


async def _pannello(nome="Supporto", **kw):
    return await ticket_form_repo.crea_pannello(ID_SERVER, nome, ID_CATEGORIA, nome, **kw)


class Server:
    def __init__(self) -> None:
        self.guild = fake_guild(ID_SERVER, "Server uno")
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
        m.display_name = "Mario [x](http://e.it)"
        return fake_interaction(guild=self.guild, user=m)


def _testo(i) -> str:
    c = i.response.send_message.await_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


# ====================================================================
# TKT-002: bottoni per riga
# ====================================================================
def test_tkt_002_i_bottoni_per_riga_si_scelgono_da_1_a_5():
    assert form.righe_di_bottoni(7, 3) == [3, 3, 1]
    assert form.righe_di_bottoni(5, 5) == [5]
    assert form.righe_di_bottoni(5, 1) == [1, 1, 1, 1, 1]
    for sbagliato in (0, 6):
        with pytest.raises(form.ErroreConfigurazione):
            form.righe_di_bottoni(3, sbagliato)
    with pytest.raises(form.ErroreConfigurazione):
        form.righe_di_bottoni(11, 2)  # 6 righe: Discord ne ammette 5
    assert form.righe_di_bottoni(10, 2) == [2] * 5


def test_tkt_002_la_vista_mette_ogni_bottone_nella_sua_riga():
    pannelli = [SimpleNamespace(id=i, button_label=f"P{i}", button_emoji=None) for i in range(1, 6)]
    vista = modulo.vista_pannelli(pannelli, per_riga=2)
    assert [b.item.row for b in vista.children] == [0, 0, 1, 1, 2]
    with pytest.raises(form.ErroreConfigurazione):
        modulo.vista_pannelli(pannelli, per_riga=6)


# ====================================================================
# TKT-003: messaggio del pannello personalizzabile
# ====================================================================
async def test_tkt_003_il_messaggio_del_pannello_ha_colore_miniatura_e_immagine():
    await _pannello("Supporto")
    i = Server().interazione()
    cog = modulo.TicketsCog(MagicMock())
    await cog.pannello_pubblica.callback(
        cog, i, "Supporto", "Aiuto", "Scrivici", 5, "#c24a3a", "https://esempio.it/m.png", "https://esempio.it/i.png", None
    )
    embed = i.response.send_message.await_args.kwargs["embed"]
    assert (embed.title, embed.description) == ("Aiuto", "Scrivici")
    assert embed.colour.value == 0xC24A3A
    assert embed.thumbnail.url == "https://esempio.it/m.png" and embed.image.url == "https://esempio.it/i.png"


@pytest.mark.parametrize("campo,valore", [("colore", "rosso"), ("miniatura", "ftp://x.it/a.png"), ("immagine", "https://a b.it/x.png")])
async def test_tkt_003_colore_o_indirizzo_sbagliati_non_pubblicano_nulla(campo, valore):
    await _pannello("Supporto")
    i = Server().interazione()
    cog = modulo.TicketsCog(MagicMock())
    argomenti = {"colore": None, "miniatura": None, "immagine": None, campo: valore}
    await cog.pannello_pubblica.callback(cog, i, "Supporto", "T", "X", 5, argomenti["colore"], argomenti["miniatura"], argomenti["immagine"], None)
    assert "embed" not in i.response.send_message.await_args.kwargs
    assert "view" not in i.response.send_message.await_args.kwargs


async def test_tkt_003_un_embed_salvato_prende_il_posto_di_titolo_e_testo():
    await _pannello("Supporto")
    await saved_embed_repo.create(ID_SERVER, "mio", json.dumps({"title": "Dal costruttore", "description": "Testo salvato", "color": "#112233"}), 1)
    i = Server().interazione()
    cog = modulo.TicketsCog(MagicMock())
    await cog.pannello_pubblica.callback(cog, i, "Supporto", "T", "X", 5, None, None, None, "MIO")
    assert i.response.send_message.await_args.kwargs["embed"].title == "Dal costruttore"
    await cog.pannello_pubblica.callback(cog, i, "Supporto", "T", "X", 5, None, None, None, "inesistente")
    assert "inesistente" in _testo(i)


# ====================================================================
# TKT-004: bottone personalizzabile (testo, colore, emoji)
# ====================================================================
async def test_tkt_004_il_colore_del_bottone_si_salva_e_arriva_al_bottone():
    p = await _pannello("Supporto")
    assert p.button_style == "primary"
    cog = modulo.TicketsCog(MagicMock())
    i = Server().interazione()
    await cog.pannello_aspetto.callback(cog, i, "Supporto", SimpleNamespace(value="verde"), None, None)
    p = await ticket_form_repo.pannello_per_id(p.id)
    assert p.button_style == "success"
    vista = modulo.vista_pannelli([p])
    assert vista.children[0].item.style is discord.ButtonStyle.success
    assert vista.children[0].item.label == "Supporto"


def test_tkt_004_un_colore_sconosciuto_e_un_errore():
    assert form.stile_bottone(" Rosso ") == "danger"
    with pytest.raises(form.ErroreConfigurazione):
        form.stile_bottone("viola")
    assert modulo.BottonePannello(1, "x", None, "inventato").item.style is discord.ButtonStyle.primary


def test_tkt_004_l_etichetta_del_bottone_sta_in_80_caratteri():
    assert len(form.etichetta_bottone("E" * 200)) == 80


# ====================================================================
# TKT-005: menu con segnaposto e descrizione per ogni voce
# ====================================================================
async def test_tkt_005_il_menu_dei_motivi_ha_segnaposto_e_descrizioni():
    p = await _pannello("Supporto")
    await ticket_form_repo.aggiungi_motivo(p.id, "Acquisti", None, None, "Problemi con un ordine")
    await ticket_form_repo.aggiungi_motivo(p.id, "Altro tema", None, None, None)
    cog = modulo.TicketsCog(MagicMock())
    await cog.pannello_aspetto.callback(cog, Server().interazione(), "Supporto", None, "Di cosa hai bisogno?", None)
    p = await ticket_form_repo.pannello_per_id(p.id)
    vista = modulo.VistaMotivi(p, await ticket_form_repo.elenca_motivi(p.id), ("…", "Altro"))
    menu = vista.children[0]
    assert menu.placeholder == "Di cosa hai bisogno?"
    assert [o.description for o in menu.options] == ["Problemi con un ordine", None, None]


async def test_tkt_005_la_descrizione_e_tagliata_a_100_e_vale_anche_per_le_categorie():
    motivi = [SimpleNamespace(id=1, etichetta="A", emoji=None, descrizione="d" * 300)]
    assert len(form.opzioni_motivi(motivi)[0][3]) == 100
    await ticket_repo.add_category(ID_SERVER, "Supporto tecnico", 5, None, "Guasti e domande")
    categorie = await ticket_repo.list_categories(ID_SERVER)
    assert [o.description for o in modulo._category_options(categorie)] == ["Guasti e domande"]


# ====================================================================
# TKT-011: minimo e massimo di caratteri
# ====================================================================
def test_tkt_011_minimo_e_massimo_si_controllano():
    assert form.limiti_testo(10, 50) == (10, 50)
    assert form.limiti_testo(0, None) == (None, None)
    for minimo, massimo in ((-1, None), (None, 0), (None, 4001), (20, 10)):
        with pytest.raises(form.ErroreConfigurazione):
            form.limiti_testo(minimo, massimo)


async def test_tkt_011_la_finestra_porta_minimo_e_massimo_e_un_invio_fuori_misura_non_apre_il_ticket():
    p = await _pannello()
    await ticket_form_repo.aggiungi_domanda(p.id, "Racconta", None, True, True, min_length=20, max_length=3000)
    domande = await ticket_form_repo.elenca_domande(p.id)
    finestra = modulo.ModuloTicket(p, domande)
    campo = finestra.children[0]
    assert (campo.min_length, campo.max_length) == (20, 3000)
    s = Server()
    i = s.interazione()
    campo._value = "troppo corto"
    await finestra.on_submit(i)
    assert s.canali == [] and "Racconta" in _testo(i)
    i2 = s.interazione()
    campo._value = "una risposta abbastanza lunga da passare"
    await finestra.on_submit(i2)
    assert len(s.canali) == 1


def test_tkt_011_un_minimo_sopra_il_tetto_di_prima_alza_il_tetto():
    d = SimpleNamespace(min_length=500, max_length=None, long_answer=False, tipo="testo")
    assert form.lunghezza_minima_massima(d) == (500, 500)


# ====================================================================
# TKT-012: campi a scelta
# ====================================================================
def test_tkt_012_le_voci_di_un_campo_a_scelta():
    assert form.opzioni_scelta("Uno; due ;UNO;; tre") == ("Uno", "due", "tre")
    for sbagliato in ("solo una", "", ";".join(str(n) for n in range(26)), "a;" + "b" * 101):
        with pytest.raises(form.ErroreConfigurazione):
            form.opzioni_scelta(sbagliato)


async def test_tkt_012_la_finestra_ha_menu_dentro_un_etichetta_e_si_legge_la_scelta():
    p = await _pannello()
    await ticket_form_repo.aggiungi_domanda(p.id, "Quale gioco?", "scegli", True, False, tipo="scelta", opzioni=("Minecraft", "Valorant"), max_valori=1)
    await ticket_form_repo.aggiungi_domanda(p.id, "Chi segnali?", None, False, False, tipo="utente")
    domande = await ticket_form_repo.elenca_domande(p.id)
    assert domande[0].opzioni == ("Minecraft", "Valorant")
    finestra = modulo.ModuloTicket(p, domande)
    etichetta, utente = finestra.children
    assert isinstance(etichetta, discord.ui.Label) and isinstance(etichetta.component, discord.ui.Select)
    assert [o.value for o in etichetta.component.options] == ["Minecraft", "Valorant"]
    assert isinstance(utente.component, discord.ui.UserSelect) and utente.component.required is False
    etichetta.component._values = ["Valorant"]
    assert modulo._valori_campo(etichetta) == ["Valorant"]


async def test_tkt_012_utente_ruolo_e_canale_scelti_diventano_nomi_puliti_mai_menzioni(monkeypatch):
    persona = SimpleNamespace(id=7, display_name="Zoe [click](http://x.it) <@&5>")
    monkeypatch.setattr(discord.ui.UserSelect, "values", property(lambda self: [persona]))
    etichetta = discord.ui.Label(text="x", component=discord.ui.UserSelect())
    nome = modulo._valori_campo(etichetta)[0]
    assert "[" not in nome and "<" not in nome and "(" not in nome and nome.startswith("Zoe")


async def test_tkt_012_una_voce_che_non_c_e_non_apre_il_ticket():
    p = await _pannello()
    await ticket_form_repo.aggiungi_domanda(p.id, "Gioco", None, True, False, tipo="scelta", opzioni=("A", "B"))
    domande = await ticket_form_repo.elenca_domande(p.id)
    assert form.scelte_non_ammesse(domande, [["C"]]) == ["Gioco"]
    s = Server()
    finestra = modulo.ModuloTicket(p, domande)
    finestra.children[0].component._values = ["C"]
    await finestra.on_submit(s.interazione())
    assert s.canali == []


async def test_tkt_012_il_comando_modulo_aggiungi_controlla_le_voci():
    await _pannello()
    cog = modulo.TicketsCog(MagicMock())
    i = Server().interazione()
    await cog.modulo_aggiungi.callback(cog, i, "Supporto", "Gioco", None, True, False, None, None, SimpleNamespace(value="scelta"), "una sola", 1)
    assert await ticket_form_repo.elenca_domande((await ticket_form_repo.pannello_per_nome(ID_SERVER, "Supporto")).id) == []
    i = Server().interazione()
    await cog.modulo_aggiungi.callback(cog, i, "Supporto", "Gioco", None, True, False, None, None, SimpleNamespace(value="scelta"), "A;B;C", 5)
    assert await ticket_form_repo.elenca_domande((await ticket_form_repo.pannello_per_nome(ID_SERVER, "Supporto")).id) == []  # 5 scelte su 3 voci
    i = Server().interazione()
    await cog.modulo_aggiungi.callback(cog, i, "Supporto", "Gioco", None, True, False, None, None, SimpleNamespace(value="scelta"), "A;B;C", 2)
    d = (await ticket_form_repo.elenca_domande((await ticket_form_repo.pannello_per_nome(ID_SERVER, "Supporto")).id))[0]
    assert (d.tipo, d.opzioni, d.max_valori) == ("scelta", ("A", "B", "C"), 2)


# ====================================================================
# TKT-014: un modulo riusabile su più pannelli, con copia
# ====================================================================
async def test_tkt_014_il_modulo_si_copia_su_un_altro_pannello_e_poi_sono_indipendenti():
    a, b = await _pannello("Supporto"), await _pannello("Candidature")
    await ticket_form_repo.aggiungi_domanda(a.id, "Nick", "come ti chiami", True, False, min_length=3)
    await ticket_form_repo.aggiungi_domanda(a.id, "Gioco", None, False, False, tipo="scelta", opzioni=("A", "B"))
    await ticket_form_repo.aggiungi_domanda(b.id, "Vecchia domanda")
    cog = modulo.TicketsCog(MagicMock())
    i = Server().interazione()
    await cog.modulo_copia.callback(cog, i, "Supporto", "Candidature")
    copia = await ticket_form_repo.elenca_domande(b.id)
    assert [(d.position, d.label, d.min_length, d.tipo, d.opzioni) for d in copia] == [
        (1, "Nick", 3, "testo", ()), (2, "Gioco", None, "scelta", ("A", "B"))]
    await ticket_form_repo.rimuovi_domanda(b.id, 1)
    assert len(await ticket_form_repo.elenca_domande(a.id)) == 2  # l'originale non cambia
    i = Server().interazione()
    await cog.modulo_copia.callback(cog, i, "Supporto", "supporto")
    assert len(await ticket_form_repo.elenca_domande(a.id)) == 2  # sullo stesso pannello non fa nulla


# ====================================================================
# TKT-036: messaggio di apertura personalizzabile con segnaposto
# ====================================================================
def test_tkt_036_i_segnaposto_si_sostituiscono_una_volta_sola_e_i_sconosciuti_restano():
    valori = {"utente": "<@5>", "nome": "{server}", "server": "Casa", "numero": "0007", "pannello": "Aiuto"}
    assert form.testo_benvenuto("{utente} · {nome} · {numero} · {x} · {pannello}", valori) == "<@5> · {server} · 0007 · {x} · Aiuto"
    assert form.testo_benvenuto("{utente.__class__}", valori) == "{utente.__class__}"
    assert len(form.testo_benvenuto("a" * 9000, valori)) == 4000


def test_tkt_036_un_nome_scelto_da_un_utente_non_apre_link_ne_menzioni():
    nome = form.nome_sicuro("Mario [vai](http://x.it) `a` <@&1> ‮@everyone")
    assert not any(c in nome for c in "[]()`<>@‮")


async def _apri(panel, s):
    i = s.interazione()
    await modulo._open_ticket_channel(i, s.guild, s.categoria, "Supporto", panel=panel)
    return s.canali[-1].send.await_args.kwargs["embed"]


async def test_tkt_036_il_benvenuto_del_pannello_usa_i_segnaposto():
    p = await _pannello("Aiuto", welcome_text="Ciao {utente} nel {server}: ticket {numero} di {pannello} ({nome})")
    embed = await _apri(p, Server())
    assert embed.description.startswith("Ciao <@20> nel Server uno: ticket 0001 di Aiuto (Mario")
    assert "](" not in embed.description and "[" not in embed.description  # nessun link mascherato dal nome dell'utente


async def test_tkt_036_un_embed_salvato_e_il_messaggio_di_apertura_con_le_risposte_dopo():
    dati = {"title": "Ticket {numero}", "description": "Benvenuto {utente} in {server}", "color": "#112233",
            "footer": "{pannello}", "fields": [["Regole", "Sii gentile con {nome}", False]]}
    await saved_embed_repo.create(ID_SERVER, "apertura", json.dumps(dati), 1)
    p = await _pannello("Aiuto")
    cog = modulo.TicketsCog(MagicMock())
    await cog.pannello_aspetto.callback(cog, Server().interazione(), "Aiuto", None, None, "Apertura")
    p = await ticket_form_repo.pannello_per_id(p.id)
    assert p.embed_apertura == "apertura"
    s = Server()
    i = s.interazione()
    await modulo._open_ticket_channel(i, s.guild, s.categoria, "Supporto", panel=p, campi=[("Nick", "Yokai")])
    embed = s.canali[0].send.await_args.kwargs["embed"]
    assert embed.title == "Ticket 0001" and embed.description == "Benvenuto <@20> in Server uno"
    assert embed.footer.text == "Aiuto" and embed.colour.value == 0x112233
    assert [f.name for f in embed.fields][:2] == ["Regole", "Categoria"] and embed.fields[-1].name == "Nick"
    await cog.pannello_aspetto.callback(cog, Server().interazione(), "Aiuto", None, None, "nessuno")
    assert (await ticket_form_repo.pannello_per_id(p.id)).embed_apertura is None


async def test_tkt_036_se_l_embed_salvato_sparisce_il_ticket_nasce_lo_stesso():
    p = await _pannello("Aiuto")
    await ticket_form_repo.imposta_aspetto(p.id, embed_apertura="cancellato")
    p = await ticket_form_repo.pannello_per_id(p.id)
    s = Server()
    embed = await _apri(p, s)
    assert "Ciao" in embed.description and len(s.canali) == 1

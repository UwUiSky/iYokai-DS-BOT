"""
tests/test_ticket_catalogo_r2tkt_c.py
=====================================
#120, controllo del catalogo ticket, terza parte: raccolta di modelli pronti (TKT-080) e riassunto AI della
conversazione nel log (TKT-086). Database vero; Discord e AI finti.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

import cogs.tickets.tickets as modulo
from cogs.ai import ticket_ai
from core import channel_router as router
from core import ticket_form_logic as form
from core import ticket_gestione_logic as gestione
from core import ticket_modelli_logic as modl
from core.database import db
from core.repositories.ai_ticket_repo import ai_ticket_repo
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_gestione_repo import ticket_gestione_repo
from core.repositories.ticket_repo import ticket_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

GUILD = 100
UTENTE = 20
CATEGORIA = 900


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(GUILD, modulo.MODULE_TICKETS, True)
    yield
    database_module.db._modules_cache.clear()


def _inter():
    m = fake_member(31, guild_permissions=discord.Permissions(manage_guild=True))
    return fake_interaction(guild=fake_guild(GUILD, "Server uno"), user=m)


def _categoria():
    c = discord.utils  # segnaposto per avere un oggetto con id
    return SimpleNamespace(id=CATEGORIA, name="Ticket")


# ====================================================================
# TKT-080: raccolta di modelli
# ====================================================================
@pytest.mark.parametrize("lingua", ["it", "en-US"])
def test_tkt_080_ogni_modello_rispetta_i_limiti_di_discord_e_del_bot(lingua):
    visti = modl.modelli(lingua)
    assert 3 <= len(visti) <= 4
    for m in visti:
        assert 1 <= len(form.nome_pannello_valido(m.nome)) <= form.MAX_NOME_PANNELLO and len(form.etichetta_bottone(m.nome)) <= 80
        assert len(m.benvenuto) <= form.MAX_TESTO_BENVENUTO and len(m.descrizione) <= 200
        assert 1 <= len(m.domande) <= form.MAX_DOMANDE and len(m.motivi) <= form.MAX_MOTIVI
        for d in m.domande:
            form.domanda_valida(d.etichetta, d.segnaposto)
            if d.tipo == "scelta":
                assert form.opzioni_scelta(";".join(d.voci)) == d.voci
            else:
                form.limiti_testo(d.minimo, None)
        for etichetta, descrizione in m.motivi:
            form.motivo_valido(etichetta, None)
            assert len(descrizione or "") <= form.MAX_DESCRIZIONE_VOCE
        for titolo, testo in m.articoli:
            gestione.articolo_valido(titolo, testo)


def test_tkt_080_le_due_lingue_hanno_gli_stessi_modelli_e_la_stessa_forma():
    it, en = modl.modelli("it"), modl.modelli("en-US")
    assert [m.id for m in it] == [m.id for m in en] == list(modl.IDENTIFICATORI)
    for a, b in zip(it, en):
        assert [(d.tipo, d.obbligatoria, d.lunga, d.minimo, len(d.voci)) for d in a.domande] == [
            (d.tipo, d.obbligatoria, d.lunga, d.minimo, len(d.voci)) for d in b.domande]
        assert len(a.motivi) == len(b.motivi) and len(a.articoli) == len(b.articoli) and a.voto == b.voto
    assert modl.modelli("fr") == en  # ogni altra lingua: inglese
    assert modl.modello(" SUPPORTO ", "it").id == "supporto" and modl.modello("boh", "it") is None


async def test_tkt_080_l_importazione_crea_pannello_modulo_motivi_risposte_e_voto():
    cog = modulo.TicketsCog(SimpleNamespace())
    i = _inter()
    await cog.pannello_modello.callback(cog, i, SimpleNamespace(value="supporto"), _categoria(), None)
    panel = await ticket_form_repo.pannello_per_nome(GUILD, "Supporto")
    assert panel.category_id == CATEGORIA and panel.rating_enabled is True and "{utente}" in panel.welcome_text
    domande = await ticket_form_repo.elenca_domande(panel.id)
    assert [d.position for d in domande] == [1, 2] and domande[0].min_length == 15 and domande[1].required is False
    assert len(await ticket_form_repo.elenca_motivi(panel.id)) == 2
    assert [a.titolo for a in await ticket_gestione_repo.cerca_articoli(GUILD, "")] == ["Come funziona il supporto"]
    # I campi del modello si trasformano in una finestra che Discord accetta.
    assert len(modulo.ModuloTicket(panel, domande).children) == 2
    assert "Supporto" in i.followup.send.await_args.args[0]


async def test_tkt_080_un_modello_con_campi_a_scelta_diventa_una_finestra_valida():
    cog = modulo.TicketsCog(SimpleNamespace())
    await cog.pannello_modello.callback(cog, _inter(), SimpleNamespace(value="segnalazioni"), _categoria(), "Segnala qui")
    panel = await ticket_form_repo.pannello_per_nome(GUILD, "segnala qui")
    domande = await ticket_form_repo.elenca_domande(panel.id)
    assert [d.tipo for d in domande] == ["scelta", "utente", "testo"]
    finestra = modulo.ModuloTicket(panel, domande)
    assert isinstance(finestra.children[0], discord.ui.Label) and len(finestra.children) == 3


async def test_tkt_080_senza_modello_c_e_l_elenco_senza_categoria_o_con_un_nome_gia_preso_non_cambia_nulla():
    cog = modulo.TicketsCog(SimpleNamespace())
    i = _inter()
    await cog.pannello_modello.callback(cog, i, None, None, None)
    testo = i.response.send_message.await_args.args[0]
    assert all(m.id in testo for m in modl.modelli("it"))
    i = _inter()
    await cog.pannello_modello.callback(cog, i, SimpleNamespace(value="supporto"), None, None)
    assert await ticket_form_repo.elenca_pannelli(GUILD) == []
    await cog.pannello_modello.callback(cog, _inter(), SimpleNamespace(value="supporto"), _categoria(), None)
    doppio = _inter()
    await cog.pannello_modello.callback(cog, doppio, SimpleNamespace(value="supporto"), _categoria(), None)
    assert len(await ticket_form_repo.elenca_pannelli(GUILD)) == 1 and "esiste" in doppio.response.send_message.await_args.args[0].lower()
    lungo = _inter()
    await cog.pannello_modello.callback(cog, lungo, SimpleNamespace(value="partnership"), _categoria(), "x" * 50)
    assert len(await ticket_form_repo.elenca_pannelli(GUILD)) == 2


# ====================================================================
# TKT-086: riassunto AI nel log
# ====================================================================
async def _ticket_con_pannello(riassunto: bool):
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 1, "Supporto")
    if riassunto:
        await ai_ticket_repo.imposta_riassunto(GUILD, p.id, True)
    await ticket_repo.create_ticket(GUILD, UTENTE, 200, ticket_number=7, panel_id=p.id)
    return await ticket_repo.get_ticket_by_channel(200)


@pytest.fixture
def ai(monkeypatch):
    chiedi = AsyncMock(return_value=(SimpleNamespace(testo="Problema: login. @everyone Risolto. discord.gg/abcdef"), None))
    monkeypatch.setattr(ticket_ai, "chiedi", chiedi)
    monkeypatch.setattr(ticket_ai, "testo_canale", AsyncMock(return_value="Utente: non entro"))
    log = fake_text_channel(777, "log")
    monkeypatch.setattr(router, "destinazione", AsyncMock(return_value=log))
    invia = AsyncMock(return_value=True)
    monkeypatch.setattr(router, "invia_a", invia)
    return SimpleNamespace(chiedi=chiedi, invia=invia)


async def test_tkt_086_il_riassunto_va_nel_log_pulito_e_senza_menzioni(ai):
    t = await _ticket_con_pannello(True)
    cog = ticket_ai.AiTicketCog(bot=None)
    await cog.riassunto_alla_chiusura(fake_guild(GUILD), fake_text_channel(200), t)
    ai.chiedi.assert_awaited_once()
    richiesta = ai.chiedi.await_args.args[0]
    assert richiesta.funzione == "ticket_riassunto" and richiesta.guild_id == GUILD and richiesta.conta_utente is False
    embed = ai.invia.await_args.kwargs["embed"]
    assert embed.title == "Riassunto del ticket #0007" and "Problema: login" in embed.description
    assert "@everyone" not in embed.description.replace("@​everyone", "") and "discord.gg" not in embed.description
    permessi = ai.invia.await_args.kwargs["allowed_mentions"]
    assert permessi.everyone is False and permessi.users is False and permessi.roles is False


async def test_tkt_086_senza_il_consenso_del_pannello_l_ai_non_viene_nemmeno_chiamata(ai):
    t = await _ticket_con_pannello(False)
    cog = ticket_ai.AiTicketCog(bot=None)
    await cog.riassunto_alla_chiusura(fake_guild(GUILD), fake_text_channel(200), t)
    ai.chiedi.assert_not_awaited()
    ai.invia.assert_not_awaited()


async def test_tkt_086_ai_ferma_o_canale_vuoto_il_ticket_si_chiude_lo_stesso(ai, monkeypatch):
    t = await _ticket_con_pannello(True)
    cog = ticket_ai.AiTicketCog(bot=None)
    ai.chiedi.return_value = (None, "AI ferma")
    await cog.riassunto_alla_chiusura(fake_guild(GUILD), fake_text_channel(200), t)
    ai.invia.assert_not_awaited()
    monkeypatch.setattr(ticket_ai, "testo_canale", AsyncMock(return_value=""))
    ai.chiedi.reset_mock()
    await cog.riassunto_alla_chiusura(fake_guild(GUILD), fake_text_channel(200), t)
    ai.chiedi.assert_not_awaited()  # niente da riassumere: niente costo


async def test_tkt_086_il_comando_accende_e_spegne_per_pannello():
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 1, "Supporto")
    cog = ticket_ai.AiTicketCog(bot=None)
    i = _inter()
    i.guild_id = GUILD
    await cog.riassunto_cmd.callback(cog, i, "Supporto", True)
    assert await ai_ticket_repo.riassunto_attivo(GUILD, p.id) is True
    await cog.riassunto_cmd.callback(cog, i, "Supporto", False)
    assert await ai_ticket_repo.riassunto_attivo(GUILD, p.id) is False
    assert await ai_ticket_repo.riassunto_attivo(GUILD + 1, p.id) is False


async def test_tkt_086_la_chiusura_chiama_il_riassunto_e_un_errore_non_la_ferma(monkeypatch):
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    cog = bot.get_cog("TicketsCog")
    cog._deliver_transcript = AsyncMock()
    cog._fine_ticket = AsyncMock()
    cog._cog_risposte = lambda: None
    t = await _ticket_con_pannello(True)
    chiamato = AsyncMock(side_effect=RuntimeError("AI rotta"))
    bot.get_cog = lambda nome: SimpleNamespace(riassunto_alla_chiusura=chiamato) if nome == "AiTicketCog" else None
    await cog._transcript_senza_bloccare(fake_guild(GUILD), fake_text_channel(200), t)
    chiamato.assert_awaited_once()
    assert 200 not in cog._transcript_in_corso
    await bot.close()

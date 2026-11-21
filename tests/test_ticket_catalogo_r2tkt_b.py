"""
tests/test_ticket_catalogo_r2tkt_b.py
=====================================
#120, controllo del catalogo ticket, seconda parte: escludere un ticket dalla chiusura automatica (TKT-062),
questionario dopo il voto (TKT-066), log delle azioni (TKT-076), statistiche avanzate (TKT-077), risposte pronte
per lo staff (TKT-078), bozza AI mai inviata (TKT-087). Database vero; Discord finto.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.tickets.risposte as risposte
import cogs.tickets.tickets as modulo
from cogs.tickets.inattivita import TicketInattivitaCog
from cogs.tickets.tickets import TICKET_AUTOCLOSE_ACTION_TYPE
from core import channel_router as router
from core import ticket_log_logic as logl
from core import ticket_statistiche_logic as statl
from core.database import db
from core.repositories.ticket_automazioni_repo import ticket_automazioni_repo as autom
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_gestione_repo import ticket_gestione_repo
from core.repositories.ticket_log_repo import ticket_log_repo
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

GUILD = 100
CANALE = 200
UTENTE = 20
STAFF = 31
BOT_ID = 999


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(GUILD, modulo.MODULE_TICKETS, True)
    yield
    database_module.db._modules_cache.clear()


@pytest.fixture
async def cog(monkeypatch):
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    c = bot.get_cog("TicketsCog")
    c._transcript_senza_bloccare = AsyncMock()
    c._richiedi_voto = AsyncMock()
    yield c
    await bot.close()


def _manager(uid=STAFF):
    m = fake_member(uid, guild_permissions=discord.Permissions(manage_guild=True))
    m.display_name = "Giulia"
    return m


def _inter(user, canale_id=CANALE):
    guild = fake_guild(GUILD, "Server uno")
    return fake_interaction(guild=guild, user=user, channel=fake_text_channel(canale_id))


async def _pannello(**kw):
    return await ticket_form_repo.crea_pannello(GUILD, "Supporto", 1, "Supporto", **kw)


async def _ticket(panel_id=None, numero=1, canale=CANALE):
    await ticket_repo.create_ticket(GUILD, UTENTE, canale, ticket_number=numero, panel_id=panel_id)
    return await ticket_repo.get_ticket_by_channel(canale)


def _testo(i) -> str:
    c = i.response.send_message.await_args
    return str(c)


# ====================================================================
# TKT-062: escludere un ticket dalla chiusura automatica
# ====================================================================
async def test_tkt_062_il_comando_vale_solo_per_lo_staff_e_su_un_ticket_aperto(cog):
    await _ticket()
    i = _inter(fake_member(UTENTE))
    await cog.tieni_aperto.callback(cog, i, True)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).tieni_aperto is False
    await cog.tieni_aperto.callback(cog, _inter(_manager()), True)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).tieni_aperto is True
    await cog.tieni_aperto.callback(cog, _inter(_manager()), False)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).tieni_aperto is False
    await ticket_repo.close_ticket(CANALE, STAFF)
    chiuso = _inter(_manager())
    await cog.tieni_aperto.callback(cog, chiuso, True)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).tieni_aperto is False


async def test_tkt_062_un_ticket_escluso_non_si_chiude_da_solo_e_riparte_quando_e_tolto(cog, clean_db):
    p = await _pannello()
    await ticket_form_repo.imposta_chiusura_automatica(p.id, 30)
    await _ticket(p.id)
    await ticket_repo._pool.execute(
        "UPDATE tickets SET last_activity_at = $1 WHERE channel_id = $2", datetime.now(timezone.utc) - timedelta(minutes=500), CANALE
    )
    canale = fake_text_channel(CANALE)
    canale.guild = fake_guild(GUILD)
    canale.guild.me = fake_member(BOT_ID)
    cog.bot.get_channel = lambda cid: canale
    await ticket_repo.set_tieni_aperto(CANALE, True)
    await cog.handle_ticket_autoclose(GUILD, UTENTE, {"channel_id": CANALE})
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "open"
    (azione,) = await clean_db.fetch("SELECT * FROM scheduled_actions WHERE action_type = $1", TICKET_AUTOCLOSE_ACTION_TYPE)
    assert abs((azione["execute_at"] - (datetime.now(timezone.utc) + timedelta(minutes=30))).total_seconds()) < 60
    await ticket_repo.set_tieni_aperto(CANALE, False)
    await cog.handle_ticket_autoclose(GUILD, UTENTE, {"channel_id": CANALE})
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "closed"


async def test_tkt_062_le_regole_che_chiudono_saltano_il_ticket_escluso_ma_il_sollecito_resta():
    p = await _pannello()
    await _ticket(p.id)
    await ticket_repo._pool.execute("UPDATE tickets SET tieni_aperto = TRUE WHERE channel_id = $1", CANALE)
    await autom.aggiungi_regola(p.id, "utente", 30, "messaggio", "Ci sei {utente}?", False)
    await autom.aggiungi_regola(p.id, "utente", 60, "chiudi", None, False)
    canale = fake_text_channel(CANALE)
    canale.__class__ = discord.TextChannel
    canale.send = AsyncMock()
    chiudi = AsyncMock(return_value=True)
    tickets_cog = SimpleNamespace(_chiudi_da_sistema=chiudi, _pianifica_eliminazione_canale=AsyncMock())
    guild = SimpleNamespace(id=GUILD, get_channel=lambda c: canale, get_channel_or_thread=lambda c: canale, me=SimpleNamespace(id=1))
    cog = TicketInattivitaCog.__new__(TicketInattivitaCog)
    cog.bot = SimpleNamespace(get_guild=lambda g: guild, get_cog=lambda n: tickets_cog)
    cog._regole, cog._dopo_id = {}, 0
    adesso = datetime.now(timezone.utc)
    await autom.segna_scritto(CANALE, True, adesso - timedelta(minutes=120))
    await cog.controlla_ticket(adesso)
    canale.send.assert_awaited_once()  # il sollecito parte
    # Un testo di regola con @everyone non deve mai avvisare tutti: solo chi ha aperto il ticket.
    permessi = canale.send.await_args.kwargs["allowed_mentions"]
    assert permessi.everyone is False and permessi.roles is False and [u.id for u in permessi.users] == [UTENTE]
    chiudi.assert_not_awaited()  # la chiusura no
    await ticket_repo.set_tieni_aperto(CANALE, False)
    cog._regole = {}
    await cog.controlla_ticket(adesso + timedelta(minutes=1))
    chiudi.assert_awaited_once()


# ====================================================================
# TKT-066: questionario dopo il voto
# ====================================================================
async def _chiuso_e_votato(domanda="Cosa miglioreresti?", voto=True):
    p = await _pannello()
    await ticket_form_repo.imposta_voto(p.id, True)
    await ticket_form_repo.imposta_questionario(p.id, domanda)
    t = await _ticket(p.id)
    await ticket_repo.close_ticket(CANALE, STAFF)
    if voto:
        await ticket_repo.set_rating(t.id, UTENTE, 4)
    return t


async def test_tkt_066_la_risposta_si_salva_solo_dopo_il_voto_una_volta_e_solo_di_chi_ha_aperto():
    t = await _chiuso_e_votato(voto=False)
    assert await ticket_form_repo.questionario_in_attesa(t.id, UTENTE) is None  # prima il voto
    assert not await ticket_form_repo.salva_risposta_questionario(t.id, UTENTE, "x")
    await ticket_repo.set_rating(t.id, UTENTE, 5)
    assert await ticket_form_repo.questionario_in_attesa(t.id, UTENTE) == "Cosa miglioreresti?"
    assert await ticket_form_repo.questionario_in_attesa(t.id, UTENTE + 1) is None  # non è suo
    assert not await ticket_form_repo.salva_risposta_questionario(t.id, UTENTE + 1, "intruso")
    assert await ticket_form_repo.salva_risposta_questionario(t.id, UTENTE, "I tempi")
    assert not await ticket_form_repo.salva_risposta_questionario(t.id, UTENTE, "di nuovo")
    assert await ticket_form_repo.risposta_questionario(t.id) == "I tempi"
    assert await ticket_form_repo.questionario_in_attesa(t.id, UTENTE) is None


async def test_tkt_066_il_clic_sul_voto_apre_il_questionario_e_chi_chiude_la_finestra_puo_riaprirla(monkeypatch):
    t = await _chiuso_e_votato()
    await ticket_repo._pool.execute("UPDATE tickets SET rating = NULL, rated_at = NULL WHERE id = $1", t.id)
    monkeypatch.setattr(modulo, "registra_azione", AsyncMock())
    i = fake_interaction(user=fake_member(UTENTE))
    i.client = MagicMock()
    await modulo.BottoneVoto(t.id, 5).callback(i)
    finestra = i.response.send_modal.await_args.args[0]
    assert isinstance(finestra, modulo.ModuloQuestionario) and finestra.children[0].label == "Cosa miglioreresti?"
    i.response.edit_message.assert_not_awaited()
    # La finestra viene chiusa senza rispondere: un secondo clic la riapre, il voto resta quello del primo.
    i2 = fake_interaction(user=fake_member(UTENTE))
    i2.client = MagicMock()
    await modulo.BottoneVoto(t.id, 1).callback(i2)
    i2.response.send_modal.assert_awaited_once()
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).rating == 5
    finestra.children[0]._value = "  Più staff  "
    inv = fake_interaction(user=fake_member(UTENTE))
    inv.client = MagicMock()
    await finestra.on_submit(inv)
    assert await ticket_form_repo.risposta_questionario(t.id) == "Più staff"
    inv.response.edit_message.assert_awaited_once()
    i3 = fake_interaction(user=fake_member(UTENTE))
    i3.client = MagicMock()
    await modulo.BottoneVoto(t.id, 2).callback(i3)
    i3.response.send_modal.assert_not_awaited()  # già risposto: solo «hai già votato»
    i3.response.send_message.assert_awaited_once()


async def test_tkt_066_una_risposta_vuota_o_di_un_altro_non_si_salva():
    t = await _chiuso_e_votato()
    finestra = modulo.ModuloQuestionario(t.id, "Cosa?")
    finestra.children[0]._value = "   "
    i = fake_interaction(user=fake_member(UTENTE))
    await finestra.on_submit(i)
    i.response.send_message.assert_awaited_once()
    finestra.children[0]._value = "ok"
    altro = fake_interaction(user=fake_member(UTENTE + 5))
    await finestra.on_submit(altro)
    assert await ticket_form_repo.risposta_questionario(t.id) is None


async def test_tkt_066_il_comando_voto_imposta_e_toglie_la_domanda(cog):
    p = await _pannello()
    await cog.voto.callback(cog, _inter(_manager()), "Supporto", True, "  Come   è andata? ")
    assert (await ticket_form_repo.pannello_per_id(p.id)).questionario == "Come è andata?"
    await cog.voto.callback(cog, _inter(_manager()), "Supporto", True, "NESSUNO")
    assert (await ticket_form_repo.pannello_per_id(p.id)).questionario is None


# ====================================================================
# TKT-076: log delle azioni
# ====================================================================
def test_tkt_076_azioni_e_pulizia_dei_testi():
    assert logl.azioni_scelte("TUTTE") == logl.AZIONI and logl.azioni_scelte("chiuso") == ("chiuso",)
    for nome in ("inventata", ""):
        with pytest.raises(logl.ErroreLog):
            logl.azioni_scelte(nome)
    assert set(logl.AZIONI) >= {"creato", "chiuso", "riaperto", "rinominato", "eliminato", "preso", "passato", "priorita"}
    pulito = logl.dettaglio_sicuro("ciao `x`‮\x07 " + "a" * 2000)
    assert "`" not in pulito and "‮" not in pulito and "\x07" not in pulito and len(pulito) == 1024
    assert logl.dettaglio_sicuro("  ​ ") is None


async def test_tkt_076_gli_interruttori_sono_per_server_e_spenti_di_base():
    assert await ticket_log_repo.accese(GUILD) == frozenset()
    await ticket_log_repo.imposta(GUILD, ("chiuso", "creato"), True)
    await ticket_log_repo.imposta(GUILD, ("creato",), False)
    assert await ticket_log_repo.accese(GUILD) == frozenset({"chiuso"})
    assert await ticket_log_repo.accese(GUILD + 1) == frozenset()
    with pytest.raises(ValueError):
        await ticket_log_repo.imposta(GUILD, ("falsa",), True)


async def test_tkt_076_registra_azione_scrive_solo_se_acceso_senza_menzioni(monkeypatch):
    t = await _ticket()
    canale_log = fake_text_channel(777, "log")
    monkeypatch.setattr(router, "destinazione", AsyncMock(return_value=canale_log))
    invia = AsyncMock(return_value=True)
    monkeypatch.setattr(router, "invia_a", invia)
    guild = fake_guild(GUILD, "Server uno")
    await modulo.registra_azione(guild, "chiuso", t, staff_id=STAFF, dettaglio="finito")
    invia.assert_not_awaited()  # spento
    await ticket_log_repo.imposta(GUILD, ("chiuso",), True)
    await modulo.registra_azione(guild, "chiuso", t, staff_id=STAFF, dettaglio="finito `@everyone`‮")
    invia.assert_awaited_once()
    argomenti = invia.await_args
    assert argomenti.args[2] == router.TIPO_TICKET
    embed = argomenti.kwargs["embed"]
    assert argomenti.kwargs["allowed_mentions"].everyone is False and not argomenti.kwargs["allowed_mentions"].users
    campi = {f.name: f.value for f in embed.fields}
    assert campi["Ticket"] == "#0001" and campi["Staff"] == f"<@{STAFF}>" and "‮" not in campi["Dettaglio"]
    await modulo.registra_azione(guild, "creato", t)  # un'altra azione, spenta
    assert invia.await_count == 1


async def test_tkt_076_un_log_che_non_parte_non_ferma_nessuno(monkeypatch):
    t = await _ticket()
    await ticket_log_repo.imposta(GUILD, logl.AZIONI, True)
    monkeypatch.setattr(router, "destinazione", AsyncMock(side_effect=RuntimeError("giù")))
    await modulo.registra_azione(fake_guild(GUILD), "chiuso", t)  # niente eccezione
    monkeypatch.setattr(router, "destinazione", AsyncMock(return_value=None))
    await modulo.registra_azione(fake_guild(GUILD), "chiuso", t)
    await modulo.registra_azione(None, "chiuso", t)


async def test_tkt_076_le_azioni_vere_scrivono_nel_log(cog, monkeypatch):
    p = await _pannello()
    await _ticket(p.id)
    registra = AsyncMock()
    monkeypatch.setattr(modulo, "registra_azione", registra)
    inter = _inter(_manager())
    await cog.priority.callback(cog, inter, SimpleNamespace(value="high"))
    assert registra.await_args.args[1] == "priorita" and registra.await_args.kwargs["dettaglio"] == "high"
    await cog.claim.callback(cog, _inter(_manager()))
    assert registra.await_args.args[1] == "preso"
    monkeypatch.setattr(modulo, "_support_role_ids", AsyncMock(return_value=[7]))
    collega = fake_member(52, roles=[fake_role(role_id=7)])
    await cog.passa.callback(cog, _inter(_manager()), collega)
    assert registra.await_args.args[1] == "passato"
    canale = fake_text_channel(CANALE)
    canale.guild = fake_guild(GUILD)
    canale.guild.me = fake_member(BOT_ID)
    cog.bot.get_channel = lambda cid: canale
    await cog._chiudi_e_pianifica(GUILD, CANALE, STAFF, "risolto", UTENTE, "motivo")
    assert registra.await_args.args[1] == "chiuso" and registra.await_args.kwargs["dettaglio"] == "risolto"
    cog.bot.get_guild = lambda g: canale.guild
    await cog._elimina_canale(CANALE, "pulizia")
    assert registra.await_args.args[1] == "eliminato"


async def test_tkt_076_il_comando_log_accende_spegne_e_sceglie_il_canale(cog):
    i = _inter(_manager())
    await cog.ticket_log.callback(cog, i, SimpleNamespace(value="tutte"), True, None)
    assert await ticket_log_repo.accese(GUILD) == frozenset(logl.AZIONI)
    await cog.ticket_log.callback(cog, _inter(_manager()), SimpleNamespace(value="voto"), False, None)
    assert "voto" not in await ticket_log_repo.accese(GUILD)
    privo = fake_text_channel(55)
    privo.permissions_for.return_value = discord.Permissions(view_channel=True)
    i = _inter(_manager())
    await cog.ticket_log.callback(cog, i, None, True, privo)
    assert await router.output_channel_repo.ottieni(GUILD, router.TIPO_TICKET) is None
    bene = fake_text_channel(56)
    bene.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True, embed_links=True)
    await cog.ticket_log.callback(cog, _inter(_manager()), None, True, bene)
    assert (await router.output_channel_repo.ottieni(GUILD, router.TIPO_TICKET)).channel_id == 56


# ====================================================================
# TKT-077: statistiche avanzate
# ====================================================================
def test_tkt_077_le_righe_stanno_in_un_campo_e_il_motivo_e_pulito():
    assert statl.riga_giorni([]) == "-"
    assert len(statl.riga_motivi([("x" * 200 + "`", 3)] * 5)) <= 1024
    assert "`" not in statl.riga_motivi([("a`b‮", 2)])
    assert statl.riga_operatori([(7, 4.5, 2)]) == "<@7>: 4.50 (2)"
    assert statl.riga_ore([(9, 4)]) == "09:00-09:59 UTC: 4"


async def test_tkt_077_i_numeri_in_piu_sono_giusti(cog):
    for n, canale in enumerate((201, 202, 203), start=1):
        await ticket_repo.create_ticket(GUILD, UTENTE + n, canale, ticket_number=n)
    adesso = datetime.now(timezone.utc)
    await ticket_repo._pool.execute(
        "UPDATE tickets SET created_at = $1 WHERE channel_id = 201", adesso - timedelta(hours=5))
    await ticket_repo.close_ticket(201, STAFF, reason="risolto")
    await ticket_repo.close_ticket(202, STAFF, reason="risolto")
    await ticket_repo._pool.execute(
        "UPDATE tickets SET first_response_at = now(), claimed_by = 55, rating = 5 WHERE channel_id = 202")
    dati = await ticket_repo.get_statistiche_avanzate(GUILD)
    assert dati["aperti"] == 1 and dati["chiusi"] == 2 and dati["senza_risposta"] == 1
    assert dati["motivi"] == [("risolto", 2)]
    assert dati["operatori"] == [(55, 5.0, 1)]
    assert sum(n for _, n in dati["giorni"]) == 3 and dati["soluzione_s"] is not None
    i = _inter(_manager())
    await cog.ticket_stats.callback(cog, i, None, True)
    embed = i.response.send_message.await_args.kwargs["embed"]
    assert len(embed) <= 6000 and len(embed.fields) == 7
    assert i.response.send_message.await_args.kwargs["allowed_mentions"].users is False


async def test_tkt_077_senza_ticket_le_statistiche_non_si_rompono(cog):
    i = _inter(_manager())
    await cog.ticket_stats.callback(cog, i, None, True)
    assert i.response.send_message.await_args.kwargs["embed"].fields[0].value.startswith("0")


# ====================================================================
# TKT-078: risposte pronte per lo staff, con segnaposto
# ====================================================================
@pytest.fixture
async def cog_risposte():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    return risposte.RisposteStandardCog(bot)


async def test_tkt_078_lo_staff_scrive_un_articolo_con_i_segnaposto_e_nessun_ping_extra(cog_risposte):
    p = await _pannello()
    await _ticket(p.id)
    a = await ticket_gestione_repo.salva_articolo(
        GUILD, "Rimborso", "Ciao {utente} ({nome}), sono {staff} su {server}: ticket {numero} di {pannello} @everyone {boh}", "", 1)
    i = _inter(_manager())
    i.guild.get_member.return_value = None
    i.guild.name = "Server uno"
    await cog_risposte.risposta_pronta.callback(cog_risposte, i, f"a:{a.id}")
    r = i.response.send_message.await_args.kwargs
    assert "<@20>" in r["embed"].description and "sono Giulia su Server uno: ticket 0001 di Supporto" in r["embed"].description
    assert "{boh}" in r["embed"].description  # un segnaposto sconosciuto resta com'è
    assert r["allowed_mentions"].everyone is False and r["allowed_mentions"].roles is False
    assert [u.id for u in r["allowed_mentions"].users] == [UTENTE]
    assert (await ticket_gestione_repo.articolo(GUILD, a.id)).usi == 1


async def test_tkt_078_solo_staff_solo_articoli_veri_e_solo_nei_ticket_aperti(cog_risposte):
    p = await _pannello()
    await _ticket(p.id)
    a = await ticket_gestione_repo.salva_articolo(GUILD, "Rimborso", "Testo", "", 1)
    utente = _inter(fake_member(UTENTE))
    await cog_risposte.risposta_pronta.callback(cog_risposte, utente, f"a:{a.id}")
    assert "embed" not in utente.response.send_message.await_args.kwargs
    libero = _inter(_manager())
    await cog_risposte.risposta_pronta.callback(cog_risposte, libero, "testo scritto a mano")
    assert "embed" not in libero.response.send_message.await_args.kwargs  # solo articoli approvati
    inesistente = _inter(_manager())
    await cog_risposte.risposta_pronta.callback(cog_risposte, inesistente, "a:99999")
    assert "embed" not in inesistente.response.send_message.await_args.kwargs
    fuori = _inter(_manager(), canale_id=4444)
    await cog_risposte.risposta_pronta.callback(cog_risposte, fuori, f"a:{a.id}")
    assert "embed" not in fuori.response.send_message.await_args.kwargs
    await ticket_repo.close_ticket(CANALE, STAFF)
    chiuso = _inter(_manager())
    await cog_risposte.risposta_pronta.callback(cog_risposte, chiuso, f"a:{a.id}")
    assert "embed" not in chiuso.response.send_message.await_args.kwargs


# ====================================================================
# TKT-087: la risposta proposta dall'AI è una bozza per lo staff, mai inviata da sola
# ====================================================================
async def test_tkt_087_la_bozza_ai_e_solo_per_lo_staff_e_nessun_messaggio_parte_nel_ticket(monkeypatch):
    from cogs.ai import ticket_ai

    await _ticket()
    monkeypatch.setattr(ticket_ai, "testo_canale", AsyncMock(return_value="Utente: non riesco a entrare"))
    monkeypatch.setattr(ticket_ai, "conoscenza_del_server", AsyncMock(return_value=""))
    risposta = SimpleNamespace(testo="Prova a riavviare il gioco.")
    monkeypatch.setattr(ticket_ai, "chiedi", AsyncMock(return_value=(risposta, "")))
    i = _inter(_manager())
    i.channel_id = CANALE
    i.guild_id = GUILD
    i.channel.send = AsyncMock()
    await ticket_ai.rispondi_assistente(i)
    i.response.defer.assert_awaited_once_with(ephemeral=True)  # il suo messaggio è privato
    invio = i.followup.send.await_args
    assert invio.kwargs["ephemeral"] is True and "Prova a riavviare" in invio.kwargs["embed"].description
    i.channel.send.assert_not_awaited()  # nel ticket non è arrivato niente

"""
tests/test_ticket_standard.py
=============================
#139, parte senza AI: risposte standard imparate dallo staff e sollecito dopo N minuti.
Regole pure, repository veri (clean_db), cog di produzione; Discord finto.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.tickets.risposte as modulo
import cogs.tickets.tickets as tickets_module
from core import channel_router as router
from core import ticket_standard_logic as logica
from core.database import db
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_repo import ticket_repo
from core.repositories.ticket_standard_repo import ticket_standard_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_role, fake_text_channel
from tests.support.percorsi import percorsi_del_gruppo

GUILD = 100
UTENTE = 20
STAFF = 30
CANALE = 200
RICHIESTA = "Ciao, quali sono i requisiti per l'affiliazione del mio canale Twitch? Servono anche le grafiche"
RISPOSTA = "Servono 50 follower e 3 stream alla settimana. Nel pacchetto trovi le grafiche."


# ====================================================================
# Regole pure
# ====================================================================
def test_parole_senza_stopword_accenti_e_con_radice():
    assert logica.parole_di("Ciao, quali sono i requisiti per l'affiliazione?") == ["quali", "requis", "affili"]
    assert logica.radice("affiliazione") == logica.radice("affiliare")


def test_parole_chiave_ordinate_per_frequenza():
    assert logica.parole_chiave("canale twitch canale grafiche twitch canale")[:2] == ["canale", "twitch"]
    assert len(logica.parole_chiave("alfa beta gamma delta " * 1, massimo=2)) == 2


def test_una_risposta_scatta_con_due_parole_in_comune_non_con_una():
    risposta = {logica.radice(p) for p in ("affiliazione", "twitch", "requisiti")}
    assert logica.corrisponde(set(logica.parole_di("requisiti affiliazione canale")), risposta)
    assert not logica.corrisponde(set(logica.parole_di("il mio canale twitch non va")), risposta)


def test_la_migliore_vince_e_senza_corrispondenza_nessuna():
    a = logica.Candidata(1, frozenset(logica.parole_di("affiliazione twitch requisiti")))
    b = logica.Candidata(2, frozenset(logica.parole_di("rimborso pagamento")))
    assert logica.trova_migliore([b, a], "requisiti affiliazione twitch").id == 1
    assert logica.trova_migliore([a, b], "voglio un rimborso del pagamento").id == 2
    assert logica.trova_migliore([a, b], "ciao come stai") is None
    assert logica.trova_migliore([], "qualsiasi cosa importante") is None


def test_parole_corrette_dallo_staff():
    assert logica.parole_da_testo_staff("Affiliazione, twitch; requisiti\nAffiliazione") == ["affili", "twitch", "requis"]
    assert logica.parole_da_testo_staff("ciao, grazie") == []


def test_scelta_della_coppia_richiesta_risposta():
    M = logica.MessaggioStorico
    storia = [M(1, True, "benvenuto", 0), M(UTENTE, False, "ho un problema", 0), M(UTENTE, False, "con X", 0),
              M(STAFF, False, "ecco", 0)]
    c = logica.scegli_coppia(storia, UTENTE)
    assert c.richiesta == "ho un problema con X" and c.indice_risposta == 3
    assert logica.scegli_coppia([M(STAFF, False, "ciao", 0), M(UTENTE, False, "x", 0)], UTENTE) is None
    assert logica.scegli_coppia([M(UTENTE, False, "x", 0)], UTENTE) is None
    assert logica.scegli_coppia([M(UTENTE, False, "x", 0), M(STAFF, False, "", 2)], UTENTE).indice_risposta == 1


def test_allegati_da_copiare_entro_i_limiti():
    mb = 1024 * 1024
    assert logica.allegati_da_scaricare([1 * mb] * 7) == [0, 1, 2, 3, 4]  # al massimo 5
    assert logica.allegati_da_scaricare([9 * mb, 2 * mb]) == [1]  # uno oltre 8 MiB è saltato
    assert logica.allegati_da_scaricare([8 * mb, 8 * mb, 8 * mb]) == [0, 1]  # in tutto sotto 20 MiB


def test_minuti_del_sollecito():
    assert logica.minuti_sollecito_validi(0) is None and logica.minuti_sollecito_validi(10) == 10
    with pytest.raises(ValueError):
        logica.minuti_sollecito_validi(1441)


# ====================================================================
# Ambiente
# ====================================================================
@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(GUILD, "tickets", True)
    monkeypatch.setattr(tickets_module, "scheduler", Scheduler())
    yield
    database_module.db._modules_cache.clear()


@pytest.fixture
async def cog(monkeypatch):
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    yield bot.get_cog("RisposteStandardCog")
    await bot.close()


async def _pannello(standard=True, sollecito=None, ruolo=None):
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 1, "Supporto")
    if standard:
        await ticket_form_repo.imposta_standard(p.id, True)
    if sollecito:
        await ticket_form_repo.imposta_sollecito(p.id, sollecito, ruolo)
    return await ticket_form_repo.pannello_per_id(p.id)


async def _ticket(p, canale=CANALE):
    await ticket_repo.create_ticket(GUILD, UTENTE, canale, ticket_number=7, panel_id=p.id, category_label="Twitch")
    return await ticket_repo.get_ticket_by_channel(canale)


def _msg(autore_id, testo, allegati=(), bot=False):
    autore = fake_member(autore_id, f"u{autore_id}", bot=bot)
    return SimpleNamespace(
        author=autore, content=testo, attachments=list(allegati),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), id=autore_id,
    )


def _canale_con_storia(righe):
    c = fake_text_channel(CANALE)

    async def storia(**kw):
        for r in righe:
            yield r

    c.history = storia
    return c


def _log(monkeypatch, id_messaggio=9000, allegati=()):
    """Il canale dei log: send restituisce un messaggio con id e gli allegati ricaricati."""
    log = fake_text_channel(777, "log")
    log.send = AsyncMock(return_value=SimpleNamespace(id=id_messaggio, attachments=list(allegati), edit=AsyncMock()))
    monkeypatch.setattr(router, "destinazione", AsyncMock(return_value=log))
    return log


# ====================================================================
# Proposta alla chiusura
# ====================================================================
async def test_alla_chiusura_il_bot_propone_la_risposta_dello_staff(cog, monkeypatch):
    p = await _pannello()
    t = await ticket_repo.get_ticket_by_channel(CANALE) or await _ticket(p)
    await ticket_repo.record_first_response(CANALE, datetime.now(timezone.utc))
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    log = _log(monkeypatch)
    canale = _canale_con_storia([_msg(UTENTE, RICHIESTA), _msg(STAFF, RISPOSTA)])
    await cog.proponi_da_ticket(fake_guild(GUILD), canale, t)

    (proposta,) = await ticket_standard_repo.elenca(GUILD)
    assert proposta.status == "proposed" and proposta.body == RISPOSTA and proposta.panel_id == p.id
    assert "affili" in proposta.keywords and proposta.source_ticket_number == 7
    kw = log.send.await_args.kwargs
    assert [b.item.custom_id for b in kw["view"].children] == [f"tkt:std:{a}:{proposta.id}" for a in ("ok", "mod", "no")]
    assert proposta.proposal_message_id == 9000
    assert await ticket_standard_repo.approvate(GUILD, p.id) == []  # senza approvazione non si usa


async def test_proposta_con_allegati_ricaricati_nel_canale_dei_log(cog, monkeypatch):
    p = await _pannello()
    await _ticket(p)
    await ticket_repo.record_first_response(CANALE, datetime.now(timezone.utc))
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    ricaricato = SimpleNamespace(filename="grafiche.zip", url="https://cdn.example/log/grafiche.zip")
    log = _log(monkeypatch, allegati=[ricaricato])
    originale = SimpleNamespace(filename="grafiche.zip", size=1000, read=AsyncMock(return_value=b"zip"))
    canale = _canale_con_storia([_msg(UTENTE, RICHIESTA), _msg(STAFF, "ecco il pacchetto", [originale])])
    await cog.proponi_da_ticket(fake_guild(GUILD), canale, t)
    (proposta,) = await ticket_standard_repo.elenca(GUILD)
    assert proposta.attachments == [{"filename": "grafiche.zip", "url": "https://cdn.example/log/grafiche.zip"}]
    assert len(log.send.await_args.kwargs["files"]) == 1


@pytest.mark.parametrize("caso", ["spento", "nessuna_risposta_staff", "nessun_log", "gia_coperta", "gia_risposto_dal_bot", "tetto"])
async def test_nessuna_proposta_se_non_ha_senso(cog, monkeypatch, caso):
    p = await _pannello(standard=caso != "spento")
    await _ticket(p)
    if caso != "nessuna_risposta_staff":
        await ticket_repo.record_first_response(CANALE, datetime.now(timezone.utc))
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    log = _log(monkeypatch)
    if caso == "nessun_log":
        monkeypatch.setattr(router, "destinazione", AsyncMock(return_value=None))
    if caso == "gia_coperta":
        r = await ticket_standard_repo.crea_proposta(GUILD, p.id, "t", "affili, twitch, requis", "x", 1)
        await ticket_standard_repo.approva(r.id, STAFF)
    if caso == "gia_risposto_dal_bot":
        await ticket_repo.mark_standard_reply(CANALE, 1)
        t = await ticket_repo.get_ticket_by_channel(CANALE)
    if caso == "tetto":
        monkeypatch.setattr(logica, "MAX_RISPOSTE_PER_SERVER", 0)
    canale = _canale_con_storia([_msg(UTENTE, RICHIESTA), _msg(STAFF, RISPOSTA)])
    await cog.proponi_da_ticket(fake_guild(GUILD), canale, t)
    attese = 1 if caso == "gia_coperta" else 0
    assert len(await ticket_standard_repo.elenca(GUILD)) == attese
    log.send.assert_not_awaited()


async def test_se_l_invio_della_proposta_fallisce_non_resta_una_riga_orfana(cog, monkeypatch):
    p = await _pannello()
    await _ticket(p)
    await ticket_repo.record_first_response(CANALE, datetime.now(timezone.utc))
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    log = _log(monkeypatch)
    log.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="x"), "x")
    await cog.proponi_da_ticket(fake_guild(GUILD), _canale_con_storia([_msg(UTENTE, RICHIESTA), _msg(STAFF, RISPOSTA)]), t)
    assert await ticket_standard_repo.elenca(GUILD) == []


# ====================================================================
# Bottoni dello staff
# ====================================================================
async def _proposta(p):
    return await ticket_standard_repo.crea_proposta(GUILD, p.id, "Affiliazione", "affili, twitch, requis", RISPOSTA, 7)


def _clic(azione, reply_id, *, staff=True, guild_id=GUILD):
    bottone = modulo.BottoneRispostaStandard(azione, reply_id)
    membro = fake_member(STAFF, "staff", guild_permissions=discord.Permissions(manage_guild=staff))
    g = fake_guild(guild_id)
    membro.guild = g
    return bottone, fake_interaction(guild=g, user=membro)


async def test_approva_rende_la_risposta_utilizzabile_una_volta_sola():
    p = await _pannello()
    r = await _proposta(p)
    b, i = _clic("ok", r.id)
    await b.callback(i)
    assert (await ticket_standard_repo.per_id(r.id)).status == "approved"
    assert (await ticket_standard_repo.per_id(r.id)).approved_by == STAFF
    i.response.edit_message.assert_awaited_once()
    b2, i2 = _clic("ok", r.id)
    await b2.callback(i2)
    i2.response.send_message.assert_awaited_once()  # «era già stata decisa»


async def test_scarta_cancella_la_proposta_ma_non_una_approvata():
    p = await _pannello()
    r = await _proposta(p)
    b, i = _clic("no", r.id)
    await b.callback(i)
    assert await ticket_standard_repo.per_id(r.id) is None
    r2 = await _proposta(p)
    await ticket_standard_repo.approva(r2.id, STAFF)
    b, i = _clic("no", r2.id)
    await b.callback(i)
    assert await ticket_standard_repo.per_id(r2.id) is not None


async def test_solo_lo_staff_decide_e_solo_nel_proprio_server():
    p = await _pannello()
    r = await _proposta(p)
    b, i = _clic("ok", r.id, staff=False)
    assert await b.interaction_check(i) is False
    assert (await ticket_standard_repo.per_id(r.id)).status == "proposed"
    b, i = _clic("ok", r.id, guild_id=GUILD + 1)
    await b.callback(i)
    assert (await ticket_standard_repo.per_id(r.id)).status == "proposed"


async def test_modifica_salva_titolo_parole_e_testo_e_rifiuta_parole_vuote():
    p = await _pannello()
    r = await _proposta(p)
    finestra = modulo.ModuloRispostaStandard(r)
    finestra.titolo._value, finestra.parole._value, finestra.corpo._value = "Nuovo", "ciao, grazie", "Testo"
    i = fake_interaction()
    await finestra.on_submit(i)
    assert (await ticket_standard_repo.per_id(r.id)).title == "Affiliazione"  # parole inutili: rifiutato
    finestra.parole._value = "Streamer, Partner"
    await finestra.on_submit(fake_interaction())
    r = await ticket_standard_repo.per_id(r.id)
    assert (r.title, r.keywords, r.body) == ("Nuovo", "stream, partne", "Testo")


# ====================================================================
# Uso nei ticket nuovi
# ====================================================================
async def _approvata(p):
    r = await _proposta(p)
    await ticket_standard_repo.approva(r.id, STAFF)
    return r


def _messaggio_utente(testo):
    canale = fake_text_channel(CANALE)
    m = fake_message(author=fake_member(UTENTE), channel=canale, content=testo)
    return m, canale


async def test_la_richiesta_ricorrente_riceve_subito_la_risposta_approvata(cog):
    p = await _pannello()
    r = await _approvata(p)
    t = await _ticket(p)
    m, canale = _messaggio_utente("Che requisiti servono per l'affiliazione Twitch?")
    await cog.su_messaggio_dell_utente(m, t)
    canale.send.assert_awaited_once()
    assert canale.send.await_args.kwargs["embed"].description == RISPOSTA
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).standard_reply_id == r.id
    assert (await ticket_standard_repo.per_id(r.id)).use_count == 1
    # un secondo messaggio non ripete la risposta
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    await cog.su_messaggio_dell_utente(m, t)
    canale.send.assert_awaited_once()


async def test_una_proposta_non_approvata_o_un_altro_tema_non_scatta(cog):
    p = await _pannello()
    await _proposta(p)  # solo proposta
    t = await _ticket(p)
    m, canale = _messaggio_utente("Che requisiti servono per l'affiliazione Twitch?")
    await cog.su_messaggio_dell_utente(m, t)
    canale.send.assert_not_awaited()
    await _approvata(p)
    m, canale = _messaggio_utente("Il mio rimborso non è arrivato")
    await cog.su_messaggio_dell_utente(m, t)
    canale.send.assert_not_awaited()


async def test_con_le_risposte_spente_o_dopo_lo_staff_non_risponde_il_bot(cog):
    p = await _pannello(standard=False)
    t = await _ticket(p)
    m, canale = _messaggio_utente("requisiti affiliazione Twitch")
    await cog.su_messaggio_dell_utente(m, t)
    canale.send.assert_not_awaited()
    await ticket_form_repo.imposta_standard(p.id, True)
    await _approvata(p)
    await ticket_repo.record_first_response(CANALE, datetime.now(timezone.utc))
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    await cog.su_messaggio_dell_utente(m, t)
    canale.send.assert_not_awaited()


async def test_le_risposte_di_un_altro_pannello_non_valgono(cog):
    p = await _pannello()
    altro = await ticket_form_repo.crea_pannello(GUILD, "Altro", 1, "Altro")
    await ticket_form_repo.imposta_standard(altro.id, True)
    await _approvata(altro)
    t = await _ticket(p)
    m, canale = _messaggio_utente("requisiti affiliazione Twitch")
    await cog.su_messaggio_dell_utente(m, t)
    canale.send.assert_not_awaited()


# ====================================================================
# Sollecito
# ====================================================================
def _canale_bot(cog, monkeypatch):
    canale = fake_text_channel(CANALE)
    monkeypatch.setattr(cog.bot, "get_channel", lambda cid: canale if cid == CANALE else None)
    return canale


async def test_senza_risposta_dello_staff_il_bot_chiede_di_cosa_ha_bisogno_una_volta_sola(cog, monkeypatch):
    p = await _pannello(standard=False, sollecito=10)
    await _ticket(p)
    canale = _canale_bot(cog, monkeypatch)
    await cog.handle_ticket_sollecito(GUILD, UTENTE, {"channel_id": CANALE})
    assert "Di cosa hai bisogno" in canale.send.await_args.args[0]
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).sollecito_at is not None
    await cog.handle_ticket_sollecito(GUILD, UTENTE, {"channel_id": CANALE})
    canale.send.assert_awaited_once()


async def test_nessun_sollecito_se_lo_staff_ha_risposto_se_e_chiuso_o_spento(cog, monkeypatch):
    p = await _pannello(standard=False, sollecito=10)
    await _ticket(p)
    canale = _canale_bot(cog, monkeypatch)
    await ticket_repo.record_first_response(CANALE, datetime.now(timezone.utc))
    await cog.handle_ticket_sollecito(GUILD, UTENTE, {"channel_id": CANALE})
    canale.send.assert_not_awaited()


async def test_risposta_dell_utente_dopo_il_sollecito_senza_risposta_pronta_chiama_il_ruolo(cog, monkeypatch):
    p = await _pannello(standard=True, sollecito=10, ruolo=555)
    await _ticket(p)
    canale = _canale_bot(cog, monkeypatch)
    await cog.handle_ticket_sollecito(GUILD, UTENTE, {"channel_id": CANALE})
    canale.send.reset_mock()
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    m, canale_m = _messaggio_utente("Voglio parlare di una cosa mai vista")
    await cog.su_messaggio_dell_utente(m, t)
    testo = canale_m.send.await_args.args[0]
    assert "<@&555>" in testo
    # chiamato una volta sola
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    canale_m.send.reset_mock()
    await cog.su_messaggio_dell_utente(m, t)
    canale_m.send.assert_not_awaited()


async def test_se_l_utente_aveva_gia_scritto_senza_risposta_pronta_il_sollecito_chiama_subito_lo_staff(cog, monkeypatch):
    p = await _pannello(standard=True, sollecito=10, ruolo=555)
    t = await _ticket(p)
    m, canale_m = _messaggio_utente("Qualcosa di nuovo e strano")
    await cog.su_messaggio_dell_utente(m, t)  # nessuna risposta pronta, sollecito non ancora partito
    canale_m.send.assert_not_awaited()
    canale = _canale_bot(cog, monkeypatch)
    await cog.handle_ticket_sollecito(GUILD, UTENTE, {"channel_id": CANALE})
    assert "<@&555>" in canale.send.await_args.args[0]


async def test_senza_ruolo_scelto_si_chiamano_i_ruoli_di_supporto(cog, monkeypatch):
    await db.set_guild_setting(GUILD, "ticket_support_role_ids", [801, 802])
    p = await _pannello(standard=False, sollecito=10)
    t = await _ticket(p)
    await ticket_repo.mark_user_wrote(CANALE)
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    canale = _canale_bot(cog, monkeypatch)
    await cog.handle_ticket_sollecito(GUILD, UTENTE, {"channel_id": CANALE})
    testo = canale.send.await_args.args[0]
    assert "<@&801>" in testo and "<@&802>" in testo


async def test_il_sollecito_viene_pianificato_alla_creazione_del_ticket():
    p = await _pannello(standard=False, sollecito=15)
    server = fake_guild(GUILD)
    server.default_role = fake_role(role_id=GUILD, name="@everyone", position=0)
    categoria = MagicMock(spec=discord.CategoryChannel)
    canale = fake_text_channel(CANALE)
    categoria.create_text_channel = AsyncMock(return_value=canale)
    i = fake_interaction(guild=server, user=fake_member(UTENTE))
    await tickets_module._open_ticket_channel(i, server, categoria, "Supporto", panel=p)
    azioni = await db.pool.fetch("SELECT * FROM scheduled_actions WHERE action_type = $1", tickets_module.TICKET_SOLLECITO_ACTION_TYPE)
    assert len(azioni) == 1
    atteso = datetime.now(timezone.utc) + timedelta(minutes=15)
    assert abs((azioni[0]["execute_at"] - atteso).total_seconds()) < 60


# ====================================================================
# Comandi e struttura
# ====================================================================
def _admin(canale=None):
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(STAFF), channel=canale)


async def test_comandi_standard_e_sollecito(cog):
    p = await _pannello(standard=False)
    await cog.standard.callback(cog, _admin(), "supporto", True)
    assert (await ticket_form_repo.pannello_per_id(p.id)).standard_attive
    i = _admin()
    await cog.sollecito.callback(cog, i, "Supporto", 2000)
    assert "1440" in i.response.send_message.await_args.args[0]
    await cog.sollecito.callback(cog, _admin(), "Supporto", 10, SimpleNamespace(id=9, mention="<@&9>"))
    p = await ticket_form_repo.pannello_per_id(p.id)
    assert (p.sollecito_minuti, p.ruolo_escalation) == (10, 9)
    await cog.sollecito.callback(cog, _admin(), "Supporto", 0, None)
    p = await ticket_form_repo.pannello_per_id(p.id)
    assert (p.sollecito_minuti, p.ruolo_escalation) == (None, None)


async def test_lista_ed_elimina_solo_nel_proprio_server(cog):
    p = await _pannello()
    r = await _approvata(p)
    i = _admin()
    await cog.lista.callback(cog, i, None)
    assert f"#{r.id}" in i.response.send_message.await_args.args[0]
    altro = fake_interaction(guild=fake_guild(GUILD + 1), user=fake_member(STAFF))
    await cog.elimina.callback(cog, altro, r.id)
    assert await ticket_standard_repo.per_id(r.id) is not None
    await cog.elimina.callback(cog, _admin(), r.id)
    assert await ticket_standard_repo.per_id(r.id) is None


async def test_eliminare_il_pannello_toglie_le_sue_risposte():
    p = await _pannello()
    r = await _approvata(p)
    await ticket_form_repo.rimuovi_pannello(GUILD, "Supporto")
    assert await ticket_standard_repo.per_id(r.id) is None


async def test_setup_registra_bottoni_handler_e_comandi_nei_limiti():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await tickets_module.setup(bot)
    await modulo.setup(bot)
    try:
        assert {"ticket standard", "ticket sollecito", "ticket risposte-lista", "ticket risposta-modifica",
                "ticket risposta-elimina"} <= percorsi_del_gruppo("admin")
        assert len({p for p in percorsi_del_gruppo("admin") if p.startswith("ticket ")}) <= 25
    finally:
        for c in list(bot.cogs):
            await bot.remove_cog(c)

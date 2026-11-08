"""
tests/test_ticket_r18.py
========================
#120 (D66), blocco T4: in attesa dell'utente (TKT-029), regole di inattività (TKT-064),
riserva di canali (TKT-035). Regole pure e repository su database vero.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import ticket_autoclose_worker as w
from core.database import db
from core.repositories.ticket_automazioni_repo import TroppeRegole, ticket_automazioni_repo as repo
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.repositories.ticket_repo import ticket_repo

GUILD = 100
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _min(n):
    return T0 + timedelta(minutes=n)


# ====================================================================
# Regole pure
# ====================================================================
def test_regola_valida_controlla_limiti_e_testo():
    assert w.regola_valida("utente", 5, "chiudi", None, False) == ("utente", 5, "chiudi", None, False)
    for args in (
        ("nessuno", 10, "chiudi", None, False),
        ("utente", 4, "chiudi", None, False),
        ("utente", 43201, "chiudi", None, False),
        ("utente", 10, "ban", None, False),
        ("utente", 10, "messaggio", "  ", False),
        ("utente", 10, "messaggio", "x" * 1001, False),
        ("utente", 10, "chiudi", None, True),
    ):
        with pytest.raises(w.ErroreRegola):
            w.regola_valida(*args)


def _scatta(regola, **k):
    base = dict(creato=_min(0), ultimo_utente=None, ultimo_staff=None, ultima_attivita=None,
                ultima_esecuzione=None, adesso=_min(100))
    base.update(k)
    return w.regola_scattata(regola, **base)


def test_regola_utente_conta_dall_ultimo_messaggio_dell_utente():
    r = w.Regola(1, 1, "utente", 30, "chiudi")
    assert _scatta(r, ultimo_utente=_min(10), adesso=_min(39)) is False
    assert _scatta(r, ultimo_utente=_min(10), adesso=_min(40)) is True
    assert _scatta(r, adesso=_min(29)) is False  # senza messaggi vale l'apertura
    assert _scatta(r, adesso=_min(30)) is True


def test_regola_staff_e_chiunque_usano_il_loro_riferimento():
    staff = w.Regola(1, 1, "staff", 10, "messaggio", "ciao")
    assert _scatta(staff, ultimo_staff=_min(95), ultimo_utente=_min(0), adesso=_min(100)) is False
    chiunque = w.Regola(2, 1, "chiunque", 10, "chiudi")
    assert _scatta(chiunque, ultima_attivita=_min(95), ultimo_utente=_min(0), adesso=_min(100)) is False
    assert _scatta(chiunque, ultima_attivita=_min(80), adesso=_min(100)) is True


def test_una_volta_sola_finche_nessuno_scrive_e_poi_si_riarma():
    r = w.Regola(1, 1, "utente", 10, "messaggio", "ciao", ripeti=False)
    assert _scatta(r, ultimo_utente=_min(0), ultima_esecuzione=_min(10), adesso=_min(500)) is False
    assert _scatta(r, ultimo_utente=_min(300), ultima_esecuzione=_min(10), adesso=_min(320)) is True


def test_a_ripetizione_riscatta_ogni_intervallo():
    r = w.Regola(1, 1, "utente", 10, "messaggio", "ciao", ripeti=True)
    assert _scatta(r, ultimo_utente=_min(0), ultima_esecuzione=_min(10), adesso=_min(19)) is False
    assert _scatta(r, ultimo_utente=_min(0), ultima_esecuzione=_min(10), adesso=_min(20)) is True


def test_attesa_scatta_dopo_lo_staff_e_non_prima_della_pausa():
    k = dict(attesa_minuti=30, in_attesa=False, ultimo_utente=_min(0), ultimo_staff=_min(10), spostato_at=None)
    assert w.da_mettere_in_attesa(**k, adesso=_min(39)) is False
    assert w.da_mettere_in_attesa(**k, adesso=_min(40)) is True
    assert w.da_mettere_in_attesa(**{**k, "ultimo_utente": _min(20)}, adesso=_min(100)) is False  # l'utente ha scritto dopo
    assert w.da_mettere_in_attesa(**{**k, "in_attesa": True}, adesso=_min(100)) is False
    assert w.da_mettere_in_attesa(**{**k, "attesa_minuti": 0}, adesso=_min(100)) is False
    assert w.da_mettere_in_attesa(**{**k, "spostato_at": _min(35)}, adesso=_min(40)) is False  # 1 ogni 10 minuti


def test_ritorno_quando_l_utente_scrive_dopo_l_attesa():
    k = dict(in_attesa=True, in_attesa_da=_min(40), ultimo_utente=_min(50), spostato_at=_min(40))
    assert w.da_riportare_indietro(**k, adesso=_min(55)) is True
    assert w.da_riportare_indietro(**k, adesso=_min(45)) is False  # pausa di 10 minuti
    assert w.da_riportare_indietro(**{**k, "ultimo_utente": _min(30)}, adesso=_min(90)) is False
    assert w.da_riportare_indietro(**{**k, "in_attesa": False}, adesso=_min(90)) is False


def test_riserva_un_canale_per_giro_e_categoria_con_posto():
    assert w.canali_da_creare(3, 1) == 1
    assert w.canali_da_creare(3, 3) == 0
    assert w.canali_da_creare(9, 0) == 1 and w.canali_da_creare(0, 0) == 0
    assert w.categoria_con_posto(49) and not w.categoria_con_posto(50)


# ====================================================================
# Repository
# ====================================================================
@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    ticket_opzioni_repo._cache.clear()
    yield


async def _ticket(panel_id, canale=5001):
    await ticket_repo.create_ticket(GUILD, 20, canale, panel_id=panel_id, ticket_number=1)
    return (await ticket_repo.get_ticket_by_channel(canale)).id


async def _pannello(nome="Supporto"):
    return await ticket_form_repo.crea_pannello(GUILD, nome, 900, nome)


async def test_al_massimo_5_regole_per_pannello():
    p = await _pannello()
    for i in range(5):
        await repo.aggiungi_regola(p.id, "utente", 10 + i, "chiudi", None, False)
    with pytest.raises(TroppeRegole):
        await repo.aggiungi_regola(p.id, "utente", 99, "chiudi", None, False)
    regole = await repo.regole(p.id)
    assert len(regole) == 5
    assert await repo.togli_regola(p.id, regole[0].id)
    assert not await repo.togli_regola(p.id, regole[0].id)
    assert len(await repo.regole(p.id)) == 4


async def test_stato_di_scrittura_attesa_e_ritorno():
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, attesa_minuti=30, attesa_categoria_id=777)
    t = await _ticket(p.id)
    await repo.segna_scritto(5001, False, _min(10))
    await repo.segna_scritto(5001, False, _min(5))  # più vecchio: ignorato
    await repo.segna_scritto(5001, True, _min(2))
    [riga] = await repo.da_controllare()
    assert riga["ultimo_staff_at"] == _min(10) and riga["ultimo_utente_at"] == _min(2)
    assert riga["attesa_minuti"] == 30 and riga["attesa_categoria_id"] == 777
    await repo.segna_attesa(t, 900, _min(40))
    [riga] = await repo.da_controllare()
    assert riga["in_attesa_da"] == _min(40) and riga["categoria_prima_attesa"] == 900
    await repo.segna_ritorno(t, _min(60))
    [riga] = await repo.da_controllare()
    assert riga["in_attesa_da"] is None and riga["spostato_at"] == _min(60)


async def test_regole_eseguite_ricordate_per_ticket():
    p = await _pannello()
    t = await _ticket(p.id)
    r = await repo.aggiungi_regola(p.id, "utente", 10, "messaggio", "ciao", True)
    assert await repo.eseguite(t) == {}
    await repo.segna_eseguita(t, r.id, _min(5))
    await repo.segna_eseguita(t, r.id, _min(15))
    assert await repo.eseguite(t) == {r.id: _min(15)}
    assert [x["id"] for x in await repo.da_controllare()] == [t]


async def test_ticket_senza_attesa_ne_regole_non_si_controlla():
    p = await _pannello()
    await ticket_repo.create_ticket(GUILD, 20, 5001, panel_id=p.id, ticket_number=1)
    assert await repo.da_controllare() == []


async def test_riserva_si_prende_il_piu_vecchio_una_volta_sola():
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, riserva_canali=2)
    assert (await repo.pannelli_con_riserva())[0]["presenti"] == 0
    await repo.aggiungi_riserva(1, GUILD, p.id)
    await repo.aggiungi_riserva(2, GUILD, p.id)
    assert (await repo.pannelli_con_riserva())[0]["presenti"] == 2
    assert await repo.prendi_riserva(p.id) == 1
    assert await repo.prendi_riserva(p.id) == 2
    assert await repo.prendi_riserva(p.id) is None


# ====================================================================
# Giro periodico (cog) con Discord finto
# ====================================================================
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord

import cogs.tickets.tickets as modulo_ticket
from cogs.tickets.inattivita import TicketInattivitaCog
from tests.support.discord_fakes import fake_text_channel


def _categoria(cat_id, n_canali=0):
    c = create_autospec(discord.CategoryChannel, instance=True)
    c.id = cat_id
    c.channels = [object()] * n_canali
    c.create_text_channel = AsyncMock(side_effect=lambda **k: fake_text_channel(7000 + len(c.channels) + 1, k["name"]))
    return c


class _Io:
    id = 1


def _scena(*canali, tickets_cog=None):
    per_id = {c.id: c for c in canali}
    guild = SimpleNamespace(id=GUILD, get_channel=per_id.get, get_channel_or_thread=per_id.get, me=_Io(), default_role=object())
    bot = SimpleNamespace(get_guild=lambda g: guild if g == GUILD else None,
                          get_cog=lambda n: tickets_cog if n == "TicketsCog" else None)
    cog = TicketInattivitaCog.__new__(TicketInattivitaCog)
    cog.bot = bot
    cog._regole = {}
    cog._dopo_id = 0
    return cog, guild


def _canale_ticket(cat_id=900, canale_id=5001):
    c = fake_text_channel(canale_id, "ticket-0001")
    c.__class__ = discord.TextChannel  # isinstance(..., TextChannel) vero
    c.category_id = cat_id
    c.edit = AsyncMock()
    c.send = AsyncMock()
    return c


NOW = datetime.now(timezone.utc)


def _fa(minuti):
    return NOW - timedelta(minutes=minuti)


async def test_giro_mette_in_attesa_e_riporta_indietro():
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, attesa_minuti=30, attesa_categoria_id=777)
    t = await _ticket(p.id)
    ch, attesa = _canale_ticket(), _categoria(777)
    cog, _ = _scena(ch, attesa, _categoria(900))
    await repo.segna_scritto(5001, False, _fa(40))
    await cog.controlla_ticket(NOW)
    ch.edit.assert_awaited_once()
    assert ch.edit.await_args.kwargs["category"] is attesa
    [riga] = await repo.da_controllare()
    assert riga["in_attesa_da"] is not None and riga["categoria_prima_attesa"] == 900
    # L'utente risponde dopo lo spostamento: dopo la pausa di 10 minuti torna indietro.
    ch.edit.reset_mock()
    prima = _categoria(900)
    cog, _ = _scena(ch, attesa, prima)
    await repo.segna_scritto(5001, True, NOW + timedelta(minutes=2))
    await cog.controlla_ticket(NOW + timedelta(minutes=5))
    ch.edit.assert_not_awaited()  # troppo presto: 1 spostamento ogni 10 minuti
    await cog.controlla_ticket(NOW + timedelta(minutes=12))
    assert ch.edit.await_args.kwargs["category"] is prima
    assert (await repo.da_controllare())[0]["in_attesa_da"] is None


async def test_categoria_in_attesa_piena_non_sposta():
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, attesa_minuti=30, attesa_categoria_id=777)
    await _ticket(p.id)
    ch = _canale_ticket()
    cog, _ = _scena(ch, _categoria(777, 50))
    await repo.segna_scritto(5001, False, _fa(40))
    await cog.controlla_ticket(NOW)
    ch.edit.assert_not_awaited()
    assert (await repo.da_controllare())[0]["in_attesa_da"] is None


async def test_regola_messaggio_una_volta_e_regola_chiudi():
    p = await _pannello()
    await _ticket(p.id)
    await repo.aggiungi_regola(p.id, "utente", 30, "messaggio", "Ci sei {utente}?", False)
    ch = _canale_ticket()
    cog, _ = _scena(ch)
    await repo.segna_scritto(5001, True, _fa(40))
    await cog.controlla_ticket(NOW)
    await cog.controlla_ticket(NOW + timedelta(minutes=5))
    ch.send.assert_awaited_once()
    assert ch.send.await_args.args[0] == "Ci sei <@20>?"

    chiudi = AsyncMock(return_value=True)
    tickets_cog = SimpleNamespace(_chiudi_da_sistema=chiudi, _pianifica_eliminazione_canale=AsyncMock())
    await repo.aggiungi_regola(p.id, "utente", 60, "elimina", None, False)
    cog, guild = _scena(ch, tickets_cog=tickets_cog)
    await cog.controlla_ticket(NOW + timedelta(minutes=30))  # utente fermo da 70 minuti
    chiudi.assert_awaited_once()
    tickets_cog._pianifica_eliminazione_canale.assert_awaited_once()


async def test_riserva_si_rifornisce_un_canale_per_giro_e_si_svuota():
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, riserva_canali=2)
    cat = _categoria(900)
    cog, _ = _scena(cat)
    await cog.rifornisci_riserva()
    assert cat.create_text_channel.await_count == 1
    cat.create_text_channel.side_effect = lambda **k: fake_text_channel(7100, k["name"])
    await cog.rifornisci_riserva()
    assert (await repo.pannelli_con_riserva())[0]["presenti"] == 2
    await cog.rifornisci_riserva()
    assert cat.create_text_channel.await_count == 2  # a riserva piena non crea
    # Riserva spenta: i canali pronti si eliminano.
    await ticket_opzioni_repo.imposta(p.id, riserva_canali=0)
    pronto = fake_text_channel(7001, "ticket-pronto")
    pronto.delete = AsyncMock()
    cog, _ = _scena(cat, pronto)
    await cog.rifornisci_riserva()
    pronto.delete.assert_awaited_once()


async def test_aprire_un_ticket_usa_il_canale_della_riserva():
    p = await _pannello()
    await repo.aggiungi_riserva(7001, GUILD, p.id)
    pronto = fake_text_channel(7001, "ticket-pronto")
    pronto.__class__ = discord.TextChannel
    pronto.category_id = 900
    pronto.edit = AsyncMock()
    guild = SimpleNamespace(get_channel=lambda i: pronto if i == 7001 else None)
    cat = SimpleNamespace(id=900)
    ow = {"x": 1}
    canale = await modulo_ticket._canale_dalla_riserva(guild, cat, p.id, "ticket-0001", ow, "m")
    assert canale is pronto
    pronto.edit.assert_awaited_once_with(name="ticket-0001", overwrites=ow, reason="m")
    assert await modulo_ticket._canale_dalla_riserva(guild, cat, p.id, "ticket-0002", ow, "m") is None
    # Categoria diversa: il canale pronto non si usa.
    await repo.aggiungi_riserva(7001, GUILD, p.id)
    assert await modulo_ticket._canale_dalla_riserva(guild, SimpleNamespace(id=901), p.id, "n", ow, "m") is None


async def test_il_giro_arriva_anche_ai_ticket_oltre_il_tetto(monkeypatch):
    """Con più ticket del tetto per giro, il giro dopo riparte da dove si era fermato (prima: sempre i primi)."""
    import cogs.tickets.inattivita as inattivita

    monkeypatch.setattr(inattivita, "MAX_TICKET_PER_GIRO", 2)
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, attesa_minuti=30, attesa_categoria_id=777)
    canali = []
    for i in range(3):
        await ticket_repo.create_ticket(GUILD, 20 + i, 5001 + i, panel_id=p.id, ticket_number=i + 1)
        canali.append(_canale_ticket(canale_id=5001 + i))
    cog, _ = _scena(*canali)
    visti = []

    async def _un_ticket(riga, adesso):
        visti.append(riga["channel_id"])

    cog._un_ticket = _un_ticket
    await cog.controlla_ticket(NOW)
    await cog.controlla_ticket(NOW)
    assert 5003 in visti


async def test_un_ticket_appena_riaperto_non_si_richiude_subito():
    """Riaprire un ticket fermo da ore non deve farlo chiudere al giro dopo da una regola di inattività."""
    p = await _pannello()
    t = await _ticket(p.id)
    await repo.aggiungi_regola(p.id, "chiunque", 60, "chiudi", None, False)
    await repo.aggiungi_regola(p.id, "utente", 60, "chiudi", None, False)
    vecchio = NOW - timedelta(hours=5)
    await db.pool.execute(
        "UPDATE tickets SET created_at = $2, last_activity_at = $2, ultimo_utente_at = $2 WHERE id = $1", t, vecchio
    )
    assert await ticket_repo.close_ticket(5001, 1)
    assert await ticket_repo.riapri(5001)
    chiudi = AsyncMock(return_value=True)
    tickets_cog = SimpleNamespace(_chiudi_da_sistema=chiudi, _pianifica_eliminazione_canale=AsyncMock())
    cog, _ = _scena(_canale_ticket(), tickets_cog=tickets_cog)
    await cog.controlla_ticket(datetime.now(timezone.utc) + timedelta(minutes=2))
    chiudi.assert_not_awaited()
    await cog.controlla_ticket(datetime.now(timezone.utc) + timedelta(minutes=61))
    chiudi.assert_awaited()

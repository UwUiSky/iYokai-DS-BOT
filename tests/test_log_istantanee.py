"""
tests/test_log_istantanee.py
============================
LOG-028 (#119): istantanee di un canale sul pannello web. Segreto mai salvato, accesso ricontrollato a ogni
apertura, tetto e scadenza, testo pulito, cancellazione con l'autore e con il server.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import jinja2
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import cogs.logging.istantanee as modulo
from core import data_registry, web_panel_istantanee as web_istantanee
from core import log_istantanee_logic as logica
from core.message_log_logic import Ignorati, MessaggioArchiviato
from core.repositories.log_istantanee_repo import LogIstantaneeRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

SERVER = 920
ALTRO = 921
PAROLA = "x" * 43


def _msg(i, testo="ciao", autore=42, nome="mario", quando="2026-11-18 10:00:00"):
    return MessaggioArchiviato(message_id=i, author_id=autore, author_nome=nome, testo=testo, quando=quando)


def _riga(i, testo="ciao", autore=42):
    return {"message_id": i, "author_id": autore, "autore_nome": "mario", "quando": "2026-11-18 10:00", "testo": testo, "cancellato": False}


# ------------------------------------------------------------------ logica
def test_log028_il_segreto_e_lungo_casuale_e_si_salva_solo_l_impronta():
    a, b = logica.nuovo_segreto(), logica.nuovo_segreto()
    assert a != b and len(a) == logica.TOKEN_LUNGHEZZA and logica.segreto_valido(a)
    assert len(logica.impronta(a)) == 64 and a not in logica.impronta(a)
    for male in ("", "x" * 42, "x" * 44, "x" * 42 + "/", "x" * 42 + "'", None):
        assert not logica.segreto_valido(male)


@pytest.mark.parametrize(
    "accesso,role,gestore,membro,ruoli,atteso",
    [
        ("gestori", None, True, True, frozenset(), True),
        ("gestori", None, False, True, frozenset({5}), False),
        ("ruolo", 5, False, True, frozenset({5}), True),
        ("ruolo", 5, False, True, frozenset({6}), False),
        ("ruolo", 5, False, False, frozenset({5}), False),  # il ruolo non basta se non e' nel server
        ("ruolo", None, False, True, frozenset({5}), False),
        ("membri", None, False, True, frozenset(), True),
        ("membri", None, False, False, frozenset(), False),
        ("pubblico", None, False, True, frozenset({5}), False),  # valore sconosciuto: chiuso
        ("pubblico", None, True, True, frozenset(), True),
    ],
)
def test_log028_chi_puo_vedere(accesso, role, gestore, membro, ruoli, atteso):
    assert logica.puo_vedere(accesso, role, e_gestore=gestore, e_membro=membro, ruoli_membro=ruoli) is atteso


def test_log028_le_righe_vanno_in_ordine_i_cancellati_sono_segnati_e_il_testo_e_pulito():
    righe = logica.righe_istantanea(
        [_msg(5, "due"), _msg(1, "uno‮TXT\x00ok", nome="Ma‮rio")], [_msg(3, "perso")]
    )
    assert [r["message_id"] for r in righe] == [1, 3, 5]
    assert [r["cancellato"] for r in righe] == [False, True, False]
    assert righe[0]["testo"] == "unoTXTok" and righe[0]["autore_nome"] == "Mario"


def test_log028_testi_e_nomi_lunghi_si_tagliano_e_l_istantanea_ha_un_peso_massimo():
    r = logica.righe_istantanea([_msg(1, "x" * 5000, nome="n" * 500)], [])[0]
    assert len(r["testo"]) <= logica.TESTO_RIGA_MAX and len(r["autore_nome"]) <= logica.NOME_AUTORE_MAX
    molti = [_msg(i, "y" * 2000) for i in range(1, 2000)]
    righe = logica.righe_istantanea(molti, [])
    assert 0 < len(righe) < len(molti)
    assert sum(len(x["testo"].encode()) for x in righe) <= logica.BYTE_TOTALI_MAX


# ------------------------------------------------------------------ database vero
@pytest.fixture
def repo(clean_db):
    return LogIstantaneeRepository(pool_provider=lambda: clean_db)


async def _crea(repo, guild=SERVER, segreto=None, accesso="gestori", role=None, righe=None, giorni=3, massimo=5):
    segreto = segreto or logica.nuovo_segreto()
    nuova = await repo.crea(
        guild, 11, "generale", 42, giorni, accesso, role, logica.impronta(segreto), righe or [_riga(1)], massimo
    )
    return nuova, segreto


async def test_log028_si_trova_solo_con_l_impronta_del_segreto_e_il_segreto_non_e_nel_database(repo, clean_db):
    nuova, segreto = await _crea(repo, righe=[_riga(1, "ciao"), _riga(2, "mondo")])
    trovata = await repo.per_impronta(logica.impronta(segreto))
    assert trovata.id == nuova and trovata.guild_id == SERVER and trovata.accesso == "gestori"
    assert [r["testo"] for r in await repo.righe(nuova)] == ["ciao", "mondo"]
    assert await repo.per_impronta(logica.impronta(segreto + "a")) is None
    assert await repo.per_impronta(segreto) is None  # il segreto in chiaro non e' una chiave
    righe = await clean_db.fetch("SELECT * FROM log_istantanee")
    assert all(segreto not in str(v) for r in righe for v in r.values())


async def test_log028_scaduta_non_si_apre_e_la_pulizia_la_toglie_con_le_sue_righe(repo, clean_db):
    nuova, segreto = await _crea(repo)
    await clean_db.execute("UPDATE log_istantanee SET scade_il = now() - interval '1 minute' WHERE id=$1", nuova)
    assert await repo.per_impronta(logica.impronta(segreto)) is None
    assert await repo.elenco(SERVER) == []
    assert await repo.pulisci_scadute() == 1
    assert await clean_db.fetchval("SELECT count(*) FROM log_istantanee_righe") == 0


async def test_log028_tetto_per_server_anche_con_richieste_insieme(repo):
    esiti = await asyncio.gather(*[_crea(repo, massimo=5) for _ in range(9)])
    assert sum(1 for n, _ in esiti if n is not None) == 5
    altro, _ = await _crea(repo, guild=ALTRO, massimo=5)  # un altro server ha il suo tetto
    assert altro is not None


async def test_log028_un_server_non_toglie_ne_vede_le_istantanee_di_un_altro(repo):
    mia, _ = await _crea(repo, guild=SERVER)
    altrui, _ = await _crea(repo, guild=ALTRO)
    assert not await repo.revoca(SERVER, altrui)
    assert [i.id for i in await repo.elenco(ALTRO)] == [altrui]
    assert await repo.revoca(SERVER, mia) and not await repo.revoca(SERVER, mia)


async def test_log028_il_database_rifiuta_ruolo_senza_ruolo_e_accesso_sconosciuto(repo):
    import asyncpg

    with pytest.raises(asyncpg.CheckViolationError):
        await _crea(repo, accesso="ruolo", role=None)
    with pytest.raises(asyncpg.CheckViolationError):
        await _crea(repo, accesso="tutti")


async def test_log028_le_righe_di_un_autore_si_cancellano_con_la_richiesta_privacy_e_col_server(repo, clean_db):
    nuova, _ = await _crea(repo, righe=[_riga(1, "mio", autore=42), _riga(2, "altrui", autore=43)])
    tabelle = {t.nome: t for t in data_registry.REGISTRO}
    righe = tabelle["log_istantanee_righe"]
    await clean_db.execute(righe.sql_cancella_utente(), 42)
    assert [r["testo"] for r in await repo.righe(nuova)] == ["altrui"]
    for nome in ("log_istantanee_righe", "log_istantanee"):
        await clean_db.execute(tabelle[nome].sql_cancella_server(), SERVER)
    assert await clean_db.fetchval("SELECT count(*) FROM log_istantanee") == 0
    assert await clean_db.fetchval("SELECT count(*) FROM log_istantanee_righe") == 0


# ------------------------------------------------------------------ pagina web
def _app(repo, monkeypatch, utente, gestibile=True, membro=None, fetch=None, guild_presente=True):
    monkeypatch.setattr(web_istantanee, "log_istantanee_repo", repo)
    guild = fake_guild(guild_id=SERVER, name="Server <b>X</b>")
    guild.get_member = MagicMock(return_value=membro)
    guild.fetch_member = AsyncMock(side_effect=fetch if fetch is not None else discord.NotFound(MagicMock(status=404, reason="x"), "x"))
    bot = SimpleNamespace(get_guild=lambda gid: guild if guild_presente and gid == SERVER else None)
    ponte = SimpleNamespace(server_gestibile=AsyncMock(return_value=guild if gestibile else None))
    ambiente = jinja2.Environment(loader=jinja2.FileSystemLoader("pannello_web/templates"), autoescape=True)

    def pagina(request, modello, codice_http=200, **dati):
        return web.Response(text=ambiente.get_template(modello).render(utente_id=1, csrf="", **dati), content_type="text/html", status=codice_http)

    def errore(request, codice, titolo, testo):
        return web.Response(text=f"{titolo}|{testo}", status=codice)

    chiave = web.RequestKey("utente_id", int)

    @web.middleware
    async def sessione(request, handler):
        if utente is not None:
            request[chiave] = utente
        return await handler(request)

    app = web.Application(middlewares=[sessione])
    web_istantanee.registra_rotte(app, bot=bot, ponte=ponte, pagina=pagina, errore=errore, chiave_utente=chiave)
    return app, guild


async def test_log028_la_pagina_mostra_i_messaggi_con_l_html_neutralizzato(repo, monkeypatch):
    _, segreto = await _crea(repo, righe=[_riga(1, "<script>alert(1)</script> [x](http://a)")])
    app, _ = _app(repo, monkeypatch, utente=7)
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get(f"/istantanea/{segreto}", allow_redirects=False)
        testo = await risposta.text()
    assert risposta.status == 200
    assert "<script>" not in testo and "&lt;script&gt;" in testo and "Server &lt;b&gt;X&lt;/b&gt;" in testo


async def test_log028_senza_accesso_con_discord_manda_ad_accedi(repo, monkeypatch):
    _, segreto = await _crea(repo)
    app, _ = _app(repo, monkeypatch, utente=None)
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get(f"/istantanea/{segreto}", allow_redirects=False)
    assert risposta.status == 302 and risposta.headers["Location"] == "/accedi"


async def test_log028_segreto_sbagliato_scaduto_o_accesso_negato_danno_la_stessa_risposta(repo, monkeypatch):
    nuova, segreto = await _crea(repo, accesso="gestori")
    app, _ = _app(repo, monkeypatch, utente=7, gestibile=False, membro=fake_member(user_id=7))
    async with TestClient(TestServer(app)) as client:
        negato = await (await client.get(f"/istantanea/{segreto}")).text()
        sbagliato = await (await client.get(f"/istantanea/{'y' * 43}")).text()
        storto = await client.get("/istantanea/corto")
    assert negato == sbagliato and storto.status == 404
    app, _ = _app(repo, monkeypatch, utente=7)
    await repo._pool.execute("UPDATE log_istantanee SET scade_il = now() - interval '1 second' WHERE id=$1", nuova)
    async with TestClient(TestServer(app)) as client:
        scaduto = await (await client.get(f"/istantanea/{segreto}")).text()
    assert scaduto == negato


async def test_log028_il_ruolo_si_ricontrolla_ad_ogni_apertura(repo, monkeypatch):
    _, segreto = await _crea(repo, accesso="ruolo", role=5)
    con = fake_member(user_id=7, roles=[SimpleNamespace(id=5)])
    senza = fake_member(user_id=7, roles=[SimpleNamespace(id=6)])
    for membro, stato in ((con, 200), (senza, 404)):
        app, _ = _app(repo, monkeypatch, utente=7, gestibile=False, membro=membro)
        async with TestClient(TestServer(app)) as client:
            assert (await client.get(f"/istantanea/{segreto}")).status == stato


async def test_log028_membri_con_il_link_ma_non_nel_server_o_con_discord_che_non_risponde_restano_fuori(repo, monkeypatch):
    _, segreto = await _crea(repo, accesso="membri")
    app, _ = _app(repo, monkeypatch, utente=7, gestibile=False, membro=fake_member(user_id=7))
    async with TestClient(TestServer(app)) as client:
        assert (await client.get(f"/istantanea/{segreto}")).status == 200
    for errore_discord in (discord.NotFound(MagicMock(status=404, reason="x"), "x"), discord.HTTPException(MagicMock(status=500, reason="x"), "x")):
        app, _ = _app(repo, monkeypatch, utente=7, gestibile=False, membro=None, fetch=errore_discord)
        async with TestClient(TestServer(app)) as client:
            assert (await client.get(f"/istantanea/{segreto}")).status == 404


async def test_log028_server_sparito_dalla_memoria_del_bot_non_si_apre(repo, monkeypatch):
    _, segreto = await _crea(repo)
    app, _ = _app(repo, monkeypatch, utente=7, guild_presente=False)
    async with TestClient(TestServer(app)) as client:
        assert (await client.get(f"/istantanea/{segreto}")).status == 404


async def test_log028_troppe_aperture_di_fila_si_fermano(repo, monkeypatch):
    _, segreto = await _crea(repo)
    app, _ = _app(repo, monkeypatch, utente=7)
    async with TestClient(TestServer(app)) as client:
        codici = [(await client.get(f"/istantanea/{segreto}")).status for _ in range(35)]
    assert codici[0] == 200 and 429 in codici


# ------------------------------------------------------------------ comando
@pytest.fixture
def ambiente(repo, monkeypatch):
    monkeypatch.setattr(modulo, "log_istantanee_repo", repo)
    monkeypatch.setattr(modulo, "config", SimpleNamespace(WEB_PANEL_PUBLIC_URL="https://pannello.example.invalid/"))
    ignora = MagicMock()
    ignora.carica = AsyncMock(return_value=Ignorati())
    monkeypatch.setattr(modulo, "log_ignora_repo", ignora)
    monkeypatch.setattr(modulo, "event_log_repo", MagicMock(log_event=AsyncMock()))
    monkeypatch.setattr(modulo.log_eventi_repo, "evento_acceso", AsyncMock(return_value=True))
    server = fake_guild(guild_id=SERVER)
    canale = fake_text_channel(11, "generale")
    canale.guild = server
    canale.category_id = None
    canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True, read_message_history=True))

    async def storia(limit):
        for i in (3, 2, 1):
            m = MagicMock()
            m.id, m.content = i, f"messaggio {i}"
            m.author = fake_member(user_id=42, name="mario")
            m.attachments, m.created_at = [], datetime(2026, 11, 18, 10, tzinfo=timezone.utc)
            yield m

    canale.history = storia
    return modulo.LogIstantaneeCog(bot=MagicMock()), server, canale


async def test_log028_il_comando_crea_con_link_mostrato_una_volta_e_segreto_solo_come_impronta(ambiente, repo, clean_db):
    cog, server, canale = ambiente
    ix = fake_interaction(guild=server)
    await cog.istantanea.callback(cog, ix, "crea", canale, 100, 3, "gestori", None, None)
    testo = ix.followup.send.call_args.args[0]
    assert "https://pannello.example.invalid/istantanea/" in testo and ix.followup.send.call_args.kwargs["ephemeral"] is True
    segreto = testo.split("/istantanea/")[1].split()[0]
    assert logica.segreto_valido(segreto)
    attive = await repo.elenco(SERVER)
    assert len(attive) == 1 and [r["testo"] for r in await repo.righe(attive[0].id)] == ["messaggio 1", "messaggio 2", "messaggio 3"]
    assert all(segreto not in str(v) for r in await clean_db.fetch("SELECT * FROM log_istantanee") for v in r.values())
    modulo.event_log_repo.log_event.assert_awaited_once()
    assert segreto not in str(modulo.event_log_repo.log_event.await_args)


async def test_log028_il_comando_rifiuta_senza_pannello_senza_permessi_ruolo_giusto_e_canale_ignorato(ambiente, repo, monkeypatch):
    cog, server, canale = ambiente
    ix = fake_interaction(guild=server)
    monkeypatch.setattr(modulo, "config", SimpleNamespace(WEB_PANEL_PUBLIC_URL=""))
    await cog.istantanea.callback(cog, ix, "crea", canale, 100, 3, "gestori", None, None)
    assert "indirizzo pubblico" in ix.response.send_message.call_args.args[0]
    monkeypatch.setattr(modulo, "config", SimpleNamespace(WEB_PANEL_PUBLIC_URL="https://p.example.invalid"))
    await cog.istantanea.callback(cog, ix, "crea", canale, 100, 3, "ruolo", None, None)  # ruolo mancante
    tutti = MagicMock()
    tutti.guild, tutti.is_default = server, lambda: True
    await cog.istantanea.callback(cog, ix, "crea", canale, 100, 3, "ruolo", tutti, None)  # @everyone
    canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=False))
    await cog.istantanea.callback(cog, ix, "crea", canale, 100, 3, "gestori", None, None)  # l'utente non lo legge
    canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True, read_message_history=True))
    modulo.log_ignora_repo.carica = AsyncMock(return_value=Ignorati(canali=frozenset({11})))
    await cog.istantanea.callback(cog, ix, "crea", canale, 100, 3, "gestori", None, None)  # canale ignorato dai log
    assert await repo.elenco(SERVER) == []
    ix.followup.send.assert_not_called()


async def test_log028_il_comando_elenca_e_toglie_e_rispetta_il_tetto(ambiente, repo):
    cog, server, canale = ambiente
    ix = fake_interaction(guild=server)
    for _ in range(modulo.ATTIVE_MAX_PER_SERVER):
        await cog.istantanea.callback(cog, ix, "crea", canale, 10, 1, "gestori", None, None)
    await cog.istantanea.callback(cog, ix, "crea", canale, 10, 1, "gestori", None, None)
    assert "5" in ix.followup.send.call_args.args[0] and len(await repo.elenco(SERVER)) == 5
    await cog.istantanea.callback(cog, ix, "elenco", None, 1, 1, "gestori", None, None)
    assert ix.response.send_message.call_args.args[0].count("<#11>") == 5
    primo = (await repo.elenco(SERVER))[0].id
    await cog.istantanea.callback(cog, ix, "revoca", None, 1, 1, "gestori", None, primo)
    assert len(await repo.elenco(SERVER)) == 4
    await cog.istantanea.callback(cog, ix, "revoca", None, 1, 1, "gestori", None, None)  # senza numero: non toglie niente
    assert len(await repo.elenco(SERVER)) == 4


async def test_log028_lettura_fallita_non_crea_niente(ambiente, repo):
    cog, server, canale = ambiente

    async def rotta(limit):
        raise discord.HTTPException(MagicMock(status=500, reason="x"), "x")
        yield  # pragma: no cover

    canale.history = rotta
    ix = fake_interaction(guild=server)
    await cog.istantanea.callback(cog, ix, "crea", canale, 10, 1, "gestori", None, None)
    assert await repo.elenco(SERVER) == []


def test_log028_i_limiti_dei_comandi_stanno_in_discord():
    assert logica.MESSAGGI_MAX <= 200 and logica.GIORNI_MAX == 7 and logica.ATTIVE_MAX_PER_SERVER == 5
    assert len(modulo.AZIONI) <= 25 and len(modulo.ACCESSI) <= 25

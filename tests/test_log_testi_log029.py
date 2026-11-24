"""
tests/test_log_testi_log029.py
==============================
LOG-029 (D122): il testo dei messaggi dei canali registrati si salva SOLO cifrato, a lotti, in una finestra di 7 giorni;
a ogni sanzione i messaggi dell'utente degli ultimi 3 giorni si copiano cifrati nell'archivio del caso; la pagina del
pannello li decifra solo all'apertura, per lo staff autorizzato, con escape e CSP senza script. Database vero.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.logging.message_logs as modulo
from core import log_testi_logic as logica, log_testi_servizio as servizio, moderation_archivio_utente as arc, panel_bridge
from core.database import db
from core.message_log_logic import Ignorati
from core.oauth_crypto import generate_key
from core.retention_worker import pulisci_scaduti
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel
from tests.test_web_panel_server import ADMIN, GUILD, _client, _entra, ambiente  # noqa: F401
import core.database as database_module

G, U, ALTRO, CANALE = 910001, 920001, 920002, 11
SEGRETO = "password del wifi: ZZ-segreto-4242"


@pytest.fixture
def chiave(monkeypatch):
    k = generate_key()
    monkeypatch.setattr(servizio, "config", SimpleNamespace(LOG_TESTI_KEY=k, TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY=""))
    monkeypatch.setattr(servizio, "coda", servizio.CodaTesti())
    return k


@pytest.fixture
async def amb(monkeypatch, clean_db, chiave):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    return clean_db


def _allegato(nome="foto.png", tipo="image/png", peso=2048):
    return SimpleNamespace(filename=nome, content_type=tipo, size=peso, url="https://cdn.discordapp.com/x", read=None)


# ------------------------------------------------------------ cifratura
async def test_il_testo_e_salvato_cifrato_e_mai_in_chiaro(amb, chiave):
    assert servizio.coda.accoda(G, CANALE, 70, U, "creato", SEGRETO, [_allegato()])
    assert len(servizio.coda) == 1  # ancora in memoria: nessuna scrittura per messaggio
    assert await amb.fetchval("SELECT count(*) FROM log_messaggi_testi") == 0
    assert await servizio.coda.svuota() == 1
    righe = await amb.fetch("SELECT * FROM log_messaggi_testi")
    assert len(righe) == 1
    assert "ZZ-segreto" not in "|".join(str(v) for v in righe[0].values())
    assert "foto.png" not in str(righe[0]["cifrato"])
    testo, allegati = logica.apri_riga(righe[0]["cifrato"], G, 70, U, "creato", chiave)
    assert testo == SEGRETO
    assert allegati == [{"nome": "foto.png", "tipo": "image/png", "peso": 2048}]  # D74: solo nome, tipo e peso
    assert "cdn.discordapp" not in str(allegati)


async def test_senza_chiave_non_si_salva_niente(amb, monkeypatch):
    monkeypatch.setattr(servizio, "config", SimpleNamespace(LOG_TESTI_KEY="", TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY=""))
    coda = servizio.CodaTesti()
    assert servizio.attivo() is False
    assert coda.accoda(G, CANALE, 70, U, "creato", SEGRETO) is False
    assert await coda.svuota() == 0
    assert await amb.fetchval("SELECT count(*) FROM log_messaggi_testi") == 0
    assert await servizio.testi_per_caso(G, 1, U) is None


def test_la_chiave_ripiega_su_quella_delle_trascrizioni_poi_su_oauth():
    c = SimpleNamespace
    assert logica.chiave_da_config(c(LOG_TESTI_KEY="a", TICKET_TRASCRIZIONI_KEY="b", OAUTH_ENCRYPTION_KEY="c")) == "a"
    assert logica.chiave_da_config(c(LOG_TESTI_KEY="", TICKET_TRASCRIZIONI_KEY="b", OAUTH_ENCRYPTION_KEY="c")) == "b"
    assert logica.chiave_da_config(c(LOG_TESTI_KEY="", TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY="c")) == "c"
    assert logica.chiave_da_config(c(LOG_TESTI_KEY=" ", TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY="")) == ""


def test_una_riga_copiata_altrove_non_si_apre(chiave):
    cifrato = logica.cifra_riga(G, 70, U, "creato", "ciao", [], chiave)
    assert logica.apri_riga(cifrato, G, 70, U, "creato", chiave)[0] == "ciao"
    assert logica.apri_riga(cifrato, G + 1, 70, U, "creato", chiave) is None  # altro server
    assert logica.apri_riga(cifrato, G, 71, U, "creato", chiave) is None  # altro messaggio
    assert logica.apri_riga(cifrato, G, 70, ALTRO, "creato", chiave) is None  # altro autore
    assert logica.apri_riga(cifrato, G, 70, U, "cancellato", chiave) is None
    assert logica.apri_riga(cifrato, G, 70, U, "creato", generate_key()) is None  # altra chiave


async def test_tetti_per_server_e_scrittura_a_lotti(amb, chiave, monkeypatch):
    monkeypatch.setattr(servizio, "MAX_IN_ATTESA_SERVER", 3)
    for i in range(10):
        servizio.coda.accoda(G, CANALE, 100 + i, U, "creato", f"m{i}")
    assert len(servizio.coda) == 3 and servizio.coda.scartate == 7
    assert servizio.coda.accoda(G + 1, CANALE, 5, U, "creato", "altro server")  # un altro server non e' toccato
    chiamate = []
    originale = servizio.log_testi_repo.inserisci_lotto

    async def conta(righe):
        chiamate.append(len(righe))
        await originale(righe)

    monkeypatch.setattr(servizio.log_testi_repo, "inserisci_lotto", conta)
    assert await servizio.coda.svuota() == 4
    assert chiamate == [4]  # un solo invio per tutto il lotto


async def test_la_potatura_tiene_al_massimo_n_righe_per_server(amb, chiave):
    for i in range(5):
        servizio.coda.accoda(G, CANALE, 200 + i, U, "creato", f"m{i}")
    servizio.coda.accoda(G + 1, CANALE, 300, U, "creato", "x")
    await servizio.coda.svuota()
    assert await servizio.log_testi_repo.pota_per_server(2) == 3
    assert await amb.fetchval("SELECT count(*) FROM log_messaggi_testi WHERE guild_id = $1", G) == 2
    assert await amb.fetchval("SELECT min(message_id) FROM log_messaggi_testi WHERE guild_id = $1", G) == 203  # le piu' recenti
    assert await amb.fetchval("SELECT count(*) FROM log_messaggi_testi WHERE guild_id = $1", G + 1) == 1


# ------------------------------------------------- finestra di 7 giorni e copia nel caso
async def _riga(amb, chiave, message_id, utente, giorni_fa, testo, guild=G, evento="creato"):
    cifrato = logica.cifra_riga(guild, message_id, utente, evento, testo, [], chiave)
    await amb.execute(
        "INSERT INTO log_messaggi_testi (guild_id, channel_id, message_id, user_id, evento, cifrato, creato) "
        "VALUES ($1,$2,$3,$4,$5,$6, now() - make_interval(days => $7))",
        guild, CANALE, message_id, utente, evento, cifrato, giorni_fa,
    )


async def test_la_finestra_e_di_7_giorni_dal_registro_dei_dati(amb, chiave):
    await _riga(amb, chiave, 1, U, 6, "dentro")
    await _riga(amb, chiave, 2, U, 8, "fuori")
    await pulisci_scaduti(amb)
    assert [r["message_id"] for r in await amb.fetch("SELECT message_id FROM log_messaggi_testi")] == [1]


async def test_a_ogni_sanzione_si_copiano_i_messaggi_degli_ultimi_3_giorni_cifrati(amb, chiave):
    await _riga(amb, chiave, 1, U, 1, "ieri <b>x</b>")
    await _riga(amb, chiave, 2, U, 2, "l'altro ieri", evento="modificato")
    await _riga(amb, chiave, 3, U, 5, "vecchio: dentro la finestra ma oltre i 3 giorni")
    await _riga(amb, chiave, 4, ALTRO, 1, "di un altro utente")
    await _riga(amb, chiave, 5, U, 1, "altro server", guild=G + 1)
    servizio.coda.accoda(G, CANALE, 6, U, "creato", "appena scritto, ancora in coda")
    assert await arc.salva(G, 7, U) == 0  # nessun evento nel registro, ma c'e' il testo
    r = await db.pool.fetchrow("SELECT testi_cifrato, testi_messaggi FROM moderation_archivio_utente WHERE case_number = 7")
    assert r["testi_messaggi"] == 3
    grezzo = r["testi_cifrato"]
    assert grezzo.startswith("v2.") and "appena scritto" not in grezzo and "l'altro ieri" not in grezzo  # cifrato
    utente, messaggi = await arc.leggi_testi(G, 7)
    assert utente == U
    assert sorted(m.testo for m in messaggi) == sorted(["ieri <b>x</b>", "l'altro ieri", "appena scritto, ancora in coda"])
    assert await arc.numero_testi(G, 7) == 3


async def test_la_copia_resta_finche_esiste_il_caso_anche_dopo_la_finestra(amb, chiave):
    await _riga(amb, chiave, 1, U, 1, "prova")
    await arc.salva(G, 8, U)
    await amb.execute("DELETE FROM log_messaggi_testi")  # la finestra scorre: l'originale sparisce
    await amb.execute("UPDATE moderation_archivio_utente SET creato = now() - interval '400 days'")
    assert [m.testo for m in (await arc.leggi_testi(G, 8))[1]] == ["prova"]  # la copia nel caso resta


async def test_l_archivio_del_caso_non_si_apre_su_un_altro_caso_o_server(amb, chiave):
    await _riga(amb, chiave, 1, U, 1, "prova")
    await arc.salva(G, 9, U)
    cifrato = await amb.fetchval("SELECT testi_cifrato FROM moderation_archivio_utente WHERE case_number = 9")
    assert logica.apri_archivio(cifrato, G, 9, chiave) is not None
    assert logica.apri_archivio(cifrato, G, 10, chiave) is None
    assert logica.apri_archivio(cifrato, G + 1, 9, chiave) is None
    assert logica.apri_archivio(cifrato, G, 9, generate_key()) is None


async def test_senza_chiave_l_archivio_non_ha_testo(amb, chiave, monkeypatch):
    await _riga(amb, chiave, 1, U, 1, "prova")
    monkeypatch.setattr(servizio, "config", SimpleNamespace(LOG_TESTI_KEY="", TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY=""))
    assert await arc.salva(G, 11, U) == 0
    assert await arc.leggi(G, 11) is None
    assert await arc.leggi_testi(G, 11) is None


async def test_la_cancellazione_su_richiesta_toglie_testi_e_archivio_di_quell_utente(amb, chiave):
    from core.data_registry import REGISTRO
    from core.forget_user_service import dimentica_utente, esporta_utente
    await _riga(amb, chiave, 1, U, 1, "mio")
    await _riga(amb, chiave, 2, ALTRO, 1, "di un altro")
    await arc.salva(G, 5, U)
    voci = {t.nome: t for t in REGISTRO}
    assert voci["log_messaggi_testi"].scadenza.giorni == 7 and "sicurezza e moderazione" in voci["log_messaggi_testi"].nota
    assert "base giuridica" in voci["moderation_archivio_utente"].nota
    esportato = await esporta_utente(amb, U)
    assert "testi_cifrato" not in str(esportato)  # il blob cifrato non esce nell'esportazione
    await dimentica_utente(amb, U)
    assert await amb.fetchval("SELECT count(*) FROM log_messaggi_testi WHERE user_id = $1", U) == 0
    assert await amb.fetchval("SELECT count(*) FROM log_messaggi_testi WHERE user_id = $1", ALTRO) == 1
    assert await amb.fetchval("SELECT count(*) FROM moderation_archivio_utente WHERE user_id = $1", U) == 0


async def test_la_cancellazione_del_server_toglie_le_righe_del_server(amb, chiave):
    from core.data_registry import REGISTRO
    sql = {t.nome: t.sql_cancella_server() for t in REGISTRO}
    assert sql["log_messaggi_testi"] and sql["moderation_archivio_utente"]  # chiusura del server: stesse regole di D6
    await _riga(amb, chiave, 1, U, 1, "x")
    await amb.execute(sql["log_messaggi_testi"], G)
    assert await amb.fetchval("SELECT count(*) FROM log_messaggi_testi") == 0


# ------------------------------------------------------------------ pagina
def test_la_pagina_ripulisce_ogni_testo_e_non_ha_script():
    from datetime import datetime, timezone
    m = logica.MessaggioArchivio(
        datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc), 11, 70, "creato",
        "<script>alert(1)</script> <img src=x onerror=alert(2)>", ({"nome": "<b>x</b>.png", "tipo": "image/png", "peso": 4096},),
    )
    pagina = logica.pagina_html([m], 7, U)
    assert "<script" not in pagina and "<img" not in pagina and "<b>x" not in pagina
    assert "&lt;script&gt;" in pagina and "&lt;b&gt;x&lt;/b&gt;.png" in pagina
    assert "script" not in logica.INTESTAZIONI_PAGINA["Content-Security-Policy"].replace("script-src", "")  # nessun permesso di script
    assert "default-src 'none'" in logica.INTESTAZIONI_PAGINA["Content-Security-Policy"]


BASE = f"/server/{GUILD}/moderazione/archivio"


@pytest.fixture
async def web(ambiente, clean_db, monkeypatch):  # noqa: F811
    k = generate_key()
    monkeypatch.setattr(servizio, "config", SimpleNamespace(LOG_TESTI_KEY=k, TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY=""))
    monkeypatch.setattr(servizio, "coda", servizio.CodaTesti())
    ambiente.k = k
    await _riga(clean_db, k, 1, U, 1, "<script>alert('x')</script> riservato", guild=GUILD)
    await arc.salva(GUILD, 7, U)
    ambiente.membri[ADMIN] = fake_member(ADMIN, "Mod", roles=[], guild_permissions=discord.Permissions(moderate_members=True, manage_guild=True))
    return ambiente


async def test_la_pagina_si_apre_decifrata_con_csp_senza_script_e_senza_cache(web):
    client = await _client(web.app)
    try:
        await _entra(client)
        r = await client.get(f"{BASE}/7")
        corpo = await r.text()
        assert r.status == 200 and "riservato" in corpo
        assert "<script>alert" not in corpo and "&lt;script&gt;alert(&#x27;x&#x27;)" in corpo
        csp = r.headers["Content-Security-Policy"]
        assert "default-src 'none'" in csp and "script-src" not in csp and "sandbox" in csp
        assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Content-Type-Options"] == "nosniff"
    finally:
        await client.close()


async def test_un_estraneo_riceve_la_stessa_risposta_di_una_pagina_inesistente(web, monkeypatch):
    # Legge il pannello (livello «lettura»), ma su Discord non ha piu' i permessi di moderazione.
    monkeypatch.setattr(panel_bridge, "livello_accesso", AsyncMock(return_value="lettura"))
    web.membri[ADMIN] = fake_member(ADMIN, "Estraneo", roles=[], guild_permissions=discord.Permissions())
    client = await _client(web.app)
    try:
        await _entra(client)
        esiste = await client.get(f"{BASE}/7")
        inesistente = await client.get(f"{BASE}/999")
        assert esiste.status == inesistente.status == 404
        assert await esiste.text() == await inesistente.text()
        assert "riservato" not in await esiste.text()
    finally:
        await client.close()


async def test_i_permessi_si_rileggono_a_ogni_richiesta(web, monkeypatch):
    monkeypatch.setattr(panel_bridge, "livello_accesso", AsyncMock(return_value="lettura"))
    client = await _client(web.app)
    try:
        await _entra(client)
        assert (await client.get(f"{BASE}/7")).status == 200
        web.membri[ADMIN] = fake_member(ADMIN, "Ex mod", roles=[], guild_permissions=discord.Permissions())
        assert (await client.get(f"{BASE}/7")).status == 404
    finally:
        await client.close()


async def test_dato_alterato_o_chiave_cambiata_o_altro_server_sono_non_trovati(web, clean_db, monkeypatch):
    client = await _client(web.app)
    try:
        await _entra(client)
        corpo = await (await client.get(f"{BASE}/999")).text()
        monkeypatch.setattr(servizio, "config", SimpleNamespace(LOG_TESTI_KEY=generate_key(), TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY=""))
        r = await client.get(f"{BASE}/7")
        assert r.status == 404 and await r.text() == corpo  # chiave cambiata
        monkeypatch.setattr(servizio, "config", SimpleNamespace(LOG_TESTI_KEY=web.k, TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY=""))
        assert (await client.get(f"{BASE}/7")).status == 200
        await clean_db.execute("UPDATE moderation_archivio_utente SET testi_cifrato = 'v2.aaaaaaaa.AAAA'")
        r = await client.get(f"{BASE}/7")
        assert r.status == 404 and await r.text() == corpo
    finally:
        await client.close()


# ------------------------------------------------------------------ listener del cog
@pytest.fixture
def cog(monkeypatch, chiave):
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=True))
    ignora = MagicMock()
    ignora.carica = AsyncMock(return_value=Ignorati())
    monkeypatch.setattr(modulo, "log_ignora_repo", ignora)
    monkeypatch.setattr(modulo.log_eventi_repo, "evento_acceso", AsyncMock(return_value=True))
    return modulo.MessageLogsCog(MagicMock()), ignora


def _msg(testo="ciao", bot=False, canale=CANALE):
    m = MagicMock()
    m.id, m.content, m.attachments = 70, testo, []
    m.guild = fake_guild(guild_id=G)
    m.channel = fake_text_channel(channel_id=canale)
    m.author = fake_member(user_id=U, bot=bot)
    m.author.id = U
    return m


async def test_il_listener_accoda_il_testo_dei_canali_registrati(cog):
    c, _ = cog
    await c.salva_testo(_msg("ciao a tutti"))
    assert len(servizio.coda) == 1


async def test_il_listener_salta_bot_canali_ignorati_e_log_spento(cog, monkeypatch):
    c, ignora = cog
    await c.salva_testo(_msg(bot=True))
    ignora.carica.return_value = Ignorati(canali=frozenset({CANALE}))
    await c.salva_testo(_msg())
    ignora.carica.return_value = Ignorati()
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=False))
    await c.salva_testo(_msg())
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=True))
    monkeypatch.setattr(modulo.log_eventi_repo, "evento_acceso", AsyncMock(return_value=False))  # cancellati e modificati spenti
    await c.salva_testo(_msg())
    assert len(servizio.coda) == 0


async def test_il_listener_senza_chiave_non_accoda_ne_interroga_il_database(cog, monkeypatch):
    c, ignora = cog
    monkeypatch.setattr(servizio, "config", SimpleNamespace(LOG_TESTI_KEY="", TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY=""))
    await c.salva_testo(_msg())
    assert len(servizio.coda) == 0
    ignora.carica.assert_not_awaited()


# ------------------------------------------------------------------ comando esistente, con il link
async def test_il_comando_archivio_da_il_link_al_pannello_e_mai_il_testo(amb, chiave, monkeypatch):
    from cogs.moderation._shared import MODULE_CASE_SYSTEM
    from cogs.moderation.case_system import ModerationCaseSystemCog
    from tests.support.discord_fakes import fake_interaction
    from tests.test_moderation_ordine_azione import ID_SERVER, Scena

    await db.set_module_active_for_guild(ID_SERVER, MODULE_CASE_SYSTEM, True)
    await _riga(amb, chiave, 1, U, 1, SEGRETO, guild=ID_SERVER)
    await arc.salva(ID_SERVER, 4, U)
    s = Scena()
    cs = ModerationCaseSystemCog(bot=None)
    monkeypatch.setattr("cogs.moderation.case_system.config", SimpleNamespace(WEB_PANEL_PUBLIC_URL="https://pannello.example/"))
    i = fake_interaction(guild=s.server, user=s.moderatore)
    await cs.case_chat.callback(cs, i, 4, True)
    kw = i.response.send_message.await_args
    testo = kw.args[0] if kw.args else kw.kwargs["content"]
    assert f"https://pannello.example/server/{ID_SERVER}/moderazione/archivio/4" in testo
    assert kw.kwargs["ephemeral"] is True and SEGRETO not in testo
    assert SEGRETO.encode() not in kw.kwargs["file"].fp.read()  # il file non ha il testo
    monkeypatch.setattr("cogs.moderation.case_system.config", SimpleNamespace(WEB_PANEL_PUBLIC_URL=""))
    i2 = fake_interaction(guild=s.server, user=s.moderatore)
    await cs.case_chat.callback(cs, i2, 4, True)
    assert "https://" not in (i2.response.send_message.await_args.args[0])  # senza indirizzo: nessun link inventato


async def test_due_svuota_insieme_non_scrivono_righe_doppie_ne_perdute(amb, chiave, monkeypatch):
    """Giro periodico e sanzione insieme: ogni riga si scrive una volta sola, nessuna va persa."""
    import asyncio

    for i in range(5):
        servizio.coda.accoda(G, CANALE, 200 + i, U, "creato", f"m{i}")
    scritte = []
    originale = servizio.log_testi_repo.inserisci_lotto

    async def lento(righe):
        scritte.extend(r.message_id for r in righe)
        await asyncio.sleep(0.05)
        await originale(righe)

    monkeypatch.setattr(servizio.log_testi_repo, "inserisci_lotto", lento)
    primo = asyncio.create_task(servizio.coda.svuota())
    await asyncio.sleep(0.01)  # il primo giro e' dentro l'inserimento lento
    for i in range(5):
        servizio.coda.accoda(G, CANALE, 300 + i, U, "creato", f"n{i}")
    secondo = asyncio.create_task(servizio.coda.svuota())
    await asyncio.gather(primo, secondo)
    assert sorted(scritte) == sorted([200 + i for i in range(5)] + [300 + i for i in range(5)])
    assert len(servizio.coda) == 0


async def test_se_l_inserimento_fallisce_il_lotto_resta_in_coda(amb, chiave, monkeypatch):
    for i in range(3):
        servizio.coda.accoda(G, CANALE, 400 + i, U, "creato", f"m{i}")

    async def rotto(righe):
        raise RuntimeError("db giu'")

    monkeypatch.setattr(servizio.log_testi_repo, "inserisci_lotto", rotto)
    assert await servizio.coda.svuota() == 0
    assert len(servizio.coda) == 3

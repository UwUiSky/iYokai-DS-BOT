"""
tests/test_sondaggi_programmati.py
==================================
D69 B23 (UTL-090, 092, 097): sondaggi che iniziano più tardi, chiusura a N voti sul sondaggio nativo, gestione
(`/sondaggi gestisci`), testo di «opzione tolta». Archivi su PostgreSQL vero.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import sondaggi_logic as L
from core.repositories.sondaggi_nativi_repo import SondaggiNativiRepository
from core.repositories.sondaggi_repo import SondaggiRepository
from tests.support.discord_fakes import fake_interaction, fake_member

G = 21
ADESSO = datetime.now(timezone.utc)


def test_inizio_tra_ha_limiti():
    assert not L.inizio_valido(30) and L.inizio_valido(60) and L.inizio_valido(30 * 86400)
    assert not L.inizio_valido(30 * 86400 + 1)


@pytest.fixture
def repo(clean_db):
    return SondaggiRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def nativi(clean_db):
    return SondaggiNativiRepository(pool_provider=lambda: clean_db)


async def _programmato(repo):
    return await repo.crea(G, 5, 99, "dopo?", ["a", "b"], stato="programmato", inizia_il=ADESSO + timedelta(hours=1), durata_s=3600)


@pytest.mark.asyncio
async def test_bottoni_programmato_si_apre_una_volta_sola(repo):
    s = await _programmato(repo)
    assert (await repo.vota(s, 1, 0, 1, ADESSO))[0] == "chiuso"  # non è ancora aperto
    scade = ADESSO + timedelta(hours=2)
    assert sorted(await asyncio.gather(repo.apri(s, scade), repo.apri(s, scade))) == [False, True]
    riga = await repo.prendi(s)
    assert riga["stato"] == "aperto" and riga["scade_il"] == scade
    assert (await repo.vota(s, 1, 0, 1, ADESSO))[0] == "ok"
    assert await repo.apri(s, scade) is False


@pytest.mark.asyncio
async def test_bottoni_programmato_annullato_non_si_apre(repo):
    s = await _programmato(repo)
    assert await repo.chiudi(s) is True
    assert await repo.apri(s, ADESSO + timedelta(hours=1)) is False
    assert (await repo.prendi(s))["stato"] == "chiuso"


@pytest.mark.asyncio
async def test_elenco_per_stato_include_programmati(repo):
    s = await _programmato(repo)
    a = await repo.crea(G, 5, 99, "ora?", ["a", "b"], scade_il=ADESSO + timedelta(hours=1))
    ids = {r["id"] for r in await repo.elenco_gestione(G, 99)}
    assert {s, a} <= ids
    assert {r["id"] for r in await repo.elenco_gestione(G, 5)} == set()
    await repo.chiudi(a)
    assert a not in {r["id"] for r in await repo.elenco_gestione(G, 99)}
    assert a in {r["id"] for r in await repo.elenco_gestione(G, 99, anche_chiusi=True)}


@pytest.mark.asyncio
async def test_nativo_programmato_si_apre_una_volta_e_porta_i_dati(nativi):
    nid = await nativi.crea(G, 5, 99, "Pizza?", ["Sì", "No"], multipla=True, durata_ore=12, discussione=True,
                            chiudi_a_voti=3, inizia_il=ADESSO + timedelta(hours=1))
    righe = await asyncio.gather(nativi.apri(nid), nativi.apri(nid))
    assert sorted(r is not None for r in righe) == [False, True]
    r = next(x for x in righe if x is not None)
    assert r["domanda"] == "Pizza?" and list(r["opzioni"]) == ["Sì", "No"] and r["durata_ore"] == 12 and r["discussione"]
    assert (await nativi.prendi(nid))["stato"] == "aperto"


@pytest.mark.asyncio
async def test_nativo_soglia_e_chiusura_una_sola_volta(nativi):
    nid = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24, chiudi_a_voti=2, stato="aperto")
    await nativi.imposta_messaggio(nid, 777)
    assert await nativi.conta_voto(777, 1) == (nid, False)
    assert await nativi.conta_voto(777, 1) == (nid, True)  # soglia: conta_voto non chiude da solo
    assert (await nativi.prendi(nid))["stato"] == "aperto"
    esiti = await asyncio.gather(nativi.chiudi(nid), nativi.chiudi(nid), nativi.chiudi(nid))
    assert sorted(esiti) == [False, False, True]
    assert await nativi.conta_voto(777, 1) is None  # già chiuso: niente più conteggio
    assert await nativi.conta_voto(999, 1) is None  # messaggio senza soglia


@pytest.mark.asyncio
async def test_nativo_riallinea_e_programmati_annullabili(nativi):
    nid = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24, chiudi_a_voti=5, stato="aperto")
    await nativi.imposta_messaggio(nid, 780)
    assert [r["id"] for r in await nativi.aperti_con_soglia()] == [nid]
    assert await nativi.riallinea(nid, 4) is False and (await nativi.prendi(nid))["voti"] == 4
    assert await nativi.riallinea(nid, 6) is True
    p = await nativi.crea(G, 5, 99, "Pizza stasera", ["a", "b"], durata_ore=24, inizia_il=ADESSO + timedelta(hours=1))
    assert [r["id"] for r in await nativi.programmati(G, 99, "pizza")] == [p]
    assert await nativi.programmati(G, 98) == []
    assert await nativi.annulla_programmato(p) is True and await nativi.annulla_programmato(p) is False
    assert await nativi.apri(p) is None  # la partenza non lo trova più
    a = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24, stato="aperto")
    assert await nativi.annulla_programmato(a) is False  # già partito


@pytest.mark.asyncio
async def test_nativo_voto_tolto_riabbassa_il_conto(nativi):
    nid = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24, chiudi_a_voti=2, stato="aperto")
    await nativi.imposta_messaggio(nid, 778)
    await nativi.conta_voto(778, 1)
    await nativi.conta_voto(778, -1)
    await nativi.conta_voto(778, -1)  # mai sotto zero
    assert (await nativi.prendi(nid))["voti"] == 0
    assert await nativi.conta_voto(778, 1) == (nid, False)


@pytest.mark.asyncio
async def test_nativo_canale_cancellato_e_fine(nativi):
    nid = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24)
    assert await nativi.elimina_del_canale(G, 6) == 0
    assert await nativi.elimina_del_canale(G, 5) == 1 and await nativi.prendi(nid) is None
    n2 = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24)
    await nativi.elimina(n2)
    assert await nativi.prendi(n2) is None


@pytest.mark.asyncio
async def test_voto_su_opzione_tolta_ha_un_testo_suo(repo, monkeypatch):
    from cogs.utility import sondaggi_bottoni as M

    monkeypatch.setattr(M, "sondaggi_repo", repo)
    monkeypatch.setattr(M, "lingua_interazione", AsyncMock(return_value="it"))
    s = await repo.crea(G, 5, 99, "q?", ["a", "b", "c"], scade_il=ADESSO + timedelta(hours=1))
    await repo.modifica(s, "q?", ["a", "b"], None)
    cog = M.SondaggiBottoniCog(MagicMock())
    i = fake_interaction(user=fake_member(user_id=1))
    i.guild.id = G
    await cog.voto(i, s, 2)
    testo = i.followup.send.await_args.args[0]
    assert testo == M.t("sb_opzione_tolta", "it") and testo != M.t("sb_gia_chiuso", "it")
    chiuso = await repo.chiudi(s)
    assert chiuso
    i2 = fake_interaction(user=fake_member(user_id=1))
    i2.guild.id = G
    await cog.voto(i2, s, 0)
    assert i2.followup.send.await_args.args[0] == M.t("sb_gia_chiuso", "it")


@pytest.mark.asyncio
async def test_gestisci_riepilogo_elenco_e_chiudi(repo, nativi, monkeypatch):
    from cogs.utility import sondaggi_bottoni as M

    monkeypatch.setattr(M, "sondaggi_repo", repo)
    monkeypatch.setattr(M, "sondaggi_nativi_repo", nativi)
    monkeypatch.setattr(M, "lingua_interazione", AsyncMock(return_value="it"))
    cog = M.SondaggiBottoniCog(MagicMock())
    cog.aggiorna_messaggio = AsyncMock()
    s = await repo.crea(G, 5, 99, "chi vince?", ["a", "b"], scade_il=ADESSO + timedelta(hours=1), risultati="alla_fine")
    await repo.vota(s, 1, 0, 1, ADESSO)

    def chiama(user_id, azione, sondaggio=None, perm=None):
        i = fake_interaction(user=fake_member(user_id=user_id), permissions=perm or discord.Permissions.none())
        i.guild.id = G
        return i, cog.gestisci.callback(cog, i, azione, sondaggio)

    i, c = chiama(99, "elenco")
    await c
    assert "chi vince?" in str(i.response.send_message.await_args)
    # riepilogo: con «alla fine» i risultati restano nascosti, ma il numero di votanti si vede
    i, c = chiama(99, "riepilogo", str(s))
    await c
    corpo = str(i.response.send_message.await_args)
    assert "chi vince?" in corpo and "█" not in corpo
    # un estraneo senza permesso non può né vedere né chiudere
    i, c = chiama(5, "chiudi", str(s))
    await c
    assert (await repo.prendi(s))["stato"] == "aperto"
    assert i.response.send_message.await_args.args[0] == M.t("sb_non_si_puo", "it")
    # lo staff con «Gestisci messaggi» chiude
    i, c = chiama(5, "chiudi", str(s), discord.Permissions(manage_messages=True))
    await c
    assert (await repo.prendi(s))["stato"] == "chiuso"
    cog.aggiorna_messaggio.assert_awaited()
    # ora il riepilogo mostra i risultati
    i, c = chiama(99, "riepilogo", str(s))
    await c
    assert "█" in str(i.response.send_message.await_args)


@pytest.mark.asyncio
async def test_nativo_programma_e_chiude_a_voti(nativi, monkeypatch):
    from cogs.utility import poll as P

    monkeypatch.setattr(P, "sondaggi_nativi_repo", nativi)
    programma = AsyncMock()
    monkeypatch.setattr(P.scheduler, "schedule", programma)
    canale = MagicMock()
    canale.id = 5
    canale.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True)
    bot = MagicMock()
    bot.get_channel.return_value = canale
    canale.send = AsyncMock(return_value=MagicMock(id=900, create_thread=AsyncMock()))
    msg = MagicMock()
    canale.get_partial_message.return_value = msg
    msg.end_poll = AsyncMock()
    cog = P.PollCog(bot)
    i = fake_interaction(channel=canale)
    i.guild.id = G
    await cog._programma(i, "q?", ["a", "b"], 24, False, False, "2h", 2)
    assert programma.await_args.args[2] == P.AZIONE_APRI_NATIVO
    nid = programma.await_args.args[4]["id"]
    await cog.alla_apertura(G, 99, {"id": nid})
    await cog.alla_apertura(G, 99, {"id": nid})  # secondo giro: niente doppione
    assert canale.send.await_count == 1 and canale.send.await_args.kwargs["poll"].question == "q?"
    p = MagicMock(message_id=900, channel_id=5)
    await cog._voto(p, 1)
    msg.end_poll.assert_not_awaited()
    await cog._voto(p, 1)
    msg.end_poll.assert_awaited_once()
    await cog._voto(p, 1)
    msg.end_poll.assert_awaited_once()


def _cog_poll(monkeypatch, nativi, votanti_per_risposta):
    from cogs.utility import poll as P

    monkeypatch.setattr(P, "sondaggi_nativi_repo", nativi)
    msg = MagicMock()
    msg.end_poll = AsyncMock()

    def risposta(ids):
        async def voters():
            for u in ids:
                yield MagicMock(id=u)
        return MagicMock(vote_count=len(ids), voters=voters)

    sondaggio = MagicMock(total_votes=sum(len(v) for v in votanti_per_risposta))
    sondaggio.answers = [risposta(v) for v in votanti_per_risposta]
    sondaggio.is_finalised.return_value = False
    canale = MagicMock()
    canale.get_partial_message.return_value = msg
    canale.fetch_message = AsyncMock(return_value=MagicMock(poll=sondaggio))
    bot = MagicMock()
    bot.get_channel.return_value = canale
    return P.PollCog(bot), canale, msg


@pytest.mark.asyncio
async def test_nativo_multiplo_conta_i_votanti_non_i_voti(nativi, monkeypatch):
    nid = await nativi.crea(G, 5, 99, "q", ["a", "b"], multipla=True, durata_ore=24, chiudi_a_voti=2, stato="aperto")
    await nativi.imposta_messaggio(nid, 790)
    # una sola persona vota due opzioni: 2 voti ma 1 votante
    cog, canale, msg = _cog_poll(monkeypatch, nativi, [[1], [1]])
    p = MagicMock(message_id=790, channel_id=5)
    await cog._voto(p, 1)
    await cog._voto(p, 1)
    msg.end_poll.assert_not_awaited()
    assert (await nativi.prendi(nid))["stato"] == "aperto"
    # arriva una seconda persona: ora i votanti sono 2
    cog, canale, msg = _cog_poll(monkeypatch, nativi, [[1], [1, 2]])
    await cog._voto(p, 1)
    msg.end_poll.assert_awaited_once()


@pytest.mark.asyncio
async def test_nativo_dopo_riavvio_ricalcola_dal_sondaggio(nativi, monkeypatch):
    nid = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24, chiudi_a_voti=3, stato="aperto")
    await nativi.imposta_messaggio(nid, 791)
    # 3 voti arrivati a bot spento: il conto salvato è 0
    cog, canale, msg = _cog_poll(monkeypatch, nativi, [[1, 2], [3]])
    await cog.on_ready()
    msg.end_poll.assert_awaited_once()
    assert await nativi.prendi(nid) is None
    # sondaggio già finito su Discord: la riga si toglie senza chiudere nulla
    n2 = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24, chiudi_a_voti=3, stato="aperto")
    await nativi.imposta_messaggio(n2, 792)
    cog, canale, msg = _cog_poll(monkeypatch, nativi, [[1]])
    canale.fetch_message.return_value.poll.is_finalised.return_value = True
    await cog.on_ready()
    msg.end_poll.assert_not_awaited()
    assert await nativi.prendi(n2) is None


@pytest.mark.asyncio
async def test_gestisci_annulla_nativo_programmato(nativi, repo, monkeypatch):
    from cogs.utility import sondaggi_bottoni as M

    monkeypatch.setattr(M, "sondaggi_repo", repo)
    monkeypatch.setattr(M, "sondaggi_nativi_repo", nativi)
    monkeypatch.setattr(M, "lingua_interazione", AsyncMock(return_value="it"))
    cog = M.SondaggiBottoniCog(MagicMock())
    n = await nativi.crea(G, 5, 99, "Film venerdi?", ["a", "b"], durata_ore=24, inizia_il=ADESSO + timedelta(hours=1))

    def chiama(user_id, azione, sondaggio=None, perm=None):
        i = fake_interaction(user=fake_member(user_id=user_id), permissions=perm or discord.Permissions.none())
        i.guild.id = G
        return i, cog.gestisci.callback(cog, i, azione, sondaggio)

    i, c = chiama(99, "elenco")
    await c
    assert f"#n{n}" in str(i.response.send_message.await_args) and "Film venerdi?" in str(i.response.send_message.await_args)
    i, c = chiama(5, "chiudi", f"n{n}")
    await c
    assert i.response.send_message.await_args.args[0] == M.t("sb_non_si_puo", "it")
    assert await nativi.prendi(n) is not None
    i, c = chiama(99, "chiudi", f"n{n}")
    await c
    assert i.response.send_message.await_args.args[0] == M.t("sb_nativo_annullato", "it")
    assert await nativi.prendi(n) is None


@pytest.mark.asyncio
async def test_nativo_end_poll_fallito_si_riprova_e_poi_si_chiude(nativi, monkeypatch):
    from cogs.utility import poll as P

    nid = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24, chiudi_a_voti=1, stato="aperto")
    await nativi.imposta_messaggio(nid, 910)
    cog, canale, msg = _cog_poll(monkeypatch, nativi, [[1]])
    programma = AsyncMock()
    monkeypatch.setattr(P.scheduler, "schedule", programma)
    msg.end_poll = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "x"))
    await cog._voto(MagicMock(message_id=910, channel_id=5), 1)
    assert programma.await_args.args[2] == P.AZIONE_RIPROVA_CHIUSURA
    payload = programma.await_args.args[4]
    assert await nativi.prendi(nid) is not None  # la riga resta finché il poll non è chiuso
    msg.end_poll = AsyncMock()
    await cog.riprova_chiusura(G, 99, payload)
    msg.end_poll.assert_awaited_once()
    assert await nativi.prendi(nid) is None


@pytest.mark.asyncio
async def test_nativo_riprova_chiusura_messaggio_sparito_pulisce(nativi, monkeypatch):
    from cogs.utility import poll as P

    nid = await nativi.crea(G, 5, 99, "q", ["a", "b"], durata_ore=24, chiudi_a_voti=1, stato="aperto")
    await nativi.imposta_messaggio(nid, 911)
    cog, canale, msg = _cog_poll(monkeypatch, nativi, [[1]])
    msg.end_poll = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "x"))
    programma = AsyncMock()
    monkeypatch.setattr(P.scheduler, "schedule", programma)
    await cog.riprova_chiusura(G, 99, {"id": nid, "channel_id": 5, "message_id": 911, "tentativo": 1})
    programma.assert_not_awaited()
    assert await nativi.prendi(nid) is None


@pytest.mark.asyncio
async def test_bottoni_programmato_trova_anche_i_thread(repo, monkeypatch):
    from cogs.utility import sondaggi_bottoni as M

    s = await _programmato(repo)
    monkeypatch.setattr(M, "sondaggi_repo", repo)
    monkeypatch.setattr(M.scheduler, "schedule", AsyncMock())
    thread = MagicMock()
    thread.send = AsyncMock(return_value=MagicMock(id=555))
    guild = MagicMock()
    guild.get_channel_or_thread.return_value = thread
    bot = MagicMock()
    bot.get_channel.return_value = None
    bot.get_guild.return_value = guild
    cog = M.SondaggiBottoniCog(bot)
    cog._disegna = AsyncMock(return_value=(MagicMock(), MagicMock()))
    await cog.alla_apertura(G, 99, {"id": s})
    thread.send.assert_awaited_once()

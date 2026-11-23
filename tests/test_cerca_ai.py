"""
tests/test_cerca_ai.py
======================
UTL-216 (D124): «cerca qualsiasi cosa». Link pericolosi mai mostrati, testo troncato, menzioni spente,
limite per persona, AI assente, servizio con ricerca web scelto dallo snodo.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.utility.cerca_ai as cog
from core import cerca_ai_logic as logica
from core.ai_providers import Fornitore, leggi_fornitori
from core.ai_router import StatoFornitori, scegli_fornitori
from core.ai_servizio import AINonDisponibile
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


@pytest.fixture
def link_pericolosi(monkeypatch):
    cattivi = {"https://cattivo.example/x"}
    monkeypatch.setattr(logica.controllo_link, "e_link_pericoloso", AsyncMock(side_effect=lambda u, **k: u in cattivi))


@pytest.mark.asyncio
async def test_link_pericolosi_mai_mostrati(link_pericolosi):
    testo, tolti = await logica.pulisci_risposta("Vedi https://buono.example/a e [clicca](https://cattivo.example/x).")
    assert "cattivo" not in testo and tolti == 1
    assert "<https://buono.example/a>" in testo and logica.SEGNO_RIMOSSO in testo


@pytest.mark.asyncio
async def test_link_oltre_il_tetto_tolti_e_menzioni_spente(link_pericolosi):
    molti = " ".join(f"https://s{i}.example/p" for i in range(10))
    testo, tolti = await logica.pulisci_risposta(f"@everyone @here <@123> {molti}")
    assert tolti == 10 - logica.MAX_LINK_MOSTRATI
    assert "@everyone" not in testo and "<@123>" not in testo and "@​everyone" in testo


@pytest.mark.asyncio
async def test_testo_troncato(link_pericolosi):
    testo, _ = await logica.pulisci_risposta("a" * 5000)
    assert len(testo) <= logica.MAX_RISPOSTA


def test_limite_per_persona():
    ora = [0.0]
    lim = logica.LimitePersona(lambda: ora[0])
    assert lim.prova(1) == (True, 0)
    ammessa, attesa = lim.prova(1)
    assert not ammessa and attesa > 0
    assert lim.prova(2)[0]
    for i in range(logica.MAX_AL_GIORNO - 1):
        ora[0] += logica.PAUSA_SECONDI + 1
        assert lim.prova(1)[0]
    ora[0] += logica.PAUSA_SECONDI + 1
    assert not lim.prova(1)[0]
    ora[0] += 86400
    assert lim.prova(1)[0]


def test_lo_snodo_sceglie_solo_chi_sa_cercare():
    solo_chat = Fornitore("a", "https://a.example", tipi=frozenset({"chat"}))
    cerca = Fornitore("b", "https://b.example", tipi=frozenset({"chat", "ricerca"}))
    assert scegli_fornitori([solo_chat, cerca], "ricerca", "bassa", StatoFornitori()) == [cerca]
    assert scegli_fornitori([solo_chat], "ricerca", "bassa", StatoFornitori()) == []


def test_il_tipo_ricerca_si_legge_dal_env():
    env = {
        "AI_FORNITORI": "px", "AI_URL_PX": "https://px.example/v1", "AI_KEY_PX": "k", "AI_ADDESTRA_PX": "no",
        "AI_TIPI_PX": "chat,ricerca",
    }
    fornitori, _ = leggi_fornitori(env)
    assert fornitori and "ricerca" in fornitori[0].tipi


def test_le_fonti_dichiarate_si_aggiungono_solo_https():
    from core.ai_providers import _fonti_dichiarate

    assert "https://a.example/1" in _fonti_dichiarate({"citations": ["https://a.example/1", "http://x", 5]})
    assert "http://x" not in _fonti_dichiarate({"citations": ["http://x"]}) and _fonti_dichiarate({}) == ""


# ------------------------------------------------------------------ comando
def _inter(user_id=7):
    return fake_interaction(guild=fake_guild(), user=fake_member(user_id=user_id))


@pytest.fixture
def servizio(monkeypatch, link_pericolosi):
    s = MagicMock()
    s.richiedi = AsyncMock(return_value=MagicMock(testo="Ecco https://buono.example/a"))
    monkeypatch.setattr(cog, "servizio_ai", lambda: s)
    monkeypatch.setattr(cog, "lingua_interazione", AsyncMock(return_value="it"))
    return s


@pytest.mark.asyncio
async def test_comando_risponde_in_privato_senza_menzioni(servizio):
    c = cog.CercaAICog(MagicMock())
    inter = _inter()
    await c.cerca.callback(c, inter, "gatti", None)
    richiesta = servizio.richiedi.await_args.args[0]
    assert richiesta.tipo == "ricerca" and richiesta.messaggi_utenti is True and richiesta.funzione == "ricerca_web"
    kw = inter.followup.send.await_args.kwargs
    assert kw["ephemeral"] is True and kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].users is False


@pytest.mark.asyncio
async def test_senza_servizio_adatto_messaggio_chiaro_e_non_conta(servizio):
    servizio.richiedi = AsyncMock(side_effect=AINonDisponibile("non_configurata"))
    c = cog.CercaAICog(MagicMock())
    inter = _inter()
    await c.cerca.callback(c, inter, "gatti", None)
    assert "ricerca sul web" in inter.followup.send.await_args.args[0]
    inter2 = _inter()
    await c.cerca.callback(c, inter2, "gatti", None)  # non ha consumato la pausa
    assert servizio.richiedi.await_count == 2


@pytest.mark.asyncio
async def test_ai_spenta_o_privacy_del_server_mostrano_il_motivo(servizio):
    servizio.richiedi = AsyncMock(side_effect=AINonDisponibile("privacy"))
    c = cog.CercaAICog(MagicMock())
    inter = _inter()
    await c.cerca.callback(c, inter, "gatti", None)
    assert "non mandare messaggi" in inter.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_pausa_per_persona(servizio):
    c = cog.CercaAICog(MagicMock())
    await c.cerca.callback(c, _inter(), "gatti", None)
    inter = _inter()
    await c.cerca.callback(c, inter, "cani", None)
    assert servizio.richiedi.await_count == 1
    inter.response.send_message.assert_awaited_once()

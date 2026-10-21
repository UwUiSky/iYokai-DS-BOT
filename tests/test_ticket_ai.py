"""
tests/test_ticket_ai.py
=======================
#139 parte AI: sollecito nella lingua dell'utente, scelta tra le risposte approvate,
ruolo da chiamare. Fornitore AI finto (tests/support/ai_finto.py) e database vero;
ogni funzione va anche con l'AI ferma.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cogs.tickets import risposte as modulo
from core import ticket_ai_logic as L
from core.ai_servizio import imposta_servizio_ai
from core.command_access import SETTING_ADMIN_ROLE
from core.database import db
from core.repositories.ai_repo import ai_repo
from tests.support.ai_finto import TrasportoFinto, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_role

G = 666
UTENTE = 20
RUOLO_ADMIN = 4444


@pytest.fixture
def repo(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    yield ai_repo
    imposta_servizio_ai(None)


async def _ai(repo, risposta, *, accesa=True):
    servizio, trasporto = servizio_finto(repo, trasporto=TrasportoFinto(risposte={"alfa": risposta}))
    imposta_servizio_ai(servizio)
    if accesa:
        await repo.imposta(G, attivo=True)
    return trasporto


class Canale:
    def __init__(self, messaggi, guild=None):
        self.id = 300
        self.guild = guild or fake_guild(G)
        self._messaggi = messaggi

    def history(self, **_):
        async def scorri():
            for m in self._messaggi:
                yield m

        return scorri()


def _msg(testo, autore=UTENTE):
    return SimpleNamespace(author=SimpleNamespace(id=autore, bot=False), content=testo, embeds=[])


def _ticket():
    return SimpleNamespace(user_id=UTENTE, guild_id=G)


# ---------------------------------------------------------------- logica
def test_letture_delle_risposte_dell_ai():
    assert L.leggi_scelta('{"numero": 3}', {3, 4}) == 3
    assert L.leggi_scelta('{"numero": 9}', {3}) is None
    assert L.leggi_scelta("boh", {3}) is None
    assert L.leggi_ruolo('```json {"ruolo": "Amministratore"} ```') == "admin"
    assert L.leggi_ruolo('{"ruolo": "staff"}') is None
    assert L.traduzione_valida("{utente} ciao", "{utente} hola") == "{utente} hola"
    assert L.traduzione_valida("{utente} ciao", "hola") is None


def test_lingua_e_testo_senza_ai():
    assert L.lingua_utente(["hello, I need help with my order please"]) == "en"
    assert L.lingua_utente([], "fr") == "fr"
    assert L.lingua_utente([], "xx") == "it"
    assert "What do you need" in L.sollecito_locale("de") and "Di cosa hai bisogno" in L.sollecito_locale("de")


# ---------------------------------------------------------------- aggancio
async def test_il_sollecito_si_traduce_nella_lingua_dell_utente(repo):
    trasporto = await _ai(repo, "{utente} nadie del equipo ha respondido. ¿Qué necesitas?")
    canale = Canale([_msg("hola, necesito ayuda con mi cuenta por favor")])
    testo = await modulo.RisposteStandardCog(bot=None)._testo_sollecito(canale, _ticket())
    assert testo.startswith(f"<@{UTENTE}> nadie") and trasporto.chiamate


async def test_con_l_ai_spenta_il_sollecito_resta_in_italiano_e_inglese(repo):
    trasporto = await _ai(repo, "non deve servire", accesa=False)
    canale = Canale([_msg("hola, necesito ayuda con mi cuenta por favor")])
    testo = await modulo.RisposteStandardCog(bot=None)._testo_sollecito(canale, _ticket())
    assert "Di cosa hai bisogno" in testo and "What do you need" in testo
    assert trasporto.chiamate == []


async def test_l_ai_sceglie_solo_tra_le_risposte_approvate(repo):
    await _ai(repo, '{"numero": 12}')
    approvate = [SimpleNamespace(id=11, title="Affiliazione Twitch", keywords="twitch affiliazione grafiche"),
                 SimpleNamespace(id=12, title="Rimborso", keywords="rimborso pagamento")]
    messaggio = SimpleNamespace(author=SimpleNamespace(id=UTENTE), content="voglio i soldi indietro",
                                guild=SimpleNamespace(id=G), channel=SimpleNamespace(id=300))
    cog = modulo.RisposteStandardCog(bot=None)
    assert (await cog._scelta_ai(messaggio, approvate)).id == 12
    await _ai(repo, '{"numero": 99}')
    assert await cog._scelta_ai(messaggio, approvate) is None


async def test_l_ai_chiama_l_amministratore_se_serve(repo):
    await _ai(repo, '{"ruolo": "amministratore"}')
    await db.set_guild_setting(G, SETTING_ADMIN_ROLE, RUOLO_ADMIN)
    guild = fake_guild(G)
    guild.get_role = MagicMock(side_effect=lambda r: fake_role(role_id=r) if r == RUOLO_ADMIN else None)
    canale = Canale([_msg("vorrei una collaborazione e un ruolo partner")], guild)
    assert await modulo.RisposteStandardCog(bot=None)._ruolo_secondo_ai(canale, _ticket()) == RUOLO_ADMIN
    await _ai(repo, "risposta strana")
    assert await modulo.RisposteStandardCog(bot=None)._ruolo_secondo_ai(canale, _ticket()) is None


async def test_chi_scrive_tanti_messaggi_nel_ticket_non_consuma_l_ai_senza_limiti(repo):
    """La scelta parte da ogni messaggio dell'utente: deve contare sul suo limite, non solo sul server."""
    from core.ai_cost_logic import RICHIESTE_AL_MINUTO_UTENTE

    trasporto = await _ai(repo, '{"numero": 0}')
    approvate = [SimpleNamespace(id=11, title="Rimborso", keywords="rimborso pagamento")]
    messaggio = SimpleNamespace(author=SimpleNamespace(id=UTENTE), content="aiuto",
                                guild=SimpleNamespace(id=G), channel=SimpleNamespace(id=300))
    cog = modulo.RisposteStandardCog(bot=None)
    for _ in range(RICHIESTE_AL_MINUTO_UTENTE + 10):
        assert await cog._scelta_ai(messaggio, approvate) is None
    assert len(trasporto.chiamate) <= RICHIESTE_AL_MINUTO_UTENTE

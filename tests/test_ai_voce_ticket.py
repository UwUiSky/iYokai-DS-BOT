"""
tests/test_ai_voce_ticket.py
============================
Saluto vocale all'apertura di un ticket (§14.19, passo 2): frase con o senza nome, solo con voce accesa e motore attivo,
tono scherzoso, nessun errore ferma il ticket. Database vero, Discord e motore finti.
"""

import random
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.ai import voce
from core.database import db
from core.repositories.ai_voce_repo import ai_voce_repo
from core.voice_client import ServizioVoce, imposta_servizio_voce
from core.voice_ticket_logic import TONO_TICKET, frase_apertura
from tests.support.discord_fakes import fake_text_channel
from tests.test_ai_voce import MotoreFinto

G = 9261


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(ai_voce_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    yield ai_voce_repo
    imposta_servizio_voce(None)


def _cog(parla_finto):
    cog = voce.AiVoceCog.__new__(voce.AiVoceCog)
    cog.bot = MagicMock()
    return cog


def test_frase_con_nome_pronunciabile_non_e_fissa():
    frase, fissa = frase_apertura("Giulia", random.Random(1))
    assert "Giulia" in frase and "Yokai" in frase and fissa is False


def test_frase_senza_nome_e_fissa_e_in_cache():
    for nome in (None, "x_y_z", "XJ9"):
        frase, fissa = frase_apertura(nome, random.Random(1))
        assert fissa is True and "Yokai" in frase and "None" not in frase


async def test_saluto_spento_se_la_voce_non_e_accesa(repo, monkeypatch):
    imposta_servizio_voce(ServizioVoce(MotoreFinto(), None))
    parla = AsyncMock()
    monkeypatch.setattr(voce, "parla", parla)
    utente = MagicMock(display_name="Giulia")
    assert await _cog(parla).saluto_ticket(fake_text_channel(), G, utente) is False
    parla.assert_not_awaited()


async def test_saluto_spento_senza_motore_non_scrive_niente_nel_ticket(repo, monkeypatch):
    await repo.imposta(G, attiva=True)
    imposta_servizio_voce(ServizioVoce(None, None))
    parla = AsyncMock()
    monkeypatch.setattr(voce, "parla", parla)
    assert await _cog(parla).saluto_ticket(fake_text_channel(), G, MagicMock(display_name="Giulia")) is False
    parla.assert_not_awaited()


async def test_saluto_con_voce_accesa_parla_con_tono_scherzoso(repo, monkeypatch):
    await repo.imposta(G, attiva=True, tono="piccante")
    imposta_servizio_voce(ServizioVoce(MotoreFinto(), None))
    parla = AsyncMock(return_value=True)
    monkeypatch.setattr(voce, "parla", parla)
    canale = fake_text_channel()
    assert await _cog(parla).saluto_ticket(canale, G, MagicMock(display_name="Giulia")) is True
    args, kw = parla.call_args
    assert args[2].startswith(("Ciao Giulia", "Ehi Giulia")) and args[3] == "WELCOME"
    assert kw["tono"] == TONO_TICKET == "scherzosa" and kw["fisso"] is False and kw["guild_id"] == G


async def test_errore_del_saluto_non_ferma_il_ticket(repo, monkeypatch):
    await repo.imposta(G, attiva=True)
    imposta_servizio_voce(ServizioVoce(MotoreFinto(), None))
    monkeypatch.setattr(voce, "parla", AsyncMock(side_effect=RuntimeError("no")))
    assert await _cog(None).saluto_ticket(fake_text_channel(), G, MagicMock(display_name="Giulia")) is False

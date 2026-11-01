"""
tests/test_ai_privacy.py
========================
Lettura AI delle richieste di cancellazione (§25.84): formato della proposta, ripiego senza AI, AI che non cancella.
"""

import pytest

from cogs.ai import _privacy_ai as privacy_ai
from core import ai_privacy_logic as logica
from core.ai_servizio import imposta_servizio_ai
from core.repositories.ai_repo import ai_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto


def test_proposta_letta_dal_json():
    p = logica.leggi_proposta('Ecco: {"riassunto": "Vuole sparire dal server", "azione": "eseguire"}')
    assert p and p.azione == "eseguire" and p.da_ai and "proposta dell'AI" in p.riga()


@pytest.mark.parametrize("testo", ["", "niente json", '{"azione": "cancella tutto", "riassunto": "x"}', '{"azione": "eseguire"}', "[1]"])
def test_proposta_non_valida_e_scartata(testo):
    assert logica.leggi_proposta(testo) is None


async def test_senza_ai_vale_la_proposta_fissa(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    servizio, _ = servizio_finto(ai_repo, fornitori=[])
    imposta_servizio_ai(servizio)
    try:
        p = await privacy_ai.proposta_per("cancellate tutto grazie")
        assert not p.da_ai and p.azione == "eseguire" and "AI non usata" in p.riga()
        assert not (await privacy_ai.proposta_per(None)).da_ai
    finally:
        imposta_servizio_ai(None)


async def test_con_ai_la_proposta_viene_dal_modello(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    risposta = '{"riassunto": "Testo confuso", "azione": "chiarire"}'
    servizio, trasporto = servizio_finto(ai_repo, trasporto=TrasportoFinto(risposte={"alfa": risposta}), fornitori=[fornitore("alfa", tipi=("giudizio",))])
    imposta_servizio_ai(servizio)
    try:
        p = await privacy_ai.proposta_per("boh forse")
        assert p.da_ai and p.azione == "chiarire"
    finally:
        imposta_servizio_ai(None)

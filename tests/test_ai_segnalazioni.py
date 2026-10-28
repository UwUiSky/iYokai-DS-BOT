"""
tests/test_ai_segnalazioni.py
=============================
Etichetta delle segnalazioni (§25.38): scelta della persona, proposta dell'AI, parole senza AI, menu dello staff.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.ai import segnalazioni
from core import segnalazioni_logic as logica
from core.ai_servizio import imposta_servizio_ai
from core.database import db
from core.repositories.ai_repo import ai_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G, U = 8601, 8602


def test_leggi_etichetta_valida_e_non():
    e = logica.leggi_etichetta('{"categoria": "Truffa", "urgenza": "alta"}')
    assert (e.categoria, e.urgenza, e.dall_ai) == ("truffa", "alta", True)
    assert logica.leggi_etichetta('{"categoria": "boh", "urgenza": "alta"}') is None
    assert logica.leggi_etichetta("non è json") is None and logica.leggi_etichetta(None) is None


def test_categoria_locale_per_parole():
    assert logica.categoria_locale("mi ha scritto di un investimento crypto") == "truffa"
    assert logica.categoria_locale("fa spam di inviti") == "spam"
    assert logica.categoria_locale("mi insulta sempre") == "insulti"
    assert logica.categoria_locale("boh") == "altro"


def test_la_scelta_della_persona_vince_poi_l_ai_poi_le_parole():
    ai = logica.Etichetta("insulti", "alta", True)
    assert logica.etichetta_finale("spam", ai, "x").categoria == "spam"
    assert logica.etichetta_finale("spam", ai, "x").dall_ai is False
    assert logica.etichetta_finale(None, ai, "x") == ai
    assert logica.etichetta_finale(None, None, "è una truffa") == logica.Etichetta("truffa", "bassa", False)


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    yield ai_repo
    imposta_servizio_ai(None)


async def test_senza_ai_si_usano_le_parole(repo):
    e = await segnalazioni.etichetta_segnalazione(G, U, "è una truffa di nitro gratis")
    assert (e.categoria, e.dall_ai) == ("truffa", False)


async def test_con_ai_propone_e_il_testo_e_un_dato(repo):
    servizio, trasporto = servizio_finto(
        repo, fornitori=[fornitore()], trasporto=TrasportoFinto(risposte={"alfa": json.dumps({"categoria": "insulti", "urgenza": "media"})})
    )
    imposta_servizio_ai(servizio)
    await repo.registra_consenso(G, U, True)
    e = await segnalazioni.etichetta_segnalazione(G, U, "chiama tutti con nomi brutti")
    assert (e.categoria, e.urgenza, e.dall_ai) == ("insulti", "media", True)
    messaggi = trasporto.chiamate[-1][1]
    assert "nomi brutti" in json.dumps(messaggi) and messaggi[0]["role"] == "system"
    assert "nomi brutti" not in messaggi[0]["content"]
    # se la persona sceglie la categoria, l'AI non viene nemmeno chiamata
    n = len(trasporto.chiamate)
    assert (await segnalazioni.etichetta_segnalazione(G, U, "x", "spam")).categoria == "spam"
    assert len(trasporto.chiamate) == n


async def test_menu_dello_staff_cambia_la_categoria_e_gli_altri_no():
    embed = discord.Embed(title="t")
    embed.add_field(name=segnalazioni.CAMPO, value="spam · urgenza alta (proposta dall'AI)", inline=False)
    menu = segnalazioni.EtichettaView().children[0]
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U))
    i.message = MagicMock(embeds=[embed])
    with patch.object(type(menu), "values", ["truffa"]):
        with patch("cogs.ai.segnalazioni.puo_usare", AsyncMock(return_value=False)):
            await menu.callback(i)
        i.response.send_message.assert_awaited()
        i.response.edit_message.assert_not_awaited()
        with patch("cogs.ai.segnalazioni.puo_usare", AsyncMock(return_value=True)):
            await menu.callback(i)
    assert "truffa · urgenza alta (cambiata dallo staff)" == embed.fields[0].value

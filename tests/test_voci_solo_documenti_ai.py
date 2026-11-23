"""
tests/test_voci_solo_documenti_ai.py
====================================
Voci AI del catalogo che esistevano senza una prova con il suo codice (giro r1doc).
Funzioni coperte: AI-022, AI-023, AI-025
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.ai._comune import completa_lingue
from cogs.ai.config import _CostruisciView
from core.ai_testi_logic import LINGUE, leggi_proposta_server
from core.traduzione_gruppo_logic import MAX_CARATTERI, MAX_MESSAGGI, unisci_successivi


# AI-022
def test_il_menu_traduci_unisce_i_messaggi_di_fila_dello_stesso_autore():
    dopo = [(1, "due"), (1, "tre"), (2, "altro"), (1, "dopo l'altro")]
    assert unisci_successivi("uno", 1, dopo) == "uno\ndue\ntre"
    assert unisci_successivi("solo", 1, []) == "solo"


# AI-022
def test_unione_ferma_ai_tetti_di_messaggi_e_di_caratteri():
    tanti = [(1, "x")] * 20
    assert len(unisci_successivi("a", 1, tanti).split("\n")) == MAX_MESSAGGI
    assert unisci_successivi("a" * (MAX_CARATTERI - 5), 1, [(1, "b" * 50)]) == "a" * (MAX_CARATTERI - 5)
    assert unisci_successivi("a", 1, [(1, "   "), (1, "b")]) == "a\nb"


# AI-023
def test_elenco_delle_lingue_si_cerca_per_nome_e_per_codice_con_tetto_25():
    tutte = completa_lingue("")
    assert 0 < len(tutte) <= 25
    assert all(len(s.value) <= 5 and s.value in LINGUE for s in tutte)
    assert {s.value for s in completa_lingue("ital")} == {c for c, n in LINGUE.items() if "ital" in n or "ital" in c}
    assert completa_lingue("zzzzzz") == []


# AI-025
@pytest.mark.asyncio
async def test_costruisci_crea_solo_dopo_la_conferma_di_chi_l_ha_chiesto():
    proposta = leggi_proposta_server(
        '{"ruoli": ["Ospiti"], "categorie": [{"nome": "Torneo", "canali": [{"nome": "regole", "tipo": "testo"}, '
        '{"nome": "sala", "tipo": "voce"}]}]}'
    )
    assert proposta is not None and proposta.canali_totali == 2
    guild = MagicMock()
    guild.create_role = AsyncMock()
    categoria = MagicMock()
    guild.create_category = AsyncMock(return_value=categoria)
    guild.create_text_channel = AsyncMock()
    guild.create_voice_channel = AsyncMock()
    vista = _CostruisciView(autore_id=5, proposta=proposta)
    # un altro utente non può confermare
    altro = MagicMock(spec=discord.Interaction)
    altro.user = MagicMock(id=6)
    altro.response = MagicMock(send_message=AsyncMock())
    assert await vista.interaction_check(altro) is False
    guild.create_role.assert_not_awaited()
    # chi ha chiesto conferma: si crea tutto, con il motivo nel registro
    io = MagicMock(spec=discord.Interaction)
    io.user = MagicMock(id=5)
    io.guild = guild
    io.response = MagicMock(edit_message=AsyncMock())
    io.edit_original_response = AsyncMock()
    await vista.crea.callback(io)
    guild.create_role.assert_awaited_once()
    guild.create_category.assert_awaited_once()
    guild.create_text_channel.assert_awaited_once()
    guild.create_voice_channel.assert_awaited_once()
    assert "Costruzione con l'AI" in guild.create_role.await_args.kwargs["reason"]


# AI-022
@pytest.mark.asyncio
async def test_il_menu_traduci_manda_all_ai_anche_i_messaggi_successivi(monkeypatch):
    from cogs.user_app import messaggi as m

    inviato = {}

    async def finto(utente, funzione, tipo, testo, istruzioni, lingua):
        inviato["testo"] = testo
        return "ok", None

    monkeypatch.setattr(m, "chiedi_ai_app", finto)
    monkeypatch.setattr(m, "lingua_interazione", AsyncMock(return_value="it"))
    monkeypatch.setattr(m, "istruzioni_ai", lambda f, l: "")

    def msg(autore, testo):
        return MagicMock(author=MagicMock(id=autore), content=testo, embeds=[], attachments=[], stickers=[])

    async def storia(**kw):
        for x in (msg(1, "secondo"), msg(2, "intruso"), msg(1, "mai")):
            yield x

    primo = msg(1, "primo")
    primo.channel.history = storia
    cog = m.MessaggiCog.__new__(m.MessaggiCog)
    io = MagicMock(spec=discord.Interaction)
    io.response = MagicMock(defer=AsyncMock(), send_message=AsyncMock())
    io.followup = MagicMock(send=AsyncMock())
    io.user = MagicMock(id=9)
    await cog.menu_traduci(io, primo)
    assert inviato["testo"] == "primo\nsecondo"

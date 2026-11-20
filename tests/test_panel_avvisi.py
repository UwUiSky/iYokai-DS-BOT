"""
tests/test_panel_avvisi.py
==========================
Avvisi del pannello nel sito o in DM (CFG-006): scelta per categoria, nessun avviso di base, accesso ricontrollato alla
consegna, DM con tetto, niente email.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import web_panel_avvisi as avvisi
from core.config_schema import ImpostazioneNonValida
from core.repositories.web_panel_avvisi_repo import MAX_AVVISI_PER_PERSONA, web_panel_avvisi_repo
from core.web_panel_logic import LimiteFrequenza
from tests.test_panel_accesso import ADMIN, GUILD, LETTORE, ambiente, _come, _imposta  # noqa: F401
from tests.test_web_panel_server import _csrf


@pytest.fixture(autouse=True)
def _limite_nuovo(monkeypatch):
    monkeypatch.setattr(avvisi, "_limite_dm", LimiteFrequenza(3, 3600))


@pytest.mark.asyncio
async def test_di_base_non_arriva_niente(ambiente):
    await _imposta(ambiente, "lettura", [7001])
    assert await avvisi.avvisa(ambiente.bot, ambiente.guild, "sicurezza", "prova") == 0
    assert await web_panel_avvisi_repo.elenco(GUILD, LETTORE) == []


@pytest.mark.asyncio
async def test_avviso_nel_sito_e_pagina_con_escape(ambiente):
    await _imposta(ambiente, "lettura", [7001])
    client = await _come(ambiente, LETTORE)  # anche la sola lettura sceglie i suoi avvisi
    try:
        csrf = await _csrf(client, f"/server/{GUILD}/avvisi")
        r = await client.post(f"/server/{GUILD}/avvisi", data={"csrf": csrf, "canale_sicurezza": "sito"}, allow_redirects=False)
        assert r.status == 302 and "esito=salvato" in r.headers["Location"]
        assert await web_panel_avvisi_repo.preferenze(GUILD, LETTORE) == {"sicurezza": "sito"}
        assert await avvisi.avvisa(ambiente.bot, ambiente.guild, "sicurezza", "Chiave <b>nuova</b> @everyone") == 1
        testo = await (await client.get(f"/server/{GUILD}/avvisi")).text()
        assert "&lt;b&gt;nuova&lt;/b&gt;" in testo and "<b>nuova</b>" not in testo
        assert "@everyone" not in testo.replace("@​everyone", "")  # le menzioni sono rese innocue
        await client.post(f"/server/{GUILD}/avvisi", data={"csrf": csrf, "azione": "letti"}, allow_redirects=False)
        assert all(a.letto for a in await web_panel_avvisi_repo.elenco(GUILD, LETTORE))
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chi_perde_l_accesso_non_riceve_piu_niente(ambiente):
    await _imposta(ambiente, "lettura", [7001])
    await avvisi.imposta_preferenza(GUILD, LETTORE, "sicurezza", "sito")
    ambiente.membri[LETTORE].roles = []
    assert await avvisi.avvisa(ambiente.bot, ambiente.guild, "sicurezza", "segreto") == 0
    assert await web_panel_avvisi_repo.elenco(GUILD, LETTORE) == []


@pytest.mark.asyncio
async def test_non_si_avvisa_chi_ha_fatto_l_azione(ambiente):
    await avvisi.imposta_preferenza(GUILD, ADMIN, "sicurezza", "sito")
    assert await avvisi.avvisa(ambiente.bot, ambiente.guild, "sicurezza", "ciao", escludi_user=ADMIN) == 0
    assert await avvisi.avvisa(ambiente.bot, ambiente.guild, "sicurezza", "ciao") == 1


@pytest.mark.asyncio
async def test_dm_con_tetto_orario_e_dm_chiusi(ambiente):
    await avvisi.imposta_preferenza(GUILD, ADMIN, "modifiche", "dm")
    utente = MagicMock()
    utente.send = AsyncMock()
    ambiente.bot.get_user = MagicMock(return_value=utente)
    for _ in range(5):
        await avvisi.avvisa(ambiente.bot, ambiente.guild, "modifiche", "cambiato")
    assert utente.send.await_count == 3  # al massimo tre DM all'ora
    assert utente.send.await_args.kwargs["allowed_mentions"].everyone is False
    utente.send.side_effect = discord.Forbidden(MagicMock(status=403), "chiusi")
    monkey = LimiteFrequenza(3, 3600)
    avvisi._limite_dm = monkey
    assert await avvisi.avvisa(ambiente.bot, ambiente.guild, "modifiche", "ancora") == 0  # nessuna eccezione


@pytest.mark.asyncio
async def test_niente_email_e_categorie_storte(ambiente):
    assert avvisi.email_disponibile() is False
    for categoria, canale in (("sicurezza", "email"), ("sicurezza", "sms"), ("inventata", "sito")):
        with pytest.raises(ImpostazioneNonValida):
            await avvisi.imposta_preferenza(GUILD, ADMIN, categoria, canale)
    client = await _come(ambiente, ADMIN)
    try:
        testo = await (await client.get(f"/server/{GUILD}/avvisi")).text()
        assert "non ha un servizio di posta" in testo and 'value="email"' not in testo
        csrf = await _csrf(client, f"/server/{GUILD}/avvisi")
        r = await client.post(f"/server/{GUILD}/avvisi", data={"csrf": csrf, "canale_sicurezza": "email"}, allow_redirects=False)
        assert "esito=non_valido" in r.headers["Location"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_tetto_di_avvisi_per_persona(ambiente):
    for i in range(MAX_AVVISI_PER_PERSONA + 5):
        await web_panel_avvisi_repo.aggiungi(GUILD, ADMIN, "sicurezza", f"n{i}")
    righe = await web_panel_avvisi_repo.elenco(GUILD, ADMIN)
    assert len(righe) == MAX_AVVISI_PER_PERSONA and righe[0].testo == f"n{MAX_AVVISI_PER_PERSONA + 4}"


@pytest.mark.asyncio
async def test_le_azioni_del_pannello_producono_avvisi(ambiente):
    await _imposta(ambiente, "lettura", [7001])
    await avvisi.imposta_preferenza(GUILD, LETTORE, "sicurezza", "sito")
    client = await _come(ambiente, ADMIN)
    try:
        csrf = await _csrf(client, f"/server/{GUILD}/api")
        await client.post(f"/server/{GUILD}/api", data={"csrf": csrf, "azione": "crea"})
        elenco = await web_panel_avvisi_repo.elenco(GUILD, LETTORE)
        assert [a.testo for a in elenco] == [f"È stata creata una nuova chiave API ({ambiente.membri[ADMIN].display_name})"]
        assert "iyk_" not in elenco[0].testo  # mai la chiave in un avviso
    finally:
        await client.close()

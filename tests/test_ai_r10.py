"""
tests/test_ai_r10.py
====================
Motore AI, giro r10: manutenzione globale dell'owner (§25.20), coda delle richieste
(§25.22), periodo di prova dell'AI premium (§25.23). Database vero, fornitore finto.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from cogs.ai import config as cfg_mod
from core.ai_coda_logic import CodaAI, CodaPiena
from core.ai_cost_logic import GIORNI_PROVA, prova_attiva, prova_finita
from core.ai_servizio import AINonDisponibile, RichiestaAI, imposta_servizio_ai
from core.config import config
from core.repositories.ai_repo import AiRepository, ai_repo
from tests.support.ai_finto import servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G, U = 4101, 4102


@pytest.fixture
def repo(clean_db):
    return AiRepository(lambda: clean_db)


def _r(**kw):
    base = dict(user_id=U, funzione="chiedi", tipo="chat", testo="come si banna?", guild_id=G)
    base.update(kw)
    return RichiestaAI(**base)


async def _motivo(servizio, richiesta):
    with pytest.raises(AINonDisponibile) as exc:
        await servizio.richiedi(richiesta)
    return exc.value


# ---------------------------------------------------------------- manutenzione
async def test_manutenzione_ferma_l_ai_ovunque_e_poi_riparte(repo):
    servizio, trasporto = servizio_finto(repo)
    await repo.registra_consenso(G, U, True)
    assert (await servizio.richiedi(_r())).testo
    await repo.imposta_manutenzione(True, "Torniamo alle 18.", 1)
    servizio.ricarica_manutenzione()
    errore = await _motivo(servizio, _r(testo="altra domanda"))
    assert errore.motivo == "manutenzione" and "Torniamo alle 18." in errore.testo
    # anche senza server (messaggi privati) e anche per le risposte già in cache
    assert (await _motivo(servizio, _r(guild_id=None))).motivo == "manutenzione"
    assert (await _motivo(servizio, _r())).motivo == "manutenzione"
    await repo.imposta_manutenzione(False, "", 1)
    servizio.ricarica_manutenzione()
    assert (await servizio.richiedi(_r(testo="altra domanda"))).testo
    assert len(trasporto.chiamate) == 2


async def test_manutenzione_letta_dal_database_al_massimo_ogni_15_secondi(repo, monkeypatch):
    servizio, _ = servizio_finto(repo)
    letture = []
    originale = repo.manutenzione

    async def conta():
        letture.append(1)
        return await originale()

    monkeypatch.setattr(repo, "manutenzione", conta)
    for _ in range(5):
        assert await servizio._messaggio_manutenzione() is None
    assert len(letture) == 1


async def test_comando_manutenzione_solo_owner(repo, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", repo._pool_provider)
    servizio, _ = servizio_finto(repo)
    imposta_servizio_ai(servizio)
    try:
        cog = cfg_mod.AiConfigCog(bot=None)
        altro = fake_interaction(guild=fake_guild(G), user=fake_member(U + 1))
        await cog.manutenzione.callback(cog, altro, True, None)
        assert "solo del proprietario" in altro.response.send_message.call_args.args[0]
        assert await repo.manutenzione() is None
        owner = fake_interaction(guild=fake_guild(G), user=fake_member(config.OWNER_ID))
        await cog.manutenzione.callback(cog, owner, True, "Aggiorniamo i modelli")
        assert await repo.manutenzione() == "Aggiorniamo i modelli"
        await cog.manutenzione.callback(cog, owner, False, None)
        assert await repo.manutenzione() is None
    finally:
        imposta_servizio_ai(None)


# ---------------------------------------------------------------- prova gratuita
def test_prova_attiva_per_sette_giorni():
    ora = datetime.now(timezone.utc)
    assert not prova_attiva(None) and not prova_finita(None)
    assert prova_attiva(ora - timedelta(days=GIORNI_PROVA - 1), ora)
    assert prova_finita(ora - timedelta(days=GIORNI_PROVA + 1), ora)


async def test_premium_senza_sblocco_usa_la_prova_una_volta_sola(repo, monkeypatch):
    from core import premium

    servizio, trasporto = servizio_finto(repo)
    await repo.registra_consenso(G, U, True)
    monkeypatch.setattr(premium.registry, "is_module_premium", lambda nome: nome == "ai")

    async def mai(guild_id, nome, bot=None):
        return False

    monkeypatch.setattr(premium, "guild_has_premium_access", mai)
    assert (await _motivo(servizio, _r())).motivo == "premium"
    cfg = await repo.avvia_prova(G)
    assert cfg.prova_inizio is not None
    assert (await servizio.richiedi(_r())).testo
    # una seconda chiamata non rinnova la prova
    assert (await repo.avvia_prova(G)).prova_inizio == cfg.prova_inizio
    await repo.imposta(G, prova_inizio=datetime.now(timezone.utc) - timedelta(days=GIORNI_PROVA + 1))
    assert (await _motivo(servizio, _r(testo="un'altra"))).motivo == "prova_finita"
    assert len(trasporto.chiamate) == 1


async def test_consenso_fa_partire_la_prova_solo_se_serve(repo, monkeypatch):
    from core import premium

    monkeypatch.setattr(ai_repo, "_pool_provider", repo._pool_provider)
    cog = cfg_mod.AiConfigCog(bot=None)
    servizio, _ = servizio_finto(repo)
    imposta_servizio_ai(servizio)
    try:
        # modulo non premium: nessuna prova
        i = fake_interaction(guild=fake_guild(G), user=fake_member(U))
        i.guild_id = G
        await cog.attiva.callback(cog, i, True)
        await i.response.send_message.call_args.kwargs["view"].conferma.callback(i)
        assert (await repo.get_config(G)).prova_inizio is None
        # modulo premium e non sbloccato: la prova parte e lo dice
        monkeypatch.setattr(premium.registry, "is_module_premium", lambda nome: nome == "ai")

        async def mai(guild_id, nome, bot=None):
            return False

        monkeypatch.setattr(premium, "guild_has_premium_access", mai)
        j = fake_interaction(guild=fake_guild(G), user=fake_member(U))
        j.guild_id = G
        await cog.attiva.callback(cog, j, True)
        await j.response.send_message.call_args.kwargs["view"].conferma.callback(j)
        assert (await repo.get_config(G)).prova_inizio is not None
        assert "prova gratuita" in j.response.edit_message.call_args.kwargs["content"]
    finally:
        imposta_servizio_ai(None)


# ---------------------------------------------------------------- coda
async def test_coda_tiene_al_massimo_i_posti_e_gli_altri_aspettano():
    coda = CodaAI(posti=2, max_attesa=10, max_per_server=10, timeout=2)
    dentro, massimo = 0, 0

    async def lavoro():
        nonlocal dentro, massimo
        async with coda.posto(1):
            dentro += 1
            massimo = max(massimo, dentro)
            await asyncio.sleep(0.02)
            dentro -= 1

    await asyncio.gather(*(lavoro() for _ in range(6)))
    assert massimo == 2 and coda.in_attesa == 0


async def test_coda_piena_e_limite_per_server():
    coda = CodaAI(posti=1, max_attesa=3, max_per_server=2, timeout=1)
    libera = asyncio.Event()

    async def tiene(guild):
        async with coda.posto(guild):
            await libera.wait()

    primo = asyncio.create_task(tiene(1))
    await asyncio.sleep(0)
    a, b = asyncio.create_task(tiene(1)), asyncio.create_task(tiene(1))
    await asyncio.sleep(0.01)
    with pytest.raises(CodaPiena) as per_server:
        async with coda.posto(1):
            pass
    assert per_server.value.motivo == "coda_piena"
    c = asyncio.create_task(tiene(2))  # un altro server trova ancora posto in fila
    await asyncio.sleep(0.01)
    assert coda.in_attesa == 3
    with pytest.raises(CodaPiena):
        async with coda.posto(3):
            pass
    libera.set()
    await asyncio.gather(primo, a, b, c)
    assert coda.in_attesa == 0


async def test_coda_attesa_troppo_lunga_rinuncia():
    coda = CodaAI(posti=1, timeout=0.05)
    libera = asyncio.Event()

    async def tiene():
        async with coda.posto(1):
            await libera.wait()

    primo = asyncio.create_task(tiene())
    await asyncio.sleep(0)
    with pytest.raises(CodaPiena) as exc:
        async with coda.posto(1):
            pass
    assert exc.value.motivo == "coda_scaduta" and coda.in_attesa == 0
    libera.set()
    await primo


async def test_servizio_con_coda_piena_da_la_risposta_locale(repo):
    servizio, trasporto = servizio_finto(repo)
    await repo.registra_consenso(G, U, True)
    servizio.coda = CodaAI(posti=1, max_attesa=0)
    async with servizio.coda.posto(G):
        errore = await _motivo(servizio, _r())
    assert errore.motivo == "coda_piena" and "in fila" in errore.testo
    assert trasporto.chiamate == []
    assert (await servizio.richiedi(_r())).testo  # posto liberato: riparte


# ---------------------------------------------------------------- bottone «Apri nel pannello» (§25.27)
def test_link_configurazione_porta_alla_pagina_giusta():
    from core.ai_testi_logic import ComandoNoto, link_configurazione

    c = lambda p: ComandoNoto(p, "x")  # noqa: E731
    url = "https://pannello.example/"
    assert link_configurazione(url, 5, [c("ai privacy")]) == "https://pannello.example/server/5/ai"
    assert link_configurazione(url, 5, [c("admin premium aspetto")]).endswith("/server/5/aspetto")
    assert link_configurazione(url, 5, [c("admin premium stato")]).endswith("/server/5/premium")
    assert link_configurazione(url, 5, [c("admin lingua set")]).endswith("/server/5")
    # il primo comando di configurazione vince; i comandi d'uso non portano al pannello
    assert link_configurazione(url, 5, [c("mod timeout"), c("ai attiva")]).endswith("/ai")
    assert link_configurazione(url, 5, [c("mod timeout")]) is None
    assert link_configurazione("", 5, [c("ai attiva")]) is None
    assert link_configurazione(url, None, [c("ai attiva")]) is None


def test_bottone_configurazione_e_un_link():
    from cogs.ai.helpdesk import bottone_configurazione
    from core.ai_testi_logic import ComandoNoto

    b = bottone_configurazione("https://p.example", 9, [ComandoNoto("ai stato", "x")])
    assert b.url == "https://p.example/server/9/ai" and b.label == "Apri nel pannello"
    assert bottone_configurazione("https://p.example", 9, [ComandoNoto("mod ban", "x")]) is None


async def test_chiedi_aggiunge_il_bottone_del_pannello_per_un_comando_di_configurazione(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import cogs.ai.helpdesk as helpdesk
    import core.ai_servizio as ai_servizio
    from cogs.utility import command_search as modulo
    from tests.test_command_search_bug147 import _albero_con_richiedi

    monkeypatch.setattr(ai_servizio, "servizio_ai", lambda: SimpleNamespace(controlla_accesso=AsyncMock()))
    citati = [SimpleNamespace(percorso="ai attiva", descrizione="Accende l'AI", gruppo="ai", moduli=(), livelli=())]
    monkeypatch.setattr(helpdesk, "risposta_ai_chiedi", AsyncMock(return_value=("Usa /ai attiva", citati, None)))
    finto = SimpleNamespace(WEB_PANEL_PUBLIC_URL="https://p.example", WIKI_BASE_URL="", MAIN_GUILD_ID=1)
    monkeypatch.setattr(modulo, "config", finto)
    cog = modulo.CommandSearchCog(_albero_con_richiedi())
    monkeypatch.setattr(cog, "_comandi_accessibili", AsyncMock(return_value=[]))
    monkeypatch.setattr(cog, "_ids", AsyncMock(return_value={}))
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U))
    i.guild_id = G
    i.is_guild_integration = lambda: True
    assert await cog._risposta_ai(i, "come accendo l'AI?") is True
    view = i.followup.send.call_args.kwargs["view"]
    assert [b.url for b in view.children if getattr(b, "url", None) and "p.example" in b.url] == [f"https://p.example/server/{G}/ai"]


async def test_comandi_ai_premium_aperti_durante_la_prova(repo, monkeypatch):
    """I comandi del modulo AI (riassumi, spiega, stile, costruisci) valgono anche durante la prova (§25.23)."""
    from cogs.ai import summaries
    from core import premium

    monkeypatch.setattr(ai_repo, "_pool_provider", repo._pool_provider)
    monkeypatch.setattr(premium.registry, "is_module_premium", lambda nome: nome == "ai")

    async def mai(guild_id, nome, bot=None):
        return False

    monkeypatch.setattr(premium, "guild_has_premium_access", mai)
    comandi = [summaries.AiRiassuntiCog.riassumi, summaries.AiRiassuntiCog.spiega,
               summaries.AiRiassuntiCog.stile, cfg_mod.AiConfigCog.costruisci]
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U))

    async def passa(comando):
        try:
            return all([await c(i) for c in comando.callback.__discord_app_commands_checks__])
        except premium.ModuleNotUnlockedError:
            return False

    assert all(c.callback.__discord_app_commands_checks__ for c in comandi)
    assert not any([await passa(c) for c in comandi])  # premium, nessuna prova
    await repo.avvia_prova(G)
    assert all([await passa(c) for c in comandi])  # prova in corso
    await repo.imposta(G, prova_inizio=datetime.now(timezone.utc) - timedelta(days=GIORNI_PROVA + 1))
    assert not any([await passa(c) for c in comandi])  # prova finita

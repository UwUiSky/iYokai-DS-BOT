"""
tests/test_ai_assistente.py
===========================
Contorno della risposta di -chiedi (§25.12, §25.28–§25.31, §25.73, §25.87, §25.101): scoperta senza AI, stato dei
comandi, alternative, attivazione dei moduli, traguardo, preferenza personale. Database vero, fornitore finto.
"""

from unittest.mock import AsyncMock

import pytest

from cogs.ai import _assistente as ass
from core import command_search_logic as ricerca
from core.ai_servizio import AINonDisponibile, RichiestaAI, imposta_servizio_ai
from core.database import db
from core.repositories.ai_repo import ai_repo
from tests.support.ai_finto import TrasportoFinto, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G, U = 7101, 7102


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    from cogs.ai._comune import registra_modulo_ai

    registra_modulo_ai()
    yield ai_repo
    imposta_servizio_ai(None)


def _inter(user_id=U):
    i = fake_interaction(guild=fake_guild(G), user=fake_member(user_id))
    i.guild_id = G
    i.channel_id = i.channel.id
    i.client = None
    return i


def cmd(percorso, moduli=()):
    return ricerca.ComandoInfo(percorso, "descr", percorso.split()[0], (), moduli=tuple(moduli))


async def test_scoperta_risponde_anche_con_ai_ferma(repo):
    i = _inter()
    ok = await ass.risposta_locale(i, "cosa posso fare qui?", [cmd("fun gioca"), cmd("level balance")], G)
    assert ok
    embed = i.followup.send.call_args.kwargs["embed"]
    assert embed.title == "Cosa puoi fare qui" and "/fun gioca" in embed.description


async def test_guida_del_server_risponde_senza_ai(repo):
    await repo.conoscenza_aggiungi(G, "Regole del server", "Sii gentile.", U)
    i = _inter()
    assert await ass.risposta_locale(i, "regole del server", [], G)
    assert i.followup.send.call_args.kwargs["embed"].description == "Sii gentile."
    assert not await ass.risposta_locale(_inter(), "come banno qualcuno che spamma ovunque nel server", [], G)


async def test_arricchisci_stato_alternative_attivazione_e_traguardo(repo, monkeypatch):
    from core.premium import registry

    nome_modulo = "ai"
    assert registry.get(nome_modulo) is not None
    await db.set_module_active_for_guild(G, nome_modulo, False, changed_by=U)
    citato = cmd("ticket apri", moduli=(nome_modulo,))
    tutti = [citato, cmd("utility report")]

    async def ids(serve):
        return {"ticket": 5, "utility": 6}

    i = _inter()
    out = await ass.arricchisci(i, "voglio parlare con lo staff", [citato], [citato], tutti, ids, G)
    campi = dict(out.campi)
    assert "spento in questo server" in campi["Stato"]
    assert "utility report" in campi["Alternative"] or "</utility report:6>" in campi["Alternative"]
    assert campi["Traguardo"].startswith("Traguardo sbloccato")
    assert [b.label for b in out.bottoni][0].startswith("Attiva")
    # il traguardo è dato una volta sola
    out2 = await ass.arricchisci(i, "voglio parlare con lo staff", [citato], [citato], tutti, ids, G)
    assert "Traguardo" not in dict(out2.campi)
    assert await repo.traguardi(U) == ["primo_comando_ai"]


async def test_attiva_modulo_solo_per_admin(repo, monkeypatch):
    await db.set_module_active_for_guild(G, "ai", False, changed_by=U)
    b = ass._AttivaModulo("ai")
    b._view = ass.AssistenteView([b])
    i = _inter()
    monkeypatch.setattr(ass, "puo_usare", AsyncMock(return_value=False))
    await b.callback(i)
    assert not await db.is_module_active_for_guild(G, "ai")
    assert "Solo chi amministra" in i.response.send_message.call_args.args[0]
    monkeypatch.setattr(ass, "puo_usare", AsyncMock(return_value=True))
    i2 = _inter()
    await b.callback(i2)
    assert await db.is_module_active_for_guild(G, "ai")


async def test_preferenza_personale_spegne_le_risposte_ai(repo):
    servizio, trasporto = servizio_finto(repo, trasporto=TrasportoFinto())
    imposta_servizio_ai(servizio)
    await repo.registra_consenso(G, U, True)
    r = RichiestaAI(user_id=U, funzione="chiedi", tipo="chat", testo="ciao", guild_id=G)
    assert (await servizio.richiedi(r)).testo
    await repo.imposta_assistente(U, False)
    servizio.dimentica_preferenza(U)
    with pytest.raises(AINonDisponibile) as exc:
        await servizio.richiedi(RichiestaAI(user_id=U, funzione="chiedi", tipo="chat", testo="altro", guild_id=G))
    assert exc.value.motivo == "utente_spento"
    # i lavori del server (non della persona) continuano
    assert (await servizio.richiedi(RichiestaAI(user_id=U, funzione="moderazione", tipo="chat", testo="x1", guild_id=G, conta_utente=False))).testo


async def test_comando_preferenza_salva_e_ricarica(repo):
    from cogs.ai.personale import AiPersonaleCog

    servizio, _ = servizio_finto(repo, trasporto=TrasportoFinto())
    imposta_servizio_ai(servizio)
    cog = AiPersonaleCog(bot=None)
    i = _inter()
    await cog.preferenza.callback(cog, i, False)
    assert not await servizio.assistente_acceso(U) and not await repo.assistente_acceso(U)
    await cog.preferenza.callback(cog, _inter(), True)
    assert await servizio.assistente_acceso(U)

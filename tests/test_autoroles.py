"""
tests/test_autoroles.py
=======================
NF-07 (#78): ruoli automatici all'ingresso, ruoli ridati a chi rientra,
ruoli dati dopo un ritardo. Logica pura, archivio su PostgreSQL vero, cog.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.autoroles as modulo
from cogs.utility.autoroles import AutorolesCog
from core.autorole_logic import (
    MAX_REGOLE,
    RegolaAutoruolo,
    regola_vale_per,
    ruoli_da_ridare_se_tolti,
    ruoli_da_sincronizzare,
    membro_in_attesa,
    piano_ingresso,
    ruoli_da_ridare,
    ruoli_da_ricordare,
)
from core.repositories.autorole_repo import AutoroleRepository
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
)
from tests.support.percorsi import comando_nel_gruppo

ORA = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- logica pura
def test_piano_ingresso_divide_subito_e_ritardati():
    regole = [RegolaAutoruolo(1, 0), RegolaAutoruolo(2, 600), RegolaAutoruolo(3, 0)]
    subito, dopo = piano_ingresso(regole, is_bot=False, ruoli_posseduti=set())
    assert subito == [1, 3]
    assert dopo == [(2, 600)]


def test_piano_ingresso_niente_ai_bot():
    assert piano_ingresso([RegolaAutoruolo(1, 0)], is_bot=True, ruoli_posseduti=set()) == ([], [])


def test_piano_ingresso_salta_i_ruoli_gia_posseduti():
    subito, dopo = piano_ingresso(
        [RegolaAutoruolo(1, 0), RegolaAutoruolo(2, 60)], is_bot=False, ruoli_posseduti={1, 2}
    )
    assert subito == [] and dopo == []


def test_ruoli_da_ricordare_scarta_everyone_e_gestiti():
    ruoli = [fake_role(0, "@everyone"), fake_role(5, "Giocatore"), fake_role(6, "Boost", managed=True)]
    assert ruoli_da_ricordare(ruoli) == [5]


def test_ruoli_da_ridare_entro_i_giorni():
    uscito = ORA - timedelta(days=29, hours=23)
    assert ruoli_da_ridare([5, 6], uscito, ORA, giorni=30) == [5, 6]


def test_ruoli_da_ridare_oltre_i_giorni_niente():
    uscito = ORA - timedelta(days=30, minutes=1)
    assert ruoli_da_ridare([5, 6], uscito, ORA, giorni=30) == []


def test_ruoli_da_ridare_non_supera_mai_30_giorni():
    uscito = ORA - timedelta(days=45)
    assert ruoli_da_ridare([5], uscito, ORA, giorni=90) == []


@pytest.mark.parametrize(
    "in_attesa_discord, verifica, ha_ruolo_verificato, atteso",
    [
        (True, False, False, True),    # schermata regole di Discord non accettata
        (False, True, False, True),    # verifica attiva e membro non ancora verificato
        (False, True, True, False),
        (False, False, False, False),
    ],
)
def test_membro_in_attesa(in_attesa_discord, verifica, ha_ruolo_verificato, atteso):
    assert membro_in_attesa(in_attesa_discord, verifica, ha_ruolo_verificato) is atteso


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return AutoroleRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_regole_aggiungi_elenca_rimuovi(repo):
    assert await repo.add_rule(1, 10, 0, created_by=7)
    assert await repo.add_rule(1, 11, 300, created_by=7)
    regole = await repo.list_rules(1)
    assert [(r.role_id, r.delay_seconds) for r in regole] == [(10, 0), (11, 300)]
    assert await repo.remove_rule(1, 10) is True
    assert await repo.remove_rule(1, 10) is False


@pytest.mark.asyncio
async def test_regola_stesso_ruolo_aggiorna_il_ritardo(repo):
    await repo.add_rule(1, 10, 0, created_by=7)
    await repo.add_rule(1, 10, 900, created_by=7)
    regole = await repo.list_rules(1)
    assert len(regole) == 1 and regole[0].delay_seconds == 900


@pytest.mark.asyncio
async def test_tetto_delle_regole_per_server(repo):
    for i in range(MAX_REGOLE):
        assert await repo.add_rule(1, 100 + i, 0, created_by=7)
    assert await repo.add_rule(1, 999, 0, created_by=7) is False
    assert await repo.add_rule(2, 999, 0, created_by=7) is True  # un altro server è libero


@pytest.mark.asyncio
async def test_memoria_dei_ruoli_si_consuma_una_volta(repo):
    await repo.save_memory(1, 50, [5, 6], ORA)
    trovato = await repo.pop_memory(1, 50)
    assert trovato is not None and trovato.role_ids == [5, 6]
    assert await repo.pop_memory(1, 50) is None


@pytest.mark.asyncio
async def test_config_ricorda(repo):
    assert (await repo.get_config(1)).remember_enabled is False
    await repo.set_remember(1, True, 14)
    config = await repo.get_config(1)
    assert config.remember_enabled and config.remember_days == 14


# -------------------------------------------------------------------------- cog
@pytest.fixture
def cog(monkeypatch):
    bot = MagicMock()
    c = AutorolesCog(bot)
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", db_finto)
    repo_finto = MagicMock()
    repo_finto.list_rules = AsyncMock(return_value=[])
    repo_finto.get_config = AsyncMock(
        return_value=MagicMock(remember_enabled=False, remember_days=30)
    )
    repo_finto.add_rule = AsyncMock(return_value=True)
    repo_finto.save_memory = AsyncMock()
    repo_finto.pop_memory = AsyncMock(return_value=None)
    monkeypatch.setattr(modulo, "autorole_repo", repo_finto)
    monkeypatch.setattr(modulo, "scheduler", MagicMock(schedule=AsyncMock(return_value=1), list_pending_for_user=AsyncMock(return_value=[])))
    monkeypatch.setattr(modulo, "raid_in_corso", lambda guild_id: False)
    # nessuna verifica attiva (la prova della verifica è a parte)
    monkeypatch.setattr(AutorolesCog, "_ruolo_verificato_atteso", AsyncMock(return_value=None))
    c.repo = repo_finto
    return c


def _server_con_ruoli(*ids):
    server = fake_guild()
    ruoli = {i: fake_role(i, f"R{i}", position=1) for i in ids}
    server.get_role = lambda rid: ruoli.get(rid)
    server.me.top_role = fake_role(900, "Bot", position=50)
    return server, ruoli


@pytest.mark.asyncio
async def test_ingresso_da_i_ruoli_subito_e_programma_i_ritardati(cog):
    server, ruoli = _server_con_ruoli(10, 11)
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 0), RegolaAutoruolo(11, 600)]
    membro = fake_member(50)
    membro.guild = server
    membro.pending = False
    membro.add_roles = AsyncMock()
    await cog.on_member_join(membro)
    membro.add_roles.assert_awaited_once()
    assert membro.add_roles.await_args.args == (ruoli[10],)
    modulo.scheduler.schedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingresso_bot_non_riceve_ruoli(cog):
    server, _ = _server_con_ruoli(10)
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 0)]
    bot_membro = fake_member(51, bot=True)
    bot_membro.guild = server
    bot_membro.pending = False
    bot_membro.add_roles = AsyncMock()
    await cog.on_member_join(bot_membro)
    bot_membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_raid_in_corso_ruoli_in_pausa(cog, monkeypatch):
    monkeypatch.setattr(modulo, "raid_in_corso", lambda guild_id: True)
    server, _ = _server_con_ruoli(10)
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 0)]
    membro = fake_member(50)
    membro.guild = server
    membro.pending = False
    membro.add_roles = AsyncMock()
    await cog.on_member_join(membro)
    membro.add_roles.assert_not_awaited()
    # in pausa, non persi: il ruolo viene programmato dopo la fine del raid
    modulo.scheduler.schedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_ruolo_non_assegnabile_viene_saltato_senza_errore(cog):
    server, ruoli = _server_con_ruoli(10, 11)
    ruoli[10].managed = True  # check_role_assignable lo rifiuta
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 0), RegolaAutoruolo(11, 0)]
    membro = fake_member(50)
    membro.guild = server
    membro.pending = False
    membro.add_roles = AsyncMock()
    await cog.on_member_join(membro)
    assert membro.add_roles.await_args.args == (ruoli[11],)


@pytest.mark.asyncio
async def test_membro_in_attesa_non_riceve_i_ruoli_all_ingresso(cog):
    server, _ = _server_con_ruoli(10)
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 0)]
    membro = fake_member(50)
    membro.guild = server
    membro.pending = True
    membro.add_roles = AsyncMock()
    await cog.on_member_join(membro)
    membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_uscita_salva_i_ruoli_se_attivo(cog):
    cog.repo.get_config.return_value = MagicMock(remember_enabled=True, remember_days=30)
    server, _ = _server_con_ruoli()
    membro = fake_member(50, roles=[fake_role(0, "@everyone"), fake_role(5, "G")])
    membro.guild = server
    await cog.on_member_remove(membro)
    cog.repo.save_memory.assert_awaited_once()
    assert cog.repo.save_memory.await_args.args[2] == [5]


@pytest.mark.asyncio
async def test_uscita_non_salva_se_spento(cog):
    server, _ = _server_con_ruoli()
    membro = fake_member(50, roles=[fake_role(5, "G")])
    membro.guild = server
    await cog.on_member_remove(membro)
    cog.repo.save_memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_rientro_riprende_i_ruoli_ricordati(cog):
    server, ruoli = _server_con_ruoli(5, 6)
    cog.repo.get_config.return_value = MagicMock(remember_enabled=True, remember_days=30)
    cog.repo.pop_memory.return_value = MagicMock(
        role_ids=[5, 6], left_at=datetime.now(timezone.utc) - timedelta(days=3)
    )
    membro = fake_member(50)
    membro.guild = server
    membro.pending = False
    membro.add_roles = AsyncMock()
    await cog.on_member_join(membro)
    assert set(membro.add_roles.await_args.args) == {ruoli[5], ruoli[6]}


@pytest.mark.asyncio
async def test_comando_aggiungi_rifiuta_ruolo_non_assegnabile(cog):
    server, ruoli = _server_con_ruoli(10)
    ruoli[10].managed = True
    interazione = fake_interaction(guild=server, user=fake_member(7))
    interazione.user.top_role = fake_role(800, "Admin", position=60)
    await cog.auto_aggiungi.callback(cog, interazione, ruoli[10], 0)
    cog.repo.add_rule.assert_not_awaited()
    assert "gestito" in interazione.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_comando_aggiungi_ok(cog):
    server, ruoli = _server_con_ruoli(10)
    interazione = fake_interaction(guild=server, user=fake_member(7))
    interazione.user.top_role = fake_role(800, "Admin", position=60)
    await cog.auto_aggiungi.callback(cog, interazione, ruoli[10], 5)
    cog.repo.add_rule.assert_awaited_once_with(
        server.id, 10, 300, created_by=7, richiesti=[], esclusi=[], ridai=False
    )


@pytest.mark.asyncio
async def test_i_comandi_stanno_sotto_gestione_ruoli():
    from discord.ext import commands as ext

    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("auto-aggiungi", "auto-rimuovi", "auto-elenco", "auto-ricorda"):
        assert comando_nel_gruppo("gestione", f"ruoli {nome}") is not None


@pytest.mark.asyncio
async def test_verifica_attiva_il_ruolo_arriva_dopo(cog, monkeypatch):
    monkeypatch.setattr(AutorolesCog, "_ruolo_verificato_atteso", AsyncMock(return_value=77))
    server, ruoli = _server_con_ruoli(10)
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 0)]
    prima = fake_member(50, roles=[])
    prima.guild = server
    prima.pending = False
    prima.add_roles = AsyncMock()
    await cog.on_member_join(prima)
    prima.add_roles.assert_not_awaited()
    # dopo la verifica il membro ha il ruolo di verificato: ora scattano i ruoli
    dopo = fake_member(50, roles=[fake_role(77, "Verificato")])
    dopo.guild = server
    dopo.pending = False
    dopo.add_roles = AsyncMock()
    await cog.on_member_update(prima, dopo)
    dopo.add_roles.assert_awaited_once()
    assert dopo.add_roles.await_args.args == (ruoli[10],)


@pytest.mark.asyncio
async def test_regole_accettate_dopo_membership_screening(cog):
    server, ruoli = _server_con_ruoli(10)
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 0)]
    prima = fake_member(50)
    prima.guild = server
    prima.pending = True
    dopo = fake_member(50)
    dopo.guild = server
    dopo.pending = False
    dopo.add_roles = AsyncMock()
    await cog.on_member_update(prima, dopo)
    dopo.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_il_ruolo_ritardato_non_si_da_se_la_regola_e_stata_tolta(cog):
    server, ruoli = _server_con_ruoli(10)
    membro = fake_member(50)
    membro.guild = server
    membro.pending = False
    membro.add_roles = AsyncMock()
    server.get_member = lambda uid: membro
    cog.bot.get_guild = lambda gid: server
    cog.repo.list_rules.return_value = []
    await cog.handle_autorole_give(server.id, 50, {"role_id": 10})
    membro.add_roles.assert_not_awaited()
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 600)]
    await cog.handle_autorole_give(server.id, 50, {"role_id": 10})
    membro.add_roles.assert_awaited_once()


def _ricordati(cog, ruoli_ids):
    cog.repo.get_config.return_value = MagicMock(remember_enabled=True, remember_days=30)
    cog.repo.pop_memory.return_value = MagicMock(
        role_ids=ruoli_ids, left_at=datetime.now(timezone.utc) - timedelta(days=1)
    )


@pytest.mark.asyncio
async def test_rientro_in_attesa_non_riprende_i_ruoli_ricordati(cog):
    server, _ = _server_con_ruoli(5)
    _ricordati(cog, [5])
    membro = fake_member(50)
    membro.guild = server
    membro.pending = True
    membro.add_roles = AsyncMock()
    await cog.on_member_join(membro)
    membro.add_roles.assert_not_awaited()
    cog.repo.pop_memory.assert_not_awaited()  # la memoria resta per quando avrà accettato le regole


@pytest.mark.asyncio
async def test_rientro_durante_un_raid_programma_i_ruoli_ricordati(cog, monkeypatch):
    monkeypatch.setattr(modulo, "raid_in_corso", lambda guild_id: True)
    server, _ = _server_con_ruoli(5)
    _ricordati(cog, [5])
    membro = fake_member(50)
    membro.guild = server
    membro.pending = False
    membro.add_roles = AsyncMock()
    await cog.on_member_join(membro)
    membro.add_roles.assert_not_awaited()
    assert modulo.scheduler.schedule.await_args.args[4] == {"role_id": 5, "ricordato": True}


@pytest.mark.asyncio
async def test_il_ruolo_ricordato_programmato_non_ha_bisogno_della_regola(cog):
    server, _ = _server_con_ruoli(5)
    membro = fake_member(50)
    membro.guild = server
    membro.pending = False
    membro.add_roles = AsyncMock()
    server.get_member = lambda uid: membro
    cog.bot.get_guild = lambda gid: server
    cog.repo.list_rules.return_value = []
    await cog.handle_autorole_give(server.id, 50, {"role_id": 5, "ricordato": True})
    membro.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_ruolo_ritardato_non_scatta_durante_un_raid_o_con_membro_in_attesa(cog, monkeypatch):
    server, _ = _server_con_ruoli(10)
    membro = fake_member(50)
    membro.guild = server
    membro.pending = True
    membro.add_roles = AsyncMock()
    server.get_member = lambda uid: membro
    cog.bot.get_guild = lambda gid: server
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 600)]
    await cog.handle_autorole_give(server.id, 50, {"role_id": 10})
    membro.add_roles.assert_not_awaited()
    membro.pending = False
    monkeypatch.setattr(modulo, "raid_in_corso", lambda guild_id: True)
    await cog.handle_autorole_give(server.id, 50, {"role_id": 10})
    membro.add_roles.assert_not_awaited()
    modulo.scheduler.schedule.assert_awaited_once()  # ripianificato a raid finito


@pytest.mark.asyncio
async def test_uscita_non_ricorda_i_ruoli_a_tempo(cog):
    cog.repo.get_config.return_value = MagicMock(remember_enabled=True, remember_days=30)
    server, _ = _server_con_ruoli()
    membro = fake_member(50, roles=[fake_role(5, "G"), fake_role(6, "Temporaneo")])
    membro.guild = server
    modulo.scheduler.list_pending_for_user = AsyncMock(
        side_effect=lambda uid, tipo, lim: [{"guild_id": server.id, "payload": {"role_id": 6}}]
        if tipo == modulo.ROLEMENU_TEMP_ACTION_TYPE else []
    )
    await cog.on_member_remove(membro)
    assert cog.repo.save_memory.await_args.args[2] == [5]


# ------------------------------------------------- condizioni (catalogo #123)
def test_regola_con_ruoli_richiesti_ed_esclusi():
    regola = RegolaAutoruolo(10, 0, richiesti=(1, 2), esclusi=(3,))
    assert regola_vale_per(regola, {2})
    assert not regola_vale_per(regola, set())
    assert not regola_vale_per(regola, {1, 3})
    assert regola_vale_per(RegolaAutoruolo(10), set())


def test_piano_ingresso_rispetta_le_condizioni_dei_ruoli_subito():
    regole = [RegolaAutoruolo(10, 0, richiesti=(1,)), RegolaAutoruolo(11, 0, esclusi=(5,)), RegolaAutoruolo(12, 60, richiesti=(1,))]
    subito, dopo = piano_ingresso(regole, is_bot=False, ruoli_posseduti={5})
    assert subito == [] and dopo == [(12, 60)]  # il ritardato si ricontrolla allo scatto


def test_ridai_se_tolto_solo_con_l_opzione_e_il_diritto():
    regole = [RegolaAutoruolo(10, ridai=True), RegolaAutoruolo(11), RegolaAutoruolo(12, ridai=True, esclusi=(9,))]
    assert ruoli_da_ridare_se_tolti(regole, prima={10, 11, 12, 9}, dopo={9}) == [10]


def test_sincronizzare_da_solo_i_mancanti_con_diritto():
    regole = [RegolaAutoruolo(10), RegolaAutoruolo(11, 600), RegolaAutoruolo(12, richiesti=(7,))]
    assert ruoli_da_sincronizzare(regole, {10}) == [11]


@pytest.mark.asyncio
async def test_regola_salva_le_condizioni(repo):
    await repo.add_rule(1, 10, 0, created_by=7, richiesti=[3], esclusi=[4], ridai=True)
    regola = (await repo.list_rules(1))[0]
    assert regola.richiesti == (3,) and regola.esclusi == (4,) and regola.ridai is True


@pytest.mark.asyncio
async def test_ruolo_tolto_torna_se_ridai(cog):
    server, ruoli = _server_con_ruoli(10)
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, ridai=True)]
    prima = fake_member(50, roles=[ruoli[10]])
    prima.pending = False
    dopo = fake_member(50, roles=[])
    dopo.guild = server
    dopo.pending = False
    dopo.add_roles = AsyncMock()
    await cog.on_member_update(prima, dopo)
    assert dopo.add_roles.await_args.args == (ruoli[10],)


@pytest.mark.asyncio
async def test_ritardato_non_scatta_se_la_condizione_non_vale_piu(cog):
    server, _ = _server_con_ruoli(10)
    membro = fake_member(50)
    membro.guild = server
    membro.pending = False
    membro.add_roles = AsyncMock()
    server.get_member = lambda uid: membro
    cog.bot.get_guild = lambda gid: server
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, 600, richiesti=(3,))]
    await cog.handle_autorole_give(server.id, 50, {"role_id": 10})
    membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_sincronizza_i_membri_presenti(cog, monkeypatch):
    monkeypatch.setattr(modulo.asyncio, "sleep", AsyncMock())
    server, ruoli = _server_con_ruoli(10)
    server.chunked = True
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10)]
    senza, con, robot = fake_member(50), fake_member(51, roles=[ruoli[10]]), fake_member(52, bot=True)
    for m in (senza, con, robot):
        m.pending = False
    server.members = [senza, con, robot]
    canale = MagicMock(send=AsyncMock())
    cog.sincronie.add(server.id)
    assert await cog.sincronizza(server, canale) == (1, 0)
    assert senza.add_roles.await_args.args == (ruoli[10],)
    con.add_roles.assert_not_awaited()
    robot.add_roles.assert_not_awaited()
    assert server.id not in cog.sincronie
    assert "1 membri" in canale.send.await_args.args[0]


@pytest.mark.asyncio
async def test_i_ruoli_dati_a_tempo_non_si_ricordano(cog):
    server, ruoli = _server_con_ruoli(5, 6)
    cog.repo.get_config.return_value = MagicMock(remember_enabled=True, remember_days=30)
    modulo.scheduler.list_pending_for_user = AsyncMock(
        side_effect=lambda uid, tipo, n: [{"guild_id": server.id, "payload": {"dati": [6], "tolti": []}}]
        if tipo == modulo.RUOLI_TEMPORANEI_ACTION_TYPE else []
    )
    membro = fake_member(50, roles=[ruoli[5], ruoli[6]])
    membro.guild = server
    await cog.on_member_remove(membro)
    assert cog.repo.save_memory.await_args.args[2] == [5]


# ------------------------------------------- condizioni che si escludono a vicenda
def test_due_regole_che_si_escludono_non_danno_entrambi_i_ruoli():
    """A «non con B» e B «non con A»: chi non ha nessuno dei due ne riceve uno solo."""
    regole = [RegolaAutoruolo(10, esclusi=(11,)), RegolaAutoruolo(11, esclusi=(10,))]
    subito, _ = piano_ingresso(regole, is_bot=False, ruoli_posseduti=set())
    assert subito == [10]
    assert ruoli_da_sincronizzare(regole, set()) == [10]


def test_regola_esclusa_da_un_ruolo_appena_dato():
    """A «non con B», B senza condizioni: dare B toglierebbe il diritto ad A, quindi B non si dà."""
    regole = [RegolaAutoruolo(10, esclusi=(11,)), RegolaAutoruolo(11)]
    assert ruoli_da_sincronizzare(regole, set()) == [10]


def test_regola_che_richiede_un_ruolo_dato_nello_stesso_giro():
    regole = [RegolaAutoruolo(10, richiesti=(11,)), RegolaAutoruolo(11)]
    subito, _ = piano_ingresso(regole, is_bot=False, ruoli_posseduti=set())
    assert sorted(subito) == [10, 11]


def test_ridai_due_ruoli_che_si_escludono_ne_ridà_uno():
    regole = [RegolaAutoruolo(10, ridai=True, esclusi=(11,)), RegolaAutoruolo(11, ridai=True, esclusi=(10,))]
    assert ruoli_da_ridare_se_tolti(regole, prima={10, 11}, dopo=set()) == [10]


@pytest.mark.asyncio
async def test_ridai_se_tolto_non_fa_ping_pong_all_infinito(cog):
    """Un altro bot che toglie sempre il ruolo: il nostro lo ridà poche volte, poi smette."""
    server, ruoli = _server_con_ruoli(10)
    cog.repo.list_rules.return_value = [RegolaAutoruolo(10, ridai=True)]
    dopo = fake_member(50, roles=[])
    dopo.guild = server
    dopo.pending = False
    dopo.add_roles = AsyncMock()
    for _ in range(20):
        prima = fake_member(50, roles=[ruoli[10]])
        prima.pending = False
        await cog.on_member_update(prima, dopo)
    assert 1 <= dopo.add_roles.await_count <= 3

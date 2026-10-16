"""
tests/test_ruoli_strumenti.py
=============================
Catalogo #123: strumenti sui ruoli (`/ruoli`, `/utility ruolo`). Logica
pura, archivio dei ruoli a scelta su PostgreSQL vero, comandi del cog.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.ruoli_strumenti as modulo
from cogs.utility.ruoli_strumenti import OperazioneMassa, RuoliStrumentiCog, motivo_audit
from core.repositories.self_role_repo import SelfRoleRepository
from core.ruoli_strumenti_logic import (
    AZIONE_DAI,
    AZIONE_TOGLI,
    CHI_BOT,
    CHI_UMANI,
    MAX_RUOLI_SCELTA,
    RUOLI_TEMPORANEI_ACTION_TYPE,
    FiltroMassa,
    colore_ruolo,
    diagnosi_ruolo,
    leggi_data,
    membri_da_toccare,
    ripristino,
    ruoli_da_azzerare,
    stima_secondi,
    stima_in_parole,
)
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.support.percorsi import comando_nel_gruppo


def _membro(uid, ruoli=(), bot=False, entrato=None):
    m = fake_member(uid, f"m{uid}", roles=list(ruoli), bot=bot)
    m.joined_at = entrato
    return m


# --------------------------------------------------------------------- logica
def test_filtro_chi_umani_e_bot():
    umano, robot = _membro(1), _membro(2, bot=True)
    assert membri_da_toccare([umano, robot], FiltroMassa(chi=CHI_UMANI), 9, AZIONE_DAI) == [umano]
    assert membri_da_toccare([umano, robot], FiltroMassa(chi=CHI_BOT), 9, AZIONE_DAI) == [robot]


def test_filtro_con_e_senza_ruolo_e_salto_di_chi_e_gia_a_posto():
    vip, base, gia = fake_role(5, "VIP"), fake_role(6, "Base"), fake_role(9, "Target")
    a, b, c = _membro(1, [vip]), _membro(2, [base]), _membro(3, [vip, gia])
    assert membri_da_toccare([a, b, c], FiltroMassa(con_ruolo=5), 9, AZIONE_DAI) == [a]
    assert membri_da_toccare([a, b, c], FiltroMassa(senza_ruolo=5), 9, AZIONE_DAI) == [b]
    assert membri_da_toccare([a, b, c], FiltroMassa(), 9, AZIONE_TOGLI) == [c]


def test_filtro_per_data_di_ingresso():
    vecchio = _membro(1, entrato=datetime(2024, 1, 1, tzinfo=timezone.utc))
    nuovo = _membro(2, entrato=datetime(2026, 6, 1, tzinfo=timezone.utc))
    soglia = leggi_data("2025-01-01")
    assert membri_da_toccare([vecchio, nuovo], FiltroMassa(entrati_dopo=soglia), 9, AZIONE_DAI) == [nuovo]
    assert membri_da_toccare([vecchio, nuovo], FiltroMassa(entrati_prima=soglia), 9, AZIONE_DAI) == [vecchio]


def test_data_scritta_male():
    assert leggi_data(None) is None
    with pytest.raises(ValueError):
        leggi_data("31/01/2026")


def test_stima_del_tempo():
    assert stima_secondi(120) == 120
    assert stima_in_parole(30) == "meno di un minuto"
    assert stima_in_parole(600) == "circa 10 min"
    assert stima_in_parole(5400) == "circa 1 h 30 min"


def test_ripristino_toglie_i_dati_e_ridà_i_tolti():
    assert ripristino([1, 2], [3, 4], posseduti={1, 4}) == ([1], [3])


def test_ruoli_da_azzerare_salta_everyone_gestiti_e_sopra_il_bot():
    bot_top = fake_role(100, "Bot", position=10)
    ruoli = [fake_role(0, "@everyone", position=0), fake_role(1, "A", position=2),
             fake_role(2, "Boost", position=3, managed=True), fake_role(3, "Capo", position=20)]
    assert [r.id for r in ruoli_da_azzerare(ruoli, bot_top)] == [1]


def test_diagnosi_ruolo():
    bot_top = fake_role(100, "Bot", position=10)
    assert diagnosi_ruolo(fake_role(1, position=2), bot_gestisce_ruoli=True, ruolo_bot_piu_alto=bot_top) == []
    problemi = diagnosi_ruolo(fake_role(2, position=20, managed=True), bot_gestisce_ruoli=False, ruolo_bot_piu_alto=bot_top)
    assert len(problemi) == 3


def test_colore_ruolo():
    assert colore_ruolo("#ff8800") == discord.Colour(0xFF8800)
    assert colore_ruolo(None) is None
    with pytest.raises(ValueError):
        colore_ruolo("rosso")


def test_motivo_audit_entro_512():
    autore = fake_member(7, "staff")
    assert len(motivo_audit(autore, "x" * 600)) == 512


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return SelfRoleRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_ruoli_a_scelta_aggiungi_elenca_togli_svuota(repo):
    assert await repo.add(1, 10, 7)
    assert await repo.add(1, 10, 7)  # già presente: resta vero, nessun doppione
    assert await repo.add(1, 11, 7)
    assert await repo.list_ids(1) == [10, 11]
    assert await repo.remove(1, 10) is True
    assert await repo.remove(1, 10) is False
    assert await repo.clear(1) == 1
    assert await repo.list_ids(1) == []


@pytest.mark.asyncio
async def test_tetto_dei_ruoli_a_scelta(repo):
    for i in range(MAX_RUOLI_SCELTA):
        assert await repo.add(1, 100 + i, 7)
    assert await repo.add(1, 999, 7) is False
    assert await repo.add(2, 999, 7) is True


# --------------------------------------------------------------------- cog
@pytest.fixture
def ambiente(monkeypatch):
    bot_top = fake_role(100, "Bot", position=50)
    me = fake_member(999, "Yokai", roles=[bot_top], bot=True)
    me.guild_permissions = discord.Permissions(manage_roles=True)
    server = fake_guild(me=me, owner_id=1)
    ruoli = {i: fake_role(i, f"R{i}", position=i) for i in (10, 11, 12)}
    server.get_role = MagicMock(side_effect=lambda i: ruoli.get(i))
    staff = fake_member(7, "staff", roles=[fake_role(800, "Admin", position=40)])
    sched = MagicMock(schedule=AsyncMock(return_value=1))
    monkeypatch.setattr(modulo, "scheduler", sched)
    repo = MagicMock(add=AsyncMock(return_value=True), remove=AsyncMock(return_value=True),
                     clear=AsyncMock(return_value=0), list_ids=AsyncMock(return_value=[10, 11]))
    monkeypatch.setattr(modulo, "self_role_repo", repo)
    cog = RuoliStrumentiCog(MagicMock())
    return SimpleNamespace(server=server, ruoli=ruoli, staff=staff, sched=sched, repo=repo, cog=cog)


def _interazione(a, user=None):
    return fake_interaction(guild=a.server, user=user or a.staff)


@pytest.mark.asyncio
async def test_dai_a_tempo_programma_il_ripristino(ambiente):
    a = ambiente
    membro = fake_member(50, "tizio", roles=[a.ruoli[11]])
    it = _interazione(a)
    await a.cog.dai.callback(a.cog, it, membro, a.ruoli[10], a.ruoli[11], None, "2h", "prova")
    membro.add_roles.assert_awaited_once()
    assert list(membro.add_roles.await_args.args) == [a.ruoli[10]]  # R11 lo aveva già
    args = a.sched.schedule.await_args.args
    assert args[2] == RUOLI_TEMPORANEI_ACTION_TYPE
    assert args[4] == {"dati": [10], "tolti": []}


@pytest.mark.asyncio
async def test_dai_rifiuta_un_ruolo_sopra_lo_staff(ambiente):
    a = ambiente
    alto = fake_role(45, "Alto", position=45)
    membro = fake_member(50, "tizio")
    it = _interazione(a)
    await a.cog.dai.callback(a.cog, it, membro, alto, None, None, None, None)
    membro.add_roles.assert_not_awaited()
    assert "sopra il tuo ruolo" in it.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_durata_oltre_30_giorni_rifiutata(ambiente):
    a = ambiente
    membro = fake_member(50, "tizio")
    it = _interazione(a)
    await a.cog.dai.callback(a.cog, it, membro, a.ruoli[10], None, None, "5w", None)
    membro.add_roles.assert_not_awaited()
    assert "30 giorni" in it.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_togli_a_tempo_e_ripristino_dello_scheduler(ambiente):
    a = ambiente
    membro = fake_member(50, "tizio", roles=[a.ruoli[10]])
    it = _interazione(a)
    await a.cog.togli.callback(a.cog, it, membro, a.ruoli[10], None, None, "1d", None)
    membro.remove_roles.assert_awaited_once()
    payload = a.sched.schedule.await_args.args[4]
    assert payload == {"dati": [], "tolti": [10]}
    # Scadenza: il membro non ha più R10, va ridato.
    membro.roles = []
    a.cog.bot.get_guild = MagicMock(return_value=a.server)
    a.server.get_member = MagicMock(return_value=membro)
    await a.cog.handle_ruoli_temporanei(a.server.id, membro.id, payload)
    assert list(membro.add_roles.await_args.args) == [a.ruoli[10]]


@pytest.mark.asyncio
async def test_massa_da_ai_filtrati_e_avvisa_a_fine_lavoro(ambiente, monkeypatch):
    a = ambiente
    monkeypatch.setattr(modulo.asyncio, "sleep", AsyncMock())
    umano, robot = fake_member(51, "u"), fake_member(52, "b", bot=True)
    a.server.members = [umano, robot]
    a.server.chunked = True
    canale = MagicMock(send=AsyncMock(), mention="#log")
    it = _interazione(a)
    await a.cog.massa.callback(a.cog, it, AZIONE_DAI, a.ruoli[10], CHI_UMANI, None, None, None, None, canale)
    await a.cog.operazioni[a.server.id].task
    umano.add_roles.assert_awaited_once()
    robot.add_roles.assert_not_awaited()
    assert "finita" in canale.send.await_args.args[0]
    assert "1 membri" in it.followup.send.await_args.args[0]
    assert a.server.id not in a.cog.operazioni


@pytest.mark.asyncio
async def test_massa_non_da_un_ruolo_con_permessi_forti(ambiente):
    a = ambiente
    forte = fake_role(20, "Mod", position=20, permissions=discord.Permissions(ban_members=True))
    it = _interazione(a)
    await a.cog.massa.callback(a.cog, it, AZIONE_DAI, forte, "tutti", None, None, None, None, None)
    assert "ban_members" in it.response.send_message.await_args.args[0]
    assert a.cog.operazioni == {}


@pytest.mark.asyncio
async def test_massa_ferma_alza_il_segnale(ambiente, monkeypatch):
    a = ambiente
    operazione = OperazioneMassa(AZIONE_DAI, 10, 3, 7)
    a.cog.operazioni[a.server.id] = operazione
    canale = MagicMock(send=AsyncMock())
    it = _interazione(a)
    await a.cog.massa_ferma.callback(a.cog, it)
    assert operazione.ferma is True
    monkeypatch.setattr(modulo.asyncio, "sleep", AsyncMock())
    membri = [fake_member(60), fake_member(61)]
    await a.cog._esegui_massa(a.server, a.ruoli[10], membri, operazione, canale, "m")
    assert all(not m.add_roles.await_count for m in membri)
    assert "fermata a mano" in canale.send.await_args.args[0]


@pytest.mark.asyncio
async def test_massa_si_ferma_dopo_troppi_errori(ambiente, monkeypatch):
    a = ambiente
    monkeypatch.setattr(modulo.asyncio, "sleep", AsyncMock())
    errore = discord.HTTPException(MagicMock(status=403, reason="no"), "Missing Permissions")
    membri = [fake_member(70 + i) for i in range(15)]
    for m in membri:
        m.add_roles.side_effect = errore
    operazione = OperazioneMassa(AZIONE_DAI, 10, 15, 7)
    canale = MagicMock(send=AsyncMock())
    await a.cog._esegui_massa(a.server, a.ruoli[10], membri, operazione, canale, "m")
    assert operazione.falliti == modulo.MAX_ERRORI_DI_FILA
    assert "interrotta" in canale.send.await_args.args[0]


@pytest.mark.asyncio
async def test_crea_rifiuta_oltre_250_ruoli(ambiente):
    a = ambiente
    a.server.roles = [object()] * 250
    it = _interazione(a)
    await a.cog.crea.callback(a.cog, it, "Nuovo", None, False, False)
    a.server.create_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_crea_con_colore(ambiente):
    a = ambiente
    a.server.create_role = AsyncMock(return_value=fake_role(30, "Nuovo"))
    it = _interazione(a)
    await a.cog.crea.callback(a.cog, it, "Nuovo", "#00ff00", True, True)
    kwargs = a.server.create_role.await_args.kwargs
    assert kwargs["colour"] == discord.Colour(0x00FF00) and kwargs["mentionable"] and kwargs["hoist"]


@pytest.mark.asyncio
async def test_modifica_nome_e_colore(ambiente):
    a = ambiente
    ruolo = a.ruoli[10]
    it = _interazione(a)
    await a.cog.modifica.callback(a.cog, it, ruolo, "Nuovo nome", "#112233", None, None)
    kwargs = ruolo.edit.await_args.kwargs
    assert kwargs["name"] == "Nuovo nome" and kwargs["colour"] == discord.Colour(0x112233)


@pytest.mark.asyncio
async def test_modifica_rifiuta_un_ruolo_sopra_il_bot(ambiente):
    a = ambiente
    ruolo = fake_role(60, "Sopra", position=60)
    it = _interazione(a)
    await a.cog.modifica.callback(a.cog, it, ruolo, "x", None, None, None)
    ruolo.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_diagnosi_senza_permesso(ambiente):
    a = ambiente
    a.server.me.guild_permissions = discord.Permissions.none()
    it = _interazione(a)
    await a.cog.diagnosi.callback(a.cog, it, a.ruoli[10])
    assert "Gestire i ruoli" in it.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_scelta_aggiungi_rifiuta_ruoli_con_permessi_forti(ambiente):
    a = ambiente
    forte = fake_role(20, "Mod", position=20, permissions=discord.Permissions(manage_guild=True))
    it = _interazione(a)
    await a.cog.scelta.callback(a.cog, it, "aggiungi", forte)
    a.repo.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_utility_ruolo_prende_e_lascia(ambiente):
    a = ambiente
    membro = fake_member(50, "tizio", roles=[a.ruoli[11]])
    membro.guild = a.server
    it = _interazione(a, user=membro)
    await a.cog.ruolo_a_scelta.callback(a.cog, it, "10")
    assert list(membro.add_roles.await_args.args) == [a.ruoli[10]]
    it2 = _interazione(a, user=membro)
    await a.cog.ruolo_a_scelta.callback(a.cog, it2, "11")
    assert list(membro.remove_roles.await_args.args) == [a.ruoli[11]]


@pytest.mark.asyncio
async def test_utility_ruolo_non_da_ruoli_fuori_elenco(ambiente):
    a = ambiente
    membro = fake_member(50, "tizio")
    membro.guild = a.server
    it = _interazione(a, user=membro)
    await a.cog.ruolo_a_scelta.callback(a.cog, it, "12")
    membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_utility_ruolo_senza_argomento_mostra_il_menu(ambiente):
    a = ambiente
    membro = fake_member(50, "tizio", roles=[a.ruoli[11]])
    membro.guild = a.server
    it = _interazione(a, user=membro)
    await a.cog.ruolo_a_scelta.callback(a.cog, it, None)
    vista = it.response.send_message.await_args.kwargs["view"]
    opzioni = {o.value: o.default for o in vista.menu.options}
    assert opzioni == {"10": False, "11": True}


@pytest.mark.asyncio
async def test_i_comandi_stanno_nei_gruppi():
    from discord.ext import commands as ext

    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("dai", "togli", "azzera", "massa", "massa-ferma", "crea", "modifica", "diagnosi", "scelta"):
        assert comando_nel_gruppo("ruoli", nome) is not None
    assert comando_nel_gruppo("utility", "ruolo") is not None

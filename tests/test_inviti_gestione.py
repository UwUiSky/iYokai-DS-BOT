"""
tests/test_inviti_gestione.py
=============================
D69 B13 (UTL-175, 176, 178, 179, 182, 183): segnaposto del benvenuto, riallinea, azzera, esporta, statistiche.
UTL-184 (/mod-ban massa invito) sta in cogs/moderation: non in questo blocco.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

import cogs.utility.invites as invites
import cogs.utility.inviti_codici as codici
import cogs.utility.inviti_gestione as modulo
from core import invite_service as svc
from core.greetings_logic import lunghezza_dopo_segnaposto, render_template, usa_segnaposto_inviti
from core.inviti_export_logic import MAX_BYTE_ALLEGATO, costruisci, neutralizza_cella
from core.repositories.invite_stats_repo import InviteStatsRepository
from core.repositories.inviti_extra_repo import InvitiExtraRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo

G = 900000000000000004


# ------------------------------------------------------------------ segnaposto
def test_segnaposto_inviti_si_sostituiscono_solo_se_c_e_il_dato():
    t = "Ciao {user}, invitato da {invitante} ({inviti_invitante}), rientri {rientri}, account {creato_il}"
    base = render_template(t, "@u", "u", "S", 3)
    assert "{invitante}" in base and "{rientri}" in base
    pieno = render_template(t, "@u", "u", "S", 3, invitante="<@5>", inviti_invitante=7, rientri=2, creato_il=1735689600)
    assert "<@5>" in pieno and "(7)" in pieno and "rientri 2" in pieno and "<t:1735689600:D>" in pieno


def test_usa_segnaposto_e_lunghezza_peggiore():
    assert usa_segnaposto_inviti("a {invitante}") and usa_segnaposto_inviti(None, "{rientri}")
    assert not usa_segnaposto_inviti("ciao {user}", None)
    # il segnaposto lungo conta nella misura del messaggio
    assert lunghezza_dopo_segnaposto("{invitante}", "S", 1) >= 23


# ------------------------------------------------------------------ esportazione
def test_celle_neutralizzate_e_formati():
    assert neutralizza_cella("=CMD()") == "'=CMD()" and neutralizza_cella(5) == "5" and neutralizza_cella(None) == ""
    dati, n = costruisci([{"a": 1, "b": "=x"}], ["a", "b"], "csv")
    assert dati.decode().splitlines() == ["a,b", "1,'=x"] and n == 1
    j, _ = costruisci([{"a": datetime(2026, 1, 1)}], ["a"], "json")
    assert json.loads(j) == [{"a": "2026-01-01T00:00:00"}]
    with pytest.raises(ValueError):
        costruisci([], ["a"], "xml")


def test_file_troppo_grande_si_taglia():
    righe = [{"a": "x" * 1000} for _ in range(20_000)]
    dati, n = costruisci(righe, ["a"], "csv")
    assert len(dati) <= MAX_BYTE_ALLEGATO and 0 < n < 20_000


# ------------------------------------------------------------------ archivio
@pytest.fixture
def stats(clean_db):
    return InviteStatsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_usciti_conteggio_per_codice_e_azzera(stats, clean_db):
    extra = InvitiExtraRepository(pool_provider=lambda: clean_db)
    await stats.record_join(G, 1, 5, "a")
    await stats.record_join(G, 2, 5, "a")
    await stats.record_join(G, 3, 6, "b")
    await stats.mark_left(G, 1)
    await stats.mark_left(G, 1)  # già uscito: non conta due volte
    await stats.record_join(G, 1, 5, "a")
    await stats.mark_left(G, 1)
    assert await stats.usciti_di(G, 1) == 2 and await stats.usciti_di(G, 99) == 0
    assert await stats.conteggio_per_codice(G) == {"a": 2, "b": 1}
    await extra.aggiungi_bonus(G, 5, 3, 1)
    await extra.aggiungi_bonus(G + 1, 5, 3, 1)
    assert await stats.azzera(G) == (3, 1)
    assert await stats.conteggio_per_codice(G) == {}
    assert await stats.top(G + 1) != []  # l'altro server resta


@pytest.mark.asyncio
async def test_statistiche_presenti_e_attivi_dopo_sette_giorni(stats, clean_db):
    await stats.record_join(G, 1, 5, "a")
    await stats.record_join(G, 2, 5, "a")
    await stats.record_join(G, 3, 5, "a", finto=True)
    await stats.record_join(G, 4, 5, "a")
    await stats.mark_left(G, 4)
    await clean_db.execute("UPDATE invite_joins SET joined_at = now() - interval '10 days' WHERE guild_id = $1", G)
    oggi = datetime.now(timezone.utc).date()
    await clean_db.execute(
        "INSERT INTO activity_member_daily (guild_id, day, user_id, messages) VALUES ($1, $2, 1, 3), ($1, $3, 2, 5)",
        G, oggi, oggi - timedelta(days=9),  # utente 2: attivo solo prima dei sette giorni
    )
    s = await stats.statistiche_server(G, 7)
    assert s == {"ingressi": 3, "presenti": 2, "attivi": 1}


# ------------------------------------------------------------------ servizio
@pytest.mark.asyncio
async def test_dati_per_benvenuto(monkeypatch):
    guild = fake_guild(G)
    membro = fake_member(user_id=9)
    membro.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    stats = MagicMock()
    stats.stats_for = AsyncMock(return_value=SimpleNamespace(punti=4))
    stats.ingresso_di = AsyncMock(return_value=None)
    stats.usciti_di = AsyncMock(return_value=2)
    monkeypatch.setattr(svc, "invite_stats_repo", stats)
    monkeypatch.setattr(svc.invite_links_repo, "da_codice", AsyncMock(return_value=None))
    with patch.object(svc.invite_tracker, "resolve_join_invite", AsyncMock(return_value=("abc", 5))):
        d = await svc.dati_per_benvenuto(guild, membro)
    assert d == {"invitante": "<@5>", "inviti_invitante": 5, "rientri": 2, "creato_il": int(membro.created_at.timestamp())}
    stats.ingresso_di = AsyncMock(return_value=SimpleNamespace(left_at=None, inviter_id=5))  # già contato
    with patch.object(svc.invite_tracker, "resolve_join_invite", AsyncMock(return_value=("abc", 5))):
        assert (await svc.dati_per_benvenuto(guild, membro))["inviti_invitante"] == 4
    with patch.object(svc.invite_tracker, "resolve_join_invite", AsyncMock(return_value=None)):
        assert (await svc.dati_per_benvenuto(guild, membro))["invitante"] == "?"
    with patch.object(svc.invite_tracker, "resolve_join_invite", AsyncMock(side_effect=RuntimeError("x"))):
        assert (await svc.dati_per_benvenuto(guild, membro))["invitante"] == "?"


@pytest.mark.asyncio
async def test_il_benvenuto_cerca_i_dati_solo_se_servono():
    import cogs.utility.greetings as g

    membro = fake_member(user_id=9)
    membro.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    membro.guild = fake_guild(G)
    membro.guild.member_count = 3
    assert "<@5>" in g._render_for_member("da {invitante}", membro, {"invitante": "<@5>"})
    assert g._render_for_member("da {invitante}", membro).count("{invitante}") == 1


# ------------------------------------------------------------------ comandi
class _Scena:
    def __init__(self, monkeypatch):
        self.cog = modulo.InvitiGestioneCog(MagicMock())
        self.guild = fake_guild()
        db = MagicMock()
        db.is_module_active_for_guild = AsyncMock(return_value=True)
        monkeypatch.setattr(modulo, "db", db)
        self.stats = MagicMock()
        monkeypatch.setattr(modulo, "invite_stats_repo", self.stats)
        self.i = fake_interaction(guild=self.guild)


@pytest.mark.asyncio
async def test_riallinea_rilegge_e_segnala_gli_ingressi_mancanti(monkeypatch):
    s = _Scena(monkeypatch)
    s.guild.invites = AsyncMock(return_value=[
        SimpleNamespace(code="a", uses=5), SimpleNamespace(code="b", uses=1), SimpleNamespace(code="c", uses=0)])
    s.stats.conteggio_per_codice = AsyncMock(return_value={"a": 2, "b": 1})
    with patch.object(modulo.invite_tracker, "refresh_guild", AsyncMock()) as rif:
        await s.cog.riallinea.callback(s.cog, s.i)
    rif.assert_awaited_once()
    testo = s.i.followup.send.await_args.args[0]
    assert "3" in testo and "`a`: 3" in testo and "`b`" not in testo


@pytest.mark.asyncio
async def test_azzera_chiede_conferma_e_solo_chi_l_ha_chiesta_la_da(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    s = _Scena(monkeypatch)
    await s.cog.azzera.callback(s.cog, s.i)
    vista = s.i.response.send_message.await_args.kwargs["view"]
    s.stats.azzera = AsyncMock()
    s.stats.azzera.assert_not_awaited()
    assert await vista.interaction_check(fake_interaction(user=fake_member(user_id=999))) is False
    s.stats.azzera = AsyncMock(return_value=(7, 2))
    click = fake_interaction(guild=s.guild, user=s.i.user)
    await vista.conferma.callback(click)
    s.stats.azzera.assert_awaited_once_with(s.guild.id)
    assert "7" in click.response.edit_message.await_args.kwargs["content"]


@pytest.mark.asyncio
async def test_esporta_ingressi_in_csv_e_classifica_in_json(monkeypatch):
    s = _Scena(monkeypatch)
    s.stats.righe_per_esportare = AsyncMock(return_value=[
        {"user_id": 1, "inviter_id": 5, "code": "=evil", "kind": "normale", "finto": False, "usciti": 0,
         "joined_at": datetime(2026, 1, 1), "left_at": None}])
    scelta = SimpleNamespace(value="ingressi")
    await s.cog.esporta.callback(s.cog, s.i, scelta, None)
    file = s.i.followup.send.await_args.kwargs["file"]
    assert file.filename == "inviti-ingressi.csv"
    assert "'=evil" in file.fp.read().decode()
    s.stats.top = AsyncMock(return_value=[(5, SimpleNamespace(presenti=2, totale=3, finti=0, bonus=1, punti=3))])
    i2 = fake_interaction(guild=s.guild)
    await s.cog.esporta.callback(s.cog, i2, SimpleNamespace(value="classifica"), SimpleNamespace(value="json"))
    dati = json.loads(i2.followup.send.await_args.kwargs["file"].fp.read())
    assert dati[0]["user_id"] == 5 and dati[0]["punti"] == 3


@pytest.mark.asyncio
async def test_esporta_vuoto_e_codici_senza_permesso(monkeypatch):
    s = _Scena(monkeypatch)
    s.stats.righe_per_esportare = AsyncMock(return_value=[])
    await s.cog.esporta.callback(s.cog, s.i, SimpleNamespace(value="ingressi"), None)
    assert "file" not in s.i.followup.send.await_args.kwargs
    s.guild.invites = AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no"))
    i2 = fake_interaction(guild=s.guild)
    await s.cog.esporta.callback(s.cog, i2, SimpleNamespace(value="codici"), None)
    assert "file" not in i2.followup.send.await_args.kwargs


@pytest.mark.asyncio
async def test_statistiche(monkeypatch):
    s = _Scena(monkeypatch)
    s.stats.statistiche_server = AsyncMock(return_value={"ingressi": 10, "presenti": 8, "attivi": 3})
    await s.cog.statistiche.callback(s.cog, s.i)
    testo = s.i.response.send_message.await_args.args[0]
    assert "10" in testo and "8" in testo and "3" in testo and "7" in testo


@pytest.mark.asyncio
async def test_albero_dei_comandi_gestione():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await invites.setup(bot)
    await codici.setup(bot)
    await modulo.setup(bot)
    for nome in ("riallinea", "azzera", "esporta", "statistiche"):
        assert comando_nel_gruppo("admin-inviti", nome)

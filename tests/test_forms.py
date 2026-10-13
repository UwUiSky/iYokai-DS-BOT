"""
tests/test_forms.py
===================
NF-34 (#105): moduli e candidature. Fino a 5 domande, etichette da 45, risposte da 1024,
una candidatura in attesa per persona, decisione una sola volta, ruolo all'accettazione.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

import cogs.utility.forms as modulo
from cogs.utility.forms import FormsCog, embed_risposta
from core.form_logic import Domanda, campi_riepilogo, leggi_domande
from core.repositories.form_repo import FormRepository, FormResponse
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel
from tests.support.percorsi import comando_nel_gruppo

G = 900000000000000001


# ---------------------------------------------------------------- logica
def test_leggi_domande_ok_e_lunga():
    d, err = leggi_domande("Nome | +Perché vuoi entrare?")
    assert err is None and d == [Domanda("Nome"), Domanda("Perché vuoi entrare?", True)]


@pytest.mark.parametrize("testo", ["", " | ", "a|b|c|d|e|f", "x" * 46, "+"])
def test_leggi_domande_rifiuta(testo):
    d, err = leggi_domande(testo)
    assert err and d == []


def test_riepilogo_non_ha_valori_vuoti_ne_oltre_1024():
    campi = campi_riepilogo([Domanda("a"), Domanda("b")], ["x" * 2000, "  "])
    assert len(campi[0][1]) == 1024 and campi[1][1] == "—"


def test_embed_resta_sotto_6000_con_5_risposte_piene():
    from core.repositories.form_repo import Form
    domande = [Domanda("d" * 45, True)] * 5
    form = Form(1, G, "n", "t" * 45, 1, None, domande)
    r = FormResponse(1, 1, G, 7, ["r" * 1024] * 5, "accepted", None, 8)
    assert len(embed_risposta(form, r)) <= 6000


# ---------------------------------------------------------------- repository
@pytest.fixture
def repo(clean_db):
    return FormRepository(pool_provider=lambda: clean_db)


async def _modulo(repo, nome="staff"):
    assert await repo.create_form(G, nome, "Candidatura", 50, 60, [Domanda("Nome")], 1) == "ok"
    return await repo.get_form(G, nome)


@pytest.mark.asyncio
async def test_crea_duplicato_e_tetto(repo):
    await _modulo(repo)
    assert await repo.create_form(G, "STAFF", "x", 50, None, [Domanda("a")], 1) == "esiste"
    for i in range(9):
        assert await repo.create_form(G, f"m{i}", "x", 50, None, [Domanda("a")], 1) == "ok"
    assert await repo.create_form(G, "extra", "x", 50, None, [Domanda("a")], 1) == "pieno"
    assert len(await repo.list_forms(G)) == 10


@pytest.mark.asyncio
async def test_una_sola_candidatura_in_attesa(repo):
    f = await _modulo(repo)
    assert await repo.add_response(f, 7, ["a"]) is not None
    assert await repo.add_response(f, 7, ["b"]) is None
    assert await repo.add_response(f, 8, ["c"]) is not None


@pytest.mark.asyncio
async def test_decisione_una_sola_volta_poi_si_puo_ricandidare(repo):
    f = await _modulo(repo)
    rid = await repo.add_response(f, 7, ["a"])
    assert await repo.decide(rid, "rejected", 1) is True
    assert await repo.decide(rid, "accepted", 2) is False
    assert (await repo.get_response(rid)).status == "rejected"
    assert await repo.add_response(f, 7, ["b"]) is not None


@pytest.mark.asyncio
async def test_elimina_modulo_toglie_le_risposte(repo):
    f = await _modulo(repo)
    rid = await repo.add_response(f, 7, ["a"])
    assert await repo.delete_form(G, "staff") is True
    assert await repo.get_response(rid) is None


@pytest.mark.asyncio
async def test_in_attesa_per_riavvio(repo):
    f = await _modulo(repo)
    rid = await repo.add_response(f, 7, ["a"])
    assert await repo.list_pending() == []
    await repo.set_review_message(rid, 999)
    assert [r.id for r in await repo.list_pending()] == [rid]


# ---------------------------------------------------------------- cog
def _cog():
    return FormsCog(MagicMock())


def _form(**kw):
    from core.repositories.form_repo import Form
    base = dict(id=1, guild_id=G, name="staff", title="Candidatura", review_channel_id=50,
                accept_role_id=60, domande=[Domanda("Nome")])
    base.update(kw)
    return Form(**base)


def _risposta(stato="pending"):
    return FormResponse(5, 1, G, 7, ["Mario"], stato, 99, None)


@pytest.mark.asyncio
async def test_invio_consegna_allo_staff_e_registra_il_bottone():
    cog = _cog()
    guild = fake_guild(guild_id=G)
    canale = fake_text_channel(50)
    canale.send = AsyncMock(return_value=MagicMock(id=999))
    guild.get_channel = lambda cid: canale
    i = fake_interaction(guild=guild)
    with patch.object(modulo.form_repo, "add_response", AsyncMock(return_value=5)), \
         patch.object(modulo.form_repo, "get_response", AsyncMock(return_value=_risposta())), \
         patch.object(modulo.form_repo, "set_review_message", AsyncMock()) as setm:
        await cog.invia_candidatura(i, _form(), ["Mario"])
    canale.send.assert_awaited_once()
    setm.assert_awaited_once_with(5, 999)
    cog.bot.add_view.assert_called_once()


@pytest.mark.asyncio
async def test_invio_fallito_non_lascia_righe_orfane():
    cog = _cog()
    guild = fake_guild(guild_id=G)
    canale = fake_text_channel(50)
    canale.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no"))
    guild.get_channel = lambda cid: canale
    with patch.object(modulo.form_repo, "add_response", AsyncMock(return_value=5)), \
         patch.object(modulo.form_repo, "get_response", AsyncMock(return_value=_risposta())), \
         patch.object(modulo.form_repo, "delete_response", AsyncMock()) as canc:
        await cog.invia_candidatura(fake_interaction(guild=guild), _form(), ["Mario"])
    canc.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_seconda_candidatura_in_attesa_rifiutata():
    cog = _cog()
    guild = fake_guild(guild_id=G)
    guild.get_channel = lambda cid: fake_text_channel(50)
    i = fake_interaction(guild=guild)
    with patch.object(modulo.form_repo, "add_response", AsyncMock(return_value=None)):
        await cog.invia_candidatura(i, _form(), ["x"])
    assert "già una candidatura" in i.followup.send.call_args.args[0]


@pytest.mark.asyncio
async def test_decisione_solo_staff():
    cog = _cog()
    i = fake_interaction(guild=fake_guild(guild_id=G))
    i.user = fake_member(user_id=3, guild_permissions=discord.Permissions.none())
    with patch.object(modulo.form_repo, "decide", AsyncMock()) as dec:
        await cog.decidi(i, 5, "accepted")
    dec.assert_not_awaited()


def _staff_interaction(guild):
    i = fake_interaction(guild=guild)
    i.user = fake_member(user_id=3, guild_permissions=discord.Permissions(manage_guild=True))
    i.message = MagicMock(edit=AsyncMock())
    return i


@pytest.mark.asyncio
async def test_accettazione_da_il_ruolo_e_avvisa():
    cog = _cog()
    guild = fake_guild(guild_id=G)
    candidato = fake_member(user_id=7)
    candidato.add_roles, candidato.send = AsyncMock(), AsyncMock()
    ruolo = fake_role(60, "Staff", position=1)
    guild.get_member = lambda uid: candidato
    guild.get_role = lambda rid: ruolo
    i = _staff_interaction(guild)
    with patch.object(modulo.form_repo, "get_response", AsyncMock(return_value=_risposta())), \
         patch.object(modulo.form_repo, "get_form_by_id", AsyncMock(return_value=_form())), \
         patch.object(modulo.form_repo, "decide", AsyncMock(return_value=True)), \
         patch.object(modulo, "motivo_ruolo_automatico_non_assegnabile", return_value=None):
        await cog.decidi(i, 5, "accepted")
    candidato.add_roles.assert_awaited_once()
    candidato.send.assert_awaited_once()
    i.message.edit.assert_awaited_once()


@pytest.mark.asyncio
async def test_rifiuto_non_da_ruoli():
    cog = _cog()
    guild = fake_guild(guild_id=G)
    candidato = fake_member(user_id=7)
    candidato.add_roles, candidato.send = AsyncMock(), AsyncMock()
    guild.get_member = lambda uid: candidato
    i = _staff_interaction(guild)
    with patch.object(modulo.form_repo, "get_response", AsyncMock(return_value=_risposta())), \
         patch.object(modulo.form_repo, "get_form_by_id", AsyncMock(return_value=_form())), \
         patch.object(modulo.form_repo, "decide", AsyncMock(return_value=True)):
        await cog.decidi(i, 5, "rejected")
    candidato.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_doppio_clic_decide_una_volta():
    cog = _cog()
    guild = fake_guild(guild_id=G)
    i = _staff_interaction(guild)
    with patch.object(modulo.form_repo, "get_response", AsyncMock(return_value=_risposta())), \
         patch.object(modulo.form_repo, "get_form_by_id", AsyncMock(return_value=_form())), \
         patch.object(modulo.form_repo, "decide", AsyncMock(return_value=False)):
        await cog.decidi(i, 5, "accepted")
    assert "già stata decisa" in i.response.send_message.call_args.args[0]
    i.message.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_albero_dei_comandi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    with patch.object(modulo.form_repo, "list_pending", AsyncMock(return_value=[])):
        await modulo.setup(bot)
    for nome in ("crea", "elimina", "elenco"):
        assert comando_nel_gruppo("admin", f"moduli {nome}") is not None
    assert comando_nel_gruppo("utility", "modulo") is not None

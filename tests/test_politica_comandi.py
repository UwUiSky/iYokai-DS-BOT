"""
tests/test_politica_comandi.py
==============================
CFG-008, CFG-009, CFG-010, CFG-018 (#122): politica dei comandi di un server (`core/command_policy.py`,
`/utility politica`, controllo in `BlacklistAwareCommandTree`).
"""

from unittest.mock import AsyncMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from core import command_policy as pol
from core.blacklist_tree import BlacklistAwareCommandTree
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

pytestmark = pytest.mark.asyncio


def _valuta(politica, **kw):
    base = dict(percorso="fun meme", canali=[10], ruoli=[], user_id=1, esente=False)
    base.update(kw)
    return pol.valuta(politica, **base)


def test_politica_vuota_lascia_passare_tutto():
    assert pol.Politica().vuota
    assert _valuta(pol.Politica()) is None


def test_comando_spento_vale_per_tutti_ma_non_per_i_gruppi_di_servizio():
    p = pol.Politica(comandi_off=frozenset({"fun meme", "admin setup attiva"}))
    assert _valuta(p) == pol.MOTIVO_COMANDO_OFF
    assert _valuta(p, esente=True) == pol.MOTIVO_COMANDO_OFF  # spento è spento, anche per lo staff
    assert _valuta(p, percorso="admin setup attiva") is None  # /admin non si spegne mai
    assert _valuta(p, percorso="fun dado") is None


def test_canali_permessi_e_vietati_e_categoria():
    solo = pol.Politica(canali_ok=frozenset({10}))
    assert _valuta(solo, canali=[10]) is None
    assert _valuta(solo, canali=[11]) == pol.MOTIVO_CANALE_NON_PERMESSO
    assert _valuta(solo, canali=[11, 99, 10]) is None  # thread dentro il canale permesso (o sua categoria)
    mai = pol.Politica(canali_no=frozenset({99}))
    assert _valuta(mai, canali=[11, 99]) == pol.MOTIVO_CANALE_VIETATO  # categoria vietata
    assert _valuta(mai, canali=[11]) is None


def test_ruoli_e_utenti_ignorati_ma_lo_staff_no():
    p = pol.Politica(ruoli_ignorati=frozenset({5}), utenti_ignorati=frozenset({7}))
    assert _valuta(p, ruoli=[5]) == pol.MOTIVO_UTENTE_IGNORATO
    assert _valuta(p, user_id=7) == pol.MOTIVO_UTENTE_IGNORATO
    assert _valuta(p, ruoli=[5], esente=True) is None
    assert _valuta(p, ruoli=[6], user_id=8) is None


def test_i_gruppi_di_servizio_non_si_bloccano_con_nessuna_regola():
    p = pol.Politica(canali_ok=frozenset({1}), utenti_ignorati=frozenset({7}))
    for percorso in ("admin config history", "owner system eval", "utility politica elenco"):
        assert _valuta(p, percorso=percorso, user_id=7, canali=[2]) is None


@pytest.fixture
async def db_pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await database_module.db.ensure_guild_exists(700)
    return database_module.db


async def test_modifica_elenco_aggiunge_toglie_e_rispetta_il_tetto(db_pronto):
    db = db_pronto
    assert await pol.modifica_elenco(700, pol.CHIAVE_COMANDI_OFF, "fun meme", aggiungi=True, changed_by=1)
    assert not await pol.modifica_elenco(700, pol.CHIAVE_COMANDI_OFF, "fun meme", aggiungi=True, changed_by=1)
    assert (await pol.leggi_politica(700)).comandi_off == {"fun meme"}
    assert await pol.modifica_elenco(700, pol.CHIAVE_COMANDI_OFF, "fun meme", aggiungi=False, changed_by=1)
    assert await db.get_guild_setting(700, pol.CHIAVE_COMANDI_OFF, None) is None  # l'elenco vuoto toglie la chiave
    with pytest.raises(pol.VoceNonValida):
        await pol.modifica_elenco(700, pol.CHIAVE_COMANDI_OFF, "admin setup", aggiungi=True, changed_by=1)
    with pytest.raises(pol.VoceNonValida):
        await pol.modifica_elenco(700, pol.CHIAVE_CANALI_OK, -4, aggiungi=True, changed_by=1)
    with pytest.raises(KeyError):
        await pol.modifica_elenco(700, "welcome_channel_id", 5, aggiungi=True, changed_by=1)
    for n in range(1, pol.MAX_VOCI + 1):
        await pol.modifica_elenco(700, pol.CHIAVE_CANALI_NO, n, aggiungi=True, changed_by=1)
    with pytest.raises(pol.ElencoPieno):
        await pol.modifica_elenco(700, pol.CHIAVE_CANALI_NO, 9999, aggiungi=True, changed_by=1)
    assert await pol.azzera_elenco(700, pol.CHIAVE_CANALI_NO, changed_by=1)
    assert not await pol.azzera_elenco(700, pol.CHIAVE_CANALI_NO, changed_by=1)


def _interazione(comando="fun meme", *, permessi=None, canale_id=10, user_id=40, ruoli=None):
    canale = fake_text_channel(canale_id)
    canale.parent_id = None
    canale.category_id = None
    guild = fake_guild(700)
    guild.owner_id = 999
    utente = fake_member(user_id, roles=ruoli or [], guild_permissions=permessi)
    i = fake_interaction(guild=guild, user=utente, channel=canale)
    i.type = discord.InteractionType.application_command
    i.channel_id = canale_id
    i.command = type("C", (), {"qualified_name": comando})()
    i.locale = discord.Locale.italian
    return i


async def test_il_controllo_dell_albero_ferma_il_comando_spento_e_risponde_effimero(db_pronto, monkeypatch):
    monkeypatch.setattr("core.blacklist_tree.blacklist_repo.is_user_blacklisted", AsyncMock(return_value=False), raising=False)
    await pol.modifica_elenco(700, pol.CHIAVE_COMANDI_OFF, "fun meme", aggiungi=True, changed_by=1)
    interazione = _interazione()
    assert await pol.valuta_interazione(interazione) == pol.MOTIVO_COMANDO_OFF
    # chi gestisce il server resta fuori dalle regole sui canali
    await pol.modifica_elenco(700, pol.CHIAVE_CANALI_OK, 77, aggiungi=True, changed_by=1)
    altro = _interazione("fun dado", canale_id=10)
    assert await pol.valuta_interazione(altro) == pol.MOTIVO_CANALE_NON_PERMESSO
    staff = _interazione("fun dado", canale_id=10, permessi=discord.Permissions(manage_guild=True))
    assert await pol.valuta_interazione(staff) is None


async def test_una_politica_rotta_non_blocca_il_bot(monkeypatch):
    async def rotta(_):
        raise RuntimeError("database giù")

    monkeypatch.setattr(pol, "leggi_politica", rotta)
    assert await pol.valuta_interazione(_interazione()) is None


async def test_i_comandi_fuori_dai_server_o_non_slash_non_sono_toccati(db_pronto):
    dm = _interazione()
    dm.guild = None
    assert await pol.valuta_interazione(dm) is None
    componente = _interazione()
    componente.type = discord.InteractionType.component
    assert await pol.valuta_interazione(componente) is None


async def test_albero_blacklist_manda_il_motivo_in_privato(db_pronto, monkeypatch):
    await pol.modifica_elenco(700, pol.CHIAVE_COMANDI_OFF, "fun meme", aggiungi=True, changed_by=1)
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), tree_cls=BlacklistAwareCommandTree)
    interazione = _interazione()
    interazione.client = bot
    assert await bot.tree.interaction_check(interazione) is False
    args, kwargs = interazione.response.send_message.call_args
    assert "spento" in args[0] and kwargs["ephemeral"] is True


# ----------------------------------------------------------------------
# Il cog
# ----------------------------------------------------------------------
@pytest.fixture
async def cog(db_pronto):
    from cogs.utility.politica import PoliticaCog

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    gruppo = app_commands.Group(name="fun", description="giochi")

    @gruppo.command(name="meme", description="un meme")
    async def meme(interaction):  # pragma: no cover
        ...

    bot.tree.add_command(gruppo)
    return PoliticaCog(bot)


async def test_comando_spegne_riaccende_e_rifiuta_i_nomi_sbagliati(cog, db_pronto):
    i = _interazione()
    await cog.comando.callback(cog, i, "/fun meme", False)
    assert (await pol.leggi_politica(700)).comandi_off == {"fun meme"}
    assert "spento" in i.response.send_message.call_args.args[0]

    i = _interazione()
    await cog.comando.callback(cog, i, "fun meme", True)
    assert (await pol.leggi_politica(700)).vuota

    i = _interazione()
    await cog.comando.callback(cog, i, "fun non-esiste", False)
    assert "Non esiste" in i.response.send_message.call_args.args[0]
    assert (await pol.leggi_politica(700)).vuota

    i = _interazione()
    await cog.comando.callback(cog, i, "admin setup", False)
    assert "non si spengono" in i.response.send_message.call_args.args[0]


async def test_canali_ignora_ed_elenco(cog, db_pronto):
    canale = fake_text_channel(55)
    i = _interazione()
    await cog.canali.callback(cog, i, app_commands.Choice(name="solo in questo", value="solo_canali"), canale, False)
    ruolo = fake_role(role_id=66)
    i = _interazione()
    await cog.ignora.callback(cog, i, ruolo, None, False)
    i = _interazione()
    await cog.ignora.callback(cog, i, None, None, False)  # né ruolo né utente
    assert "Scegli" in i.response.send_message.call_args.args[0]
    politica = await pol.leggi_politica(700)
    assert politica.canali_ok == {55} and politica.ruoli_ignorati == {66}

    i = _interazione()
    await cog.elenco.callback(cog, i, None)
    embed = i.response.send_message.call_args.kwargs["embed"]
    assert "<#55>" in embed.description and "<@&66>" in embed.description

    i = _interazione()
    await cog.elenco.callback(cog, i, app_commands.Choice(name="x", value="ruoli"))
    assert (await pol.leggi_politica(700)).ruoli_ignorati == frozenset()


async def test_diagnosi_dice_il_motivo(cog, db_pronto):
    await pol.modifica_elenco(700, pol.CHIAVE_COMANDI_OFF, "fun meme", aggiungi=True, changed_by=1)
    i = _interazione(permessi=discord.Permissions(manage_guild=True))
    await cog.diagnosi.callback(cog, i, "fun meme")
    assert "spento" in i.followup.send.call_args.kwargs["embed"].description
    await pol.modifica_elenco(700, pol.CHIAVE_COMANDI_OFF, "fun meme", aggiungi=False, changed_by=1)
    i = _interazione(permessi=discord.Permissions(manage_guild=True))
    await cog.diagnosi.callback(cog, i, "fun meme")
    assert "Nessun problema" in i.followup.send.call_args.kwargs["embed"].description


async def test_modifica_elenco_insieme_non_perde_voci(db_pronto):
    """Venti aggiunte in parallelo: tutte devono restare nell'elenco."""
    import asyncio

    await asyncio.gather(
        *(pol.modifica_elenco(700, pol.CHIAVE_CANALI_NO, 1000 + n, aggiungi=True, changed_by=1) for n in range(20))
    )
    assert len((await pol.leggi_politica(700)).canali_no) == 20

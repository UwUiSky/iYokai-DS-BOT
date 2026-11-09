"""
tests/test_leveling_azzera_cog.py
=================================
#124 B1 (LIV-068..071, 075): i comandi `/admin-livelli azzera server|ripristina|auto`, `/admin-livelli
diagnosi`, il blocco al proprietario su `/admin-livelli membro`, l'azzeramento di chi esce o viene
bannato. Archivio su PostgreSQL vero, oggetti Discord finti.
Funzioni coperte: SPEC §15 (catalogo #124)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.leveling.azzeramenti as modulo
from cogs.leveling.azzeramenti import AzzeramentiCog, ConfermaRipristinoView, ModaleAzzeraServer
from cogs.leveling.leveling import LevelingCog
from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.leveling_copie_repo import leveling_copie_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel
from tests.support.moduli import attiva_livelli

GUILD = 100
OWNER = 555
STAFF = 7
GESTORE = discord.Permissions(manage_guild=True)


@pytest.fixture
async def cog(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    import core.repositories.blacklist_repo as bl

    for repo in (leveling_repo, leveling_copie_repo, leveling_settings_repo):
        monkeypatch.setattr(repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(blacklist_repo, "_pool_provider", lambda: clean_db, raising=False)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=10)
    c = AzzeramentiCog(bot=None)
    yield c
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=10)


def _comando(cog, nome):
    return next(c for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None) if c.qualified_name == nome)


def _inter(utente=STAFF, permessi=GESTORE, canale=None, nome="Casa Yokai"):
    return fake_interaction(
        guild=fake_guild(GUILD, nome, owner_id=OWNER), user=fake_member(utente),
        permissions=permessi, channel=canale,
    )


async def _xp(utente, punti):
    await leveling_repo.modifica_xp(GUILD, utente, "aggiungi", punti)


def _modale(nome, motivo=""):
    m = ModaleAzzeraServer("t", "n", "m")
    m.nome._value = nome
    m.motivo._value = motivo
    return m


def _testo(chiamata):
    return (chiamata.args[0] if chiamata.args else chiamata.kwargs.get("content", ""))


# ---------------------------------------------------------------- modulo spento e permessi
@pytest.mark.asyncio
@pytest.mark.parametrize("nome", ["admin-livelli azzera server", "admin-livelli azzera ripristina",
                                  "admin-livelli azzera auto", "admin-livelli diagnosi"])
async def test_modulo_spento_comando_rifiutato(monkeypatch, clean_db, nome):
    await attiva_livelli(monkeypatch, clean_db)  # nessun server attivo
    cog = AzzeramentiCog(bot=None)
    comando = _comando(cog, nome)
    inter = _inter()
    await comando.callback(cog, inter, **{p.name: None for p in comando.parameters})
    inter.response.send_message.assert_awaited_once()
    assert "non è attivo" in inter.response.send_message.await_args.args[0]
    inter.response.defer.assert_not_awaited()
    inter.response.send_modal.assert_not_awaited()


@pytest.mark.asyncio
async def test_senza_gestisci_server_non_si_apre_la_finestra(cog):
    inter = _inter(permessi=discord.Permissions.none())
    await _comando(cog, "admin-livelli azzera server").callback(cog, inter)
    inter.response.send_modal.assert_not_awaited()
    assert "Gestisci server" in _testo(inter.response.send_message.await_args)


# ---------------------------------------------------------------- LIV-068
@pytest.mark.asyncio
async def test_la_finestra_si_apre_e_chiede_il_nome(cog):
    inter = _inter()
    await _comando(cog, "admin-livelli azzera server").callback(cog, inter)
    modale = inter.response.send_modal.await_args.args[0]
    assert modale.nome.max_length == 100 and modale.nome.required
    assert modale.motivo.max_length == 512 and not modale.motivo.required
    assert len(modale.title) <= 45 and len(modale.nome.label) <= 45


@pytest.mark.asyncio
async def test_nome_sbagliato_non_azzera(cog):
    await _xp(1, 300)
    inter = _inter()
    await _modale("Altro Nome").on_submit(inter)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300
    assert await leveling_copie_repo.elenco(GUILD) == []
    assert "Non ho azzerato" in _testo(inter.response.send_message.await_args)


@pytest.mark.asyncio
async def test_nome_giusto_azzera_e_fa_la_copia(cog):
    await _xp(1, 300)
    await _xp(2, 50)
    inter = _inter()
    await _modale("casa yokai", "stagione 2").on_submit(inter)
    inter.response.defer.assert_awaited_once()
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 0
    [copia] = await leveling_copie_repo.elenco(GUILD)
    assert (copia.righe, copia.autore_id, copia.motivo) == (2, STAFF, "stagione 2")
    testo = _testo(inter.followup.send.await_args)
    assert "**2** persone" in testo and f"**{copia.id}**" in testo


@pytest.mark.asyncio
async def test_due_invii_insieme_azzerano_una_volta(cog):
    await _xp(1, 300)
    modale = _modale("Casa Yokai")
    a, b = _inter(), _inter()
    await asyncio.gather(modale.on_submit(a), modale.on_submit(b))
    assert len(await leveling_copie_repo.elenco(GUILD)) == 1
    assert a.response.defer.await_count + b.response.defer.await_count == 1


@pytest.mark.asyncio
async def test_il_permesso_si_ricontrolla_all_invio(cog):
    await _xp(1, 300)
    inter = _inter(permessi=discord.Permissions.none())
    await _modale("Casa Yokai").on_submit(inter)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300


# ---------------------------------------------------------------- LIV-071
@pytest.mark.asyncio
async def test_blocco_azzeramento_solo_il_proprietario(cog):
    await leveling_settings_repo.set_options(GUILD, blocca_azzeramento=True)
    await _xp(1, 300)
    inter = _inter()
    await _comando(cog, "admin-livelli azzera server").callback(cog, inter)
    inter.response.send_modal.assert_not_awaited()
    assert "proprietario" in _testo(inter.response.send_message.await_args)
    # anche con la finestra già aperta prima del blocco
    inter = _inter()
    await _modale("Casa Yokai").on_submit(inter)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300
    inter = _inter(utente=OWNER)
    await _comando(cog, "admin-livelli azzera server").callback(cog, inter)
    inter.response.send_modal.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocco_xp_ferma_il_comando_membro_per_lo_staff(monkeypatch, cog):
    leveling = LevelingCog(bot=None)
    leveling.cog_unload()
    membro = fake_member(1)
    await leveling_settings_repo.set_options(GUILD, blocca_xp=True)
    comando = _comando(leveling, "admin-livelli membro")
    azione = MagicMock(value="aggiungi")
    inter = _inter()
    await comando.callback(leveling, inter, azione, membro, 50)
    assert "proprietario" in _testo(inter.response.send_message.await_args)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 0
    inter = _inter(utente=OWNER)
    await comando.callback(leveling, inter, azione, membro, 50)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 50


@pytest.mark.asyncio
async def test_auto_salva_e_con_un_blocco_acceso_gli_interruttori_li_cambia_il_proprietario(cog):
    comando = _comando(cog, "admin-livelli azzera auto")
    scelta = MagicMock(value="entrambi")
    inter = _inter()
    await comando.callback(cog, inter, scelta, True, True, None)
    i = (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni
    assert (i.azzera_su, i.copia_su_uscita, i.blocca_xp, i.blocca_azzeramento) == ("entrambi", True, True, False)
    # blocca_xp acceso: lo staff non può spegnerlo né accendere altri blocchi
    inter = _inter()
    await comando.callback(cog, inter, None, None, False, None)
    assert "proprietario" in _testo(inter.response.send_message.await_args)
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.blocca_xp is True
    # ma può cambiare le altre opzioni
    inter = _inter()
    await comando.callback(cog, inter, MagicMock(value="ban"), None, None, None)
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.azzera_su == "ban"
    inter = _inter(utente=OWNER)
    await comando.callback(cog, inter, None, None, False, None)
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.blocca_xp is False


@pytest.mark.asyncio
async def test_auto_senza_valori_non_salva(cog):
    inter = _inter()
    await _comando(cog, "admin-livelli azzera auto").callback(cog, inter, None, None, None, None)
    assert "almeno un valore" in _testo(inter.response.send_message.await_args)


# ---------------------------------------------------------------- LIV-069
@pytest.mark.asyncio
async def test_ripristina_chiede_conferma_poi_rimette_gli_xp(cog):
    await _xp(1, 300)
    esito = await leveling_copie_repo.azzera_server(GUILD, STAFF, "")
    comando = _comando(cog, "admin-livelli azzera ripristina")
    inter = _inter()
    await comando.callback(cog, inter, str(esito.copia_id))
    vista = inter.response.send_message.await_args.kwargs["view"]
    assert isinstance(vista, ConfermaRipristinoView)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 0  # prima del clic non cambia niente
    clic = _inter()
    await vista.conferma.callback(clic)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300
    assert "Ripristinati" in _testo(clic.followup.send.await_args)


@pytest.mark.asyncio
async def test_ripristina_copia_inesistente_o_non_numero(cog):
    comando = _comando(cog, "admin-livelli azzera ripristina")
    for valore in ("999999", "abc", "9" * 19):
        inter = _inter()
        await comando.callback(cog, inter, valore)
        assert "Non trovo" in _testo(inter.response.send_message.await_args)


@pytest.mark.asyncio
async def test_il_bottone_vale_una_volta_e_solo_per_chi_ha_dato_il_comando(cog):
    await _xp(1, 300)
    esito = await leveling_copie_repo.azzera_server(GUILD, STAFF, "")
    vista = ConfermaRipristinoView(STAFF, esito.copia_id)
    altro = _inter(utente=9)
    assert await vista.interaction_check(altro) is False
    a, b = _inter(), _inter()
    await asyncio.gather(vista.conferma.callback(a), vista.conferma.callback(b))
    assert a.response.defer.await_count + b.response.defer.await_count == 1


@pytest.mark.asyncio
async def test_il_clic_ricontrolla_blocco_e_permesso(cog):
    await _xp(1, 300)
    esito = await leveling_copie_repo.azzera_server(GUILD, STAFF, "")
    await leveling_settings_repo.set_options(GUILD, blocca_azzeramento=True)
    clic = _inter()
    clic.response.defer.side_effect = lambda **k: setattr(clic.response.is_done, "return_value", True)
    await ConfermaRipristinoView(STAFF, esito.copia_id).conferma.callback(clic)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 0
    assert "proprietario" in _testo(clic.followup.send.await_args)


@pytest.mark.asyncio
async def test_il_menu_delle_copie_ha_al_massimo_25_scelte_da_100_caratteri(cog, clean_db):
    for _ in range(30):
        await clean_db.execute(
            "INSERT INTO leveling_copie (guild_id, tipo, scade_il) VALUES ($1, 'utente', now() + interval '1 day')", GUILD
        )
    scelte = await cog._scelte_copie(_inter(), "")
    assert len(scelte) == 25 and all(len(s.name) <= 100 and s.value.isdigit() for s in scelte)


# ---------------------------------------------------------------- LIV-070
@pytest.mark.asyncio
async def test_chi_esce_viene_azzerato_solo_se_il_server_lo_vuole(cog):
    guild = fake_guild(GUILD)
    membro = fake_member(1)
    membro.guild = guild
    await _xp(1, 300)
    await cog.on_member_remove(membro)  # di base: niente
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300
    await leveling_settings_repo.set_options(GUILD, azzera_su="entrambi", copia_su_uscita=True)
    await cog.on_member_remove(membro)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 0
    [copia] = await leveling_copie_repo.elenco(GUILD)
    assert copia.tipo == "utente"


@pytest.mark.asyncio
async def test_il_ban_azzera_con_la_scelta_ban_e_l_uscita_no(cog, monkeypatch):
    monkeypatch.setattr(modulo, "SECONDI_ATTESA_BAN", 0)
    guild = fake_guild(GUILD)
    await leveling_settings_repo.set_options(GUILD, azzera_su="ban")
    await _xp(1, 300)
    membro = fake_member(1)
    membro.guild = guild
    await cog.on_member_remove(membro)  # esce: con «ban» non si azzera
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300
    await cog.on_member_ban(guild, fake_member(1))
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 0
    assert await leveling_copie_repo.elenco(GUILD) == []  # copia spenta di base


@pytest.mark.asyncio
async def test_con_uscita_un_ban_conta_come_ban_non_come_uscita(cog, monkeypatch):
    monkeypatch.setattr(modulo, "SECONDI_ATTESA_BAN", 0)
    guild = fake_guild(GUILD)
    await leveling_settings_repo.set_options(GUILD, azzera_su="uscita")
    await _xp(1, 300)
    membro = fake_member(1)
    membro.guild = guild
    await cog.on_member_ban(guild, fake_member(1))  # il ban arriva per primo
    await cog.on_member_remove(membro)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300


@pytest.mark.asyncio
async def test_bot_modulo_spento_e_errori_non_azzerano_ne_rompono(cog, monkeypatch, clean_db):
    guild = fake_guild(GUILD)
    await leveling_settings_repo.set_options(GUILD, azzera_su="entrambi")
    await _xp(1, 300)
    bot = fake_member(1, bot=True)
    bot.guild = guild
    await cog.on_member_remove(bot)
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300
    monkeypatch.setattr(leveling_copie_repo, "azzera_utente", AsyncMock(side_effect=RuntimeError("giù")))
    membro = fake_member(1)
    membro.guild = guild
    await cog.on_member_remove(membro)  # l'errore resta nel log
    assert (await leveling_repo.get_totals(GUILD, 1)).xp_total == 300


# ---------------------------------------------------------------- LIV-075
@pytest.mark.asyncio
async def test_diagnosi_elenca_le_cause(cog):
    await leveling_settings_repo.set_rule(GUILD, "canale_escluso", 4242)
    await leveling_settings_repo.set_rule(GUILD, "ruolo_escluso", 77)
    canale = fake_text_channel(channel_id=4242)
    ruolo = MagicMock(id=77)
    membro = fake_member(1)
    membro.roles = [ruolo]
    membro.bot = False
    inter = _inter()
    await _comando(cog, "admin-livelli diagnosi").callback(cog, inter, membro, canale)
    descrizione = inter.followup.send.await_args.kwargs["embed"].description
    assert "escluso" in descrizione and descrizione.count("❌") == 2 and "Ostacoli trovati: 2" in descrizione


@pytest.mark.asyncio
async def test_diagnosi_senza_ostacoli_e_con_attesa_e_tetto(cog, clean_db):
    membro = fake_member(1)
    membro.roles = []
    membro.bot = False
    comando = _comando(cog, "admin-livelli diagnosi")
    inter = _inter()
    await comando.callback(cog, inter, membro, fake_text_channel(channel_id=5))
    descrizione = inter.followup.send.await_args.kwargs["embed"].description
    assert "❌" not in descrizione and "Nessun ostacolo" in descrizione
    # ha appena preso XP: c'è l'attesa; e con un tetto basso lo ha raggiunto
    await leveling_repo.add_text_xp(GUILD, 1, amount=15, cooldown_seconds=60, max_level=1)
    await leveling_repo.modifica_xp(GUILD, 1, "livello", 1)
    await leveling_settings_repo.set_options(GUILD, max_level=1)
    inter = _inter()
    await comando.callback(cog, inter, membro, fake_text_channel(channel_id=5))
    descrizione = inter.followup.send.await_args.kwargs["embed"].description
    assert "aspettare ancora" in descrizione and "livello massimo (1)" in descrizione


@pytest.mark.asyncio
async def test_diagnosi_blacklist(cog, monkeypatch):
    monkeypatch.setattr(blacklist_repo, "is_user_blacklisted", AsyncMock(return_value=True))
    membro = fake_member(1)
    membro.roles = []
    membro.bot = False
    inter = _inter()
    await _comando(cog, "admin-livelli diagnosi").callback(cog, inter, membro, None)
    assert "bloccati" in inter.followup.send.await_args.kwargs["embed"].description

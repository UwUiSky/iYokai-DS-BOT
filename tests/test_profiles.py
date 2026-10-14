"""
tests/test_profiles.py
======================
NF-40 (#111): profilo personale, badge e sfondi da collezionare comprati con
le coin. Catalogo, archivio su PostgreSQL vero (acquisto atomico) e comandi.
Funzioni coperte: SPEC §23.16
"""

import asyncio
from types import SimpleNamespace

import pytest

import cogs.leveling.profiles as modulo
from core.profile_logic import CATALOGO, MAX_BIO, PER_ID, oggetto, pulisci_bio
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.profile_repo import EsitoAcquisto, ProfileRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

GUILD = 100


# ----------------------------------------------------------------------
# Catalogo e testi
# ----------------------------------------------------------------------
def test_il_catalogo_e_coerente():
    assert len({o.id for o in CATALOGO}) == len(CATALOGO) == len(PER_ID)
    assert len(CATALOGO) <= 25  # una scelta fissa di Discord ne ha al massimo 25
    for o in CATALOGO:
        assert o.prezzo > 0 and o.tipo in ("badge", "sfondo")
        assert (o.emoji != "") == (o.tipo == "badge")
        assert (o.colore != 0) == (o.tipo == "sfondo")
    assert oggetto("non-esiste") is None


def test_la_presentazione_e_su_una_riga_e_corta():
    assert pulisci_bio("  ciao\n\n  a   tutti \t") == "ciao a tutti"
    assert len(pulisci_bio("x" * 1000)) == MAX_BIO


# ----------------------------------------------------------------------
# Archivio
# ----------------------------------------------------------------------
@pytest.fixture
def repo(clean_db):
    return ProfileRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def monete(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.fixture(autouse=True)
def _repo_coin_del_test(monkeypatch, clean_db):
    import core.repositories.leveling_repo as leveling_repo_module

    monkeypatch.setattr(leveling_repo_module.leveling_repo, "_pool_provider", lambda: clean_db)


@pytest.mark.asyncio
async def test_acquisto_toglie_il_prezzo_e_registra_l_oggetto(repo, monete):
    await monete.add_coins(GUILD, 1, 1000)
    assert await repo.buy(GUILD, 1, "stella") == EsitoAcquisto.COMPRATO
    assert (await monete.get_totals(GUILD, 1)).coins_total == 1000 - PER_ID["stella"].prezzo
    assert (await repo.get_profile(GUILD, 1)).posseduti == {"stella"}


@pytest.mark.asyncio
async def test_senza_coin_non_si_compra_e_non_resta_niente(repo, monete):
    await monete.add_coins(GUILD, 1, PER_ID["corona"].prezzo - 1)
    assert await repo.buy(GUILD, 1, "corona") == EsitoAcquisto.SALDO_INSUFFICIENTE
    assert (await monete.get_totals(GUILD, 1)).coins_total == PER_ID["corona"].prezzo - 1
    assert (await repo.get_profile(GUILD, 1)).posseduti == frozenset()


@pytest.mark.asyncio
async def test_non_si_paga_due_volte_lo_stesso_oggetto(repo, monete):
    await monete.add_coins(GUILD, 1, 1000)
    await repo.buy(GUILD, 1, "stella")
    assert await repo.buy(GUILD, 1, "stella") == EsitoAcquisto.GIA_POSSEDUTO
    assert (await monete.get_totals(GUILD, 1)).coins_total == 1000 - PER_ID["stella"].prezzo


@pytest.mark.asyncio
async def test_oggetto_inventato_e_rifiutato(repo):
    assert await repo.buy(GUILD, 1, "inventato") == EsitoAcquisto.SCONOSCIUTO


@pytest.mark.asyncio
async def test_acquisti_insieme_dello_stesso_oggetto_addebitano_una_volta(repo, monete, clean_db):
    await apri_connessioni(clean_db)
    await monete.add_coins(GUILD, 1, 1000)
    esiti = await asyncio.gather(*(repo.buy(GUILD, 1, "luna") for _ in range(6)))
    assert esiti.count(EsitoAcquisto.COMPRATO) == 1
    assert (await monete.get_totals(GUILD, 1)).coins_total == 1000 - PER_ID["luna"].prezzo


@pytest.mark.asyncio
async def test_acquisti_insieme_di_oggetti_diversi_non_vanno_sotto_zero(repo, monete, clean_db):
    await apri_connessioni(clean_db)
    # Il saldo copre due oggetti da 200 ma non tre.
    await monete.add_coins(GUILD, 1, 450)
    esiti = await asyncio.gather(
        repo.buy(GUILD, 1, "fiamma"), repo.buy(GUILD, 1, "tramonto"), repo.buy(GUILD, 1, "oceano")
    )
    assert esiti.count(EsitoAcquisto.COMPRATO) == 2
    assert esiti.count(EsitoAcquisto.SALDO_INSUFFICIENTE) == 1
    assert (await monete.get_totals(GUILD, 1)).coins_total == 50
    assert len((await repo.get_profile(GUILD, 1)).posseduti) == 2


@pytest.mark.asyncio
async def test_si_mette_solo_cio_che_si_possiede_e_del_tipo_giusto(repo, monete):
    await monete.add_coins(GUILD, 1, 1000)
    assert await repo.equip(GUILD, 1, "badge", "stella") is False  # non comprato
    await repo.buy(GUILD, 1, "stella")
    await repo.buy(GUILD, 1, "tramonto")
    assert await repo.equip(GUILD, 1, "badge", "stella") is True
    assert await repo.equip(GUILD, 1, "badge", "tramonto") is False  # è uno sfondo
    assert await repo.equip(GUILD, 1, "sfondo", "tramonto") is True
    profilo = await repo.get_profile(GUILD, 1)
    assert (profilo.badge_id, profilo.background_id) == ("stella", "tramonto")
    assert await repo.equip(GUILD, 1, "badge", None) is True
    assert (await repo.get_profile(GUILD, 1)).badge_id is None
    with pytest.raises(ValueError):
        await repo.equip(GUILD, 1, "cappello", None)


@pytest.mark.asyncio
async def test_bio_e_server_separati(repo, monete):
    await repo.set_bio(GUILD, 1, "ciao")
    await repo.set_bio(GUILD + 1, 1, "altro")
    assert (await repo.get_profile(GUILD, 1)).bio == "ciao"
    await repo.set_bio(GUILD, 1, None)
    assert (await repo.get_profile(GUILD, 1)).bio is None
    assert (await repo.get_profile(GUILD + 1, 1)).bio == "altro"
    await monete.add_coins(GUILD, 1, 500)
    await repo.buy(GUILD, 1, "stella")
    assert (await repo.get_profile(GUILD + 1, 1)).posseduti == frozenset()


# ----------------------------------------------------------------------
# Comandi
# ----------------------------------------------------------------------
@pytest.fixture
async def scena(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    profili = ProfileRepository(pool_provider=lambda: clean_db)
    monete = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "profile_repo", profili)
    monkeypatch.setattr(modulo, "leveling_repo", monete)
    cog = modulo.ProfilesCog(bot=None)
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return SimpleNamespace(cog=cog, comandi=comandi, profili=profili, monete=monete)


def _interazione(user_id=1):
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id, name=f"u{user_id}"))


def _scelta(valore, nome=None):
    return SimpleNamespace(value=valore, name=nome or valore)


def _testo(interazione):
    return interazione.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_i_comandi_stanno_sotto_level(scena):
    assert {"level profilo", "level collezione negozio", "level collezione compra",
            "level collezione equipaggia"} <= set(scena.comandi)


@pytest.mark.asyncio
async def test_compra_equipaggia_e_il_profilo_li_mostra(scena):
    await scena.monete.add_coins(GUILD, 1, 1000)
    await scena.comandi["level collezione compra"].callback(
        scena.cog, _interazione(), oggetto_scelto=_scelta("drago")
    )
    await scena.comandi["level collezione compra"].callback(
        scena.cog, _interazione(), oggetto_scelto=_scelta("oro")
    )  # 4000: non basta
    interazione = _interazione()
    await scena.comandi["level collezione compra"].callback(
        scena.cog, interazione, oggetto_scelto=_scelta("oro")
    )
    assert "abbastanza" in _testo(interazione)

    await scena.comandi["level collezione compra"].callback(
        scena.cog, _interazione(), oggetto_scelto=_scelta("notte")
    )
    await scena.comandi["level collezione equipaggia"].callback(
        scena.cog, _interazione(), tipo=_scelta("sfondo"), oggetto_scelto=_scelta("notte")
    )
    interazione = _interazione()
    await scena.comandi["level profilo"].callback(
        scena.cog, interazione, membro=None, presentazione="Ciao   mondo", cancella_presentazione=None
    )
    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert embed.description == "Ciao mondo"
    assert embed.color.value == PER_ID["notte"].colore
    assert "Collezione" in [f.name for f in embed.fields]
    assert "salvata" in _testo(interazione)


@pytest.mark.asyncio
async def test_il_badge_si_vede_solo_se_posseduto(scena, clean_db):
    # Una riga di impostazioni con un badge mai comprato (dati sporchi) non si mostra.
    await clean_db.execute(
        "INSERT INTO profile_settings (guild_id, user_id, badge_id) VALUES ($1, 1, 'corona')", GUILD
    )
    interazione = _interazione()
    await scena.comandi["level profilo"].callback(
        scena.cog, interazione, membro=None, presentazione=None, cancella_presentazione=None
    )
    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert "👑" not in embed.title


@pytest.mark.asyncio
async def test_non_si_cambia_la_presentazione_di_un_altro(scena):
    interazione = _interazione()
    await scena.comandi["level profilo"].callback(
        scena.cog, interazione, membro=fake_member(2), presentazione="hack", cancella_presentazione=None
    )
    assert "proprio profilo" in _testo(interazione)
    assert (await scena.profili.get_profile(GUILD, 2)).bio is None


@pytest.mark.asyncio
async def test_equipaggia_senza_oggetto_toglie(scena):
    await scena.monete.add_coins(GUILD, 1, 1000)
    await scena.profili.buy(GUILD, 1, "stella")
    await scena.profili.equip(GUILD, 1, "badge", "stella")
    interazione = _interazione()
    await scena.comandi["level collezione equipaggia"].callback(
        scena.cog, interazione, tipo=_scelta("badge", "Badge"), oggetto_scelto=None
    )
    assert "tolto" in _testo(interazione)
    assert (await scena.profili.get_profile(GUILD, 1)).badge_id is None


@pytest.mark.asyncio
async def test_il_negozio_elenca_il_catalogo(scena):
    interazione = _interazione()
    await scena.comandi["level collezione negozio"].callback(scena.cog, interazione)
    descrizione = interazione.response.send_message.await_args.kwargs["embed"].description
    assert all(o.nome in descrizione for o in CATALOGO)
    assert len(descrizione) < 4096


@pytest.mark.asyncio
async def test_con_il_modulo_spento_nessun_comando_del_profilo_gira(scena):
    import core.database as database_module

    await database_module.db.set_module_active_for_guild(GUILD, "leveling", False)
    await scena.monete.add_coins(GUILD, 1, 1000)
    interazione = _interazione()
    await scena.comandi["level collezione compra"].callback(
        scena.cog, interazione, oggetto_scelto=_scelta("stella")
    )
    assert "non è attivo" in _testo(interazione)
    assert (await scena.profili.get_profile(GUILD, 1)).posseduti == frozenset()
    for nome, args in (
        ("level profilo", dict(membro=None, presentazione=None, cancella_presentazione=None)),
        ("level collezione negozio", {}),
    ):
        interazione = _interazione()
        await scena.comandi[nome].callback(scena.cog, interazione, **args)
        assert "non è attivo" in _testo(interazione)


@pytest.mark.asyncio
async def test_la_presentazione_non_accetta_piu_di_quanto_si_salva(scena):
    from core.profile_logic import MAX_BIO

    opzione = next(p for p in scena.comandi["level profilo"].parameters if p.name == "presentazione")
    assert opzione.max_value == MAX_BIO

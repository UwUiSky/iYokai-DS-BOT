"""
tests/test_leveling_azzera.py
=============================
#124 B1 (LIV-068, 069, 070, 071): azzeramento del server con copia di sicurezza e
ripristino, azzeramento di chi esce o viene bannato, blocco al proprietario.
Logica pura e archivio su PostgreSQL vero.
Funzioni coperte: SPEC §15 (catalogo #124)
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from core import leveling_azzera_logic as logica
from core.leveling_logic import LevelingSettings
from core.repositories.leveling_copie_repo import LevelingCopieRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from tests.support.concorrenza import apri_connessioni

GUILD = 100
ALTRO = 200


# ----------------------------------------------------------------------
# Logica pura
# ----------------------------------------------------------------------
def test_il_nome_del_server_va_scritto_uguale_senza_badare_a_spazi_e_maiuscole():
    assert logica.nome_confermato("  Il Mio Server ", "il mio server")
    assert not logica.nome_confermato("Il Mio", "Il Mio Server")
    assert not logica.nome_confermato("", "")  # un nome vuoto non conferma niente


def test_il_blocco_vale_per_tutti_tranne_il_proprietario():
    assert logica.rifiutato_dal_blocco(True, user_id=5, owner_id=9)
    assert not logica.rifiutato_dal_blocco(True, user_id=9, owner_id=9)
    assert not logica.rifiutato_dal_blocco(False, user_id=5, owner_id=9)
    # proprietario sconosciuto con il blocco acceso: nessuno passa
    assert logica.rifiutato_dal_blocco(True, user_id=5, owner_id=None)


@pytest.mark.parametrize(
    "scelta, evento, atteso",
    [
        ("nessuno", "uscita", False), ("nessuno", "ban", False),
        ("uscita", "uscita", True), ("uscita", "ban", False),
        ("ban", "uscita", False), ("ban", "ban", True),
        ("entrambi", "uscita", True), ("entrambi", "ban", True),
    ],
)
def test_quando_si_azzera_chi_se_ne_va(scelta, evento, atteso):
    assert logica.deve_azzerare(scelta, evento) is atteso


def test_le_impostazioni_di_base_non_azzerano_e_non_bloccano():
    i = LevelingSettings()
    assert (i.azzera_su, i.copia_su_uscita, i.blocca_xp, i.blocca_azzeramento) == (
        "nessuno", False, False, False,
    )


def test_diagnosi_dice_tutte_le_cause_in_ordine():
    v = logica.diagnosi_xp(
        modulo_attivo=False, in_blacklist=True, e_bot=False, canale_escluso=True,
        ruolo_escluso=True, attesa_secondi=12, livello=10, max_level=10,
    )
    assert [x.chiave for x in v] == ["modulo", "blacklist", "canale", "ruolo", "attesa", "tetto"]
    assert [x.ok for x in v] == [False] * 6
    tutto_bene = logica.diagnosi_xp(
        modulo_attivo=True, in_blacklist=False, e_bot=False, canale_escluso=False,
        ruolo_escluso=False, attesa_secondi=0, livello=3, max_level=0,
    )
    assert all(x.ok for x in tutto_bene)
    assert logica.diagnosi_xp(
        modulo_attivo=True, in_blacklist=False, e_bot=True, canale_escluso=False,
        ruolo_escluso=False, attesa_secondi=0, livello=0, max_level=0,
    )[0].chiave == "bot"


# ----------------------------------------------------------------------
# Archivio
# ----------------------------------------------------------------------
@pytest.fixture
def xp(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def copie(clean_db):
    return LevelingCopieRepository(pool_provider=lambda: clean_db)


async def _prepara(xp, guild=GUILD, utenti=((1, 500), (2, 120), (3, 0))):
    for user, punti in utenti:
        if punti:
            await xp.modifica_xp(guild, user, "aggiungi", punti)
        await xp.add_coins(guild, user, 40)


@pytest.mark.asyncio
async def test_azzera_server_copia_prima_e_non_tocca_monete_ne_altri_server(xp, copie):
    await _prepara(xp)
    await _prepara(xp, ALTRO)
    esito = await copie.azzera_server(GUILD, autore_id=7, motivo="nuova stagione")
    assert esito.utenti == 2  # chi ha 0 XP non entra nella copia
    for user in (1, 2, 3):
        t = await xp.get_totals(GUILD, user)
        assert (t.xp_total, t.level, t.coins_total) == (0, 0, 40)
    assert (await xp.get_totals(ALTRO, 1)).xp_total == 500  # altro server intatto
    copia = await copie.get(GUILD, esito.copia_id)
    assert (copia.tipo, copia.righe, copia.autore_id, copia.motivo) == ("server", 2, 7, "nuova stagione")
    assert copia.scade_il - copia.creata_il == timedelta(days=logica.GIORNI_COPIA)


@pytest.mark.asyncio
async def test_azzerare_un_server_vuoto_non_crea_copie(xp, copie):
    assert await copie.azzera_server(GUILD, autore_id=7, motivo="") is None
    assert await copie.elenco(GUILD) == []


@pytest.mark.asyncio
async def test_il_ripristino_ridà_xp_e_livello_ma_non_toglie_mai_xp(xp, copie):
    await _prepara(xp)
    prima = await xp.get_totals(GUILD, 1)
    esito = await copie.azzera_server(GUILD, autore_id=7, motivo="")
    await xp.modifica_xp(GUILD, 2, "aggiungi", 5000)  # dopo l'azzeramento ha guadagnato più di prima
    await xp.modifica_xp(GUILD, 9, "aggiungi", 30)  # uno nuovo
    n = await copie.ripristina(GUILD, esito.copia_id)
    assert n == 2
    t1 = await xp.get_totals(GUILD, 1)
    assert (t1.xp_total, t1.level) == (prima.xp_total, prima.level)
    assert (await xp.get_totals(GUILD, 2)).xp_total == 5000  # non scende
    assert (await xp.get_totals(GUILD, 9)).xp_total == 30
    assert await copie.ripristina(GUILD, esito.copia_id) == 2  # ripeterlo non cambia niente
    assert (await xp.get_totals(GUILD, 1)).xp_total == prima.xp_total


@pytest.mark.asyncio
async def test_il_ripristino_non_pesca_la_copia_di_un_altro_server_o_scaduta(xp, copie, clean_db):
    await _prepara(xp)
    esito = await copie.azzera_server(GUILD, autore_id=7, motivo="")
    assert await copie.ripristina(ALTRO, esito.copia_id) is None
    assert await copie.get(ALTRO, esito.copia_id) is None
    await clean_db.execute(
        "UPDATE leveling_copie SET scade_il = $1", datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    assert await copie.ripristina(GUILD, esito.copia_id) is None
    assert await copie.elenco(GUILD) == []


@pytest.mark.asyncio
async def test_si_tengono_al_massimo_due_copie_del_server(xp, copie):
    ids = []
    for giro in range(3):
        await xp.modifica_xp(GUILD, 1, "aggiungi", 10 + giro)
        ids.append((await copie.azzera_server(GUILD, autore_id=7, motivo=str(giro))).copia_id)
    rimaste = [c.id for c in await copie.elenco(GUILD)]
    assert rimaste == [ids[2], ids[1]]  # la più nuova per prima
    assert await copie.get(GUILD, ids[0]) is None


@pytest.mark.asyncio
async def test_due_azzeramenti_insieme_fanno_una_copia_sola_con_i_dati_veri(xp, copie, clean_db):
    await _prepara(xp)
    await apri_connessioni(clean_db)
    esiti = await asyncio.gather(*(copie.azzera_server(GUILD, autore_id=7, motivo="") for _ in range(4)))
    veri = [e for e in esiti if e is not None]
    assert len(veri) == 1 and veri[0].utenti == 2
    assert len(await copie.elenco(GUILD)) == 1
    assert await copie.ripristina(GUILD, veri[0].copia_id) == 2
    assert (await xp.get_totals(GUILD, 1)).xp_total == 500


@pytest.mark.asyncio
async def test_il_motivo_lungo_viene_tagliato_a_512(xp, copie):
    await _prepara(xp)
    esito = await copie.azzera_server(GUILD, autore_id=7, motivo="x" * 900)
    assert len((await copie.get(GUILD, esito.copia_id)).motivo) == 512


@pytest.mark.asyncio
async def test_azzera_utente_con_e_senza_copia(xp, copie):
    await _prepara(xp)
    assert await copie.azzera_utente(GUILD, 1, con_copia=False, motivo="uscita") is True
    assert (await xp.get_totals(GUILD, 1)).xp_total == 0
    assert (await xp.get_totals(GUILD, 1)).coins_total == 40
    assert await copie.elenco(GUILD) == []
    assert await copie.azzera_utente(GUILD, 1, con_copia=False, motivo="uscita") is False  # già a zero
    assert await copie.azzera_utente(GUILD, 2, con_copia=True, motivo="ban") is True
    [c] = await copie.elenco(GUILD)
    assert (c.tipo, c.righe) == ("utente", 1)
    assert await copie.azzera_utente(GUILD, 2, con_copia=True, motivo="ban") is False
    assert len(await copie.elenco(GUILD)) == 1  # niente copie vuote
    assert await copie.ripristina(GUILD, c.id) == 1
    assert (await xp.get_totals(GUILD, 2)).xp_total == 120


@pytest.mark.asyncio
async def test_l_elenco_delle_copie_ha_un_tetto_di_25(xp, copie, clean_db):
    for i in range(30):
        await clean_db.execute(
            "INSERT INTO leveling_copie (guild_id, tipo, scade_il) VALUES ($1, 'utente', now() + interval '1 day')",
            GUILD,
        )
    assert len(await copie.elenco(GUILD)) == 25


@pytest.mark.asyncio
async def test_le_nuove_impostazioni_si_salvano_e_i_valori_strani_no(clean_db):
    repo = LevelingSettingsRepository(pool_provider=lambda: clean_db)
    i = await repo.set_options(
        GUILD, azzera_su="entrambi", copia_su_uscita=True, blocca_xp=True, blocca_azzeramento=True
    )
    assert (i.azzera_su, i.copia_su_uscita, i.blocca_xp, i.blocca_azzeramento) == ("entrambi", True, True, True)
    with pytest.raises(ValueError):
        await repo.set_options(GUILD, azzera_su="sempre")

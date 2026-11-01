"""
tests/test_staff_rischio.py
===========================
Punteggio di rischio di un membro e carico dello staff (SPEC §23.17, D50): logica pura,
letture vere sul database e i due comandi di /mod.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import cogs.moderation.rischio_staff as modulo
from core.database import db
from core.repositories.moderation_repo import ModerationRepository
from core.repositories.staff_carico_repo import StaffCaricoRepository
from core.staff_rischio_logic import (
    FASCIA_ALTA,
    FASCIA_BASSA,
    FASCIA_MEDIA,
    CaricoStaff,
    SegnaliRischio,
    calcola_rischio,
    testo_carico as scrivi_carico,
    testo_rischio as scrivi_rischio,
)
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

SERVER = 800
UTENTE = 111111111111111111
STAFF_A = 222222222222222222
STAFF_B = 333333333333333333
STAFF_C = 444444444444444444


# ------------------------------------------------------------------ logica pura
def test_nessun_segnale_rischio_basso():
    r = calcola_rischio(SegnaliRischio(eta_account_giorni=900, giorni_nel_server=300))
    assert (r.punteggio, r.fascia, r.motivi) == (0, FASCIA_BASSA, ())
    assert "Nessun segnale" in scrivi_rischio(r)


def test_ogni_segnale_ha_un_tetto_e_il_totale_arriva_a_cento():
    r = calcola_rischio(SegnaliRischio(warn_attivi=50, timeout_90_giorni=50, kick=50, ban_o_tempban=50, spam_trap=3,
                                       eta_account_giorni=1, giorni_nel_server=0, doppi=("alto",) * 9))
    assert r.punteggio == 100 and r.fascia == FASCIA_ALTA
    assert calcola_rischio(SegnaliRischio(warn_attivi=50)).punteggio == 40


def test_fasce_e_motivi_in_ordine_di_peso():
    r = calcola_rischio(SegnaliRischio(warn_attivi=2, eta_account_giorni=3))  # 16 + 15
    assert r.punteggio == 31 and r.fascia == FASCIA_MEDIA
    assert r.motivi[0] == "2 warn attivi" and "account di 3 giorni" in r.motivi[1]
    assert calcola_rischio(SegnaliRischio(eta_account_giorni=20)).punteggio == 8
    assert calcola_rischio(SegnaliRischio(spam_trap=1, ban_o_tempban=1)).fascia == FASCIA_ALTA  # 30 + 25


def test_i_doppi_pesano_per_livello():
    assert calcola_rischio(SegnaliRischio(doppi=("basso",))).punteggio == 4
    assert calcola_rischio(SegnaliRischio(doppi=("alto", "medio"))).punteggio == 37
    assert "non una prova" in scrivi_rischio(calcola_rischio(SegnaliRischio(doppi=("alto",))))


def test_carico_con_quote_e_avviso_se_uno_solo_fa_tutto():
    righe = [CaricoStaff(1, 70, 0, 0), CaricoStaff(2, 10, 0, 0), CaricoStaff(3, 10, 5, 5)]
    testo = scrivi_carico(righe, 30)
    assert testo.index("<@1>") < testo.index("<@3>") < testo.index("<@2>")
    assert "70 (70%)" in testo and "Più della metà" in testo
    assert "Nessuna attività" in scrivi_carico([], 30)
    uguali = scrivi_carico([CaricoStaff(i, 10, 0, 0) for i in range(1, 5)], 7)
    assert "Più della metà" not in uguali
    assert "…e altre 2" in scrivi_carico([CaricoStaff(i, 1, 0, 0) for i in range(1, 6)], 7, massimo_righe=3)


# ------------------------------------------------------------------ letture vere
@pytest.fixture
def repo(clean_db):
    return StaffCaricoRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def casi(clean_db):
    return ModerationRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_segnali_dai_casi_di_moderazione(repo, casi, clean_db):
    await casi.create_case(SERVER, UTENTE, STAFF_A, "warn", "a")
    await casi.create_case(SERVER, UTENTE, STAFF_A, "warn", "b")
    togli = await casi.create_case(SERVER, UTENTE, STAFF_A, "warn", "c")
    await casi.revoke_case(SERVER, togli, STAFF_A)  # un warn tolto non conta
    await casi.create_case(SERVER, UTENTE, STAFF_B, "timeout", "x", 600)
    await casi.create_case(SERVER, UTENTE, STAFF_B, "kick", "x")
    await casi.create_case(SERVER, UTENTE, STAFF_B, "ban", "x")
    await casi.create_case(SERVER, UTENTE, STAFF_B, "spam_trap_ban", "x")
    await casi.create_case(SERVER + 1, UTENTE, STAFF_B, "ban", "altro server")
    assert await repo.segnali_utente(SERVER, UTENTE) == (2, 1, 0 + 1, 2, 1)
    assert await repo.segnali_utente(SERVER, UTENTE + 1) == (0, 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_doppi_del_membro_in_un_server(repo, clean_db):
    await clean_db.execute(
        "INSERT INTO verify_doppi (guild_id, user_id, altro_user_id, livello) VALUES ($1, $2, $3, 'alto'), ($1, $4, $2, 'basso'), ($5, $2, $3, 'alto')",
        SERVER, UTENTE, STAFF_A, STAFF_B, SERVER + 1,
    )
    assert sorted(await repo.doppi_di(SERVER, UTENTE)) == ["alto", "basso"]
    assert await repo.doppi_di(SERVER, UTENTE + 5) == []


@pytest.mark.asyncio
async def test_carico_conta_casi_appelli_e_ticket_nel_periodo_senza_il_bot(repo, casi, clean_db):
    BOT = 999
    await casi.create_case(SERVER, UTENTE, STAFF_A, "warn", "a")
    await casi.create_case(SERVER, UTENTE, STAFF_A, "kick", "b")
    await casi.create_case(SERVER, UTENTE, BOT, "automod_escalation", "scala")
    vecchio = await casi.create_case(SERVER, UTENTE, STAFF_C, "warn", "vecchio")
    await clean_db.execute(
        "UPDATE moderation_cases SET created_at = now() - interval '60 days' WHERE guild_id = $1 AND case_number = $2",
        SERVER, vecchio,
    )
    await clean_db.execute(
        "INSERT INTO ban_appelli (guild_id, user_id, case_number, testo, stato, deciso_da, deciso_il) "
        "VALUES ($1, $2, 1, 'x', 'accettato', $3, now())",
        SERVER, UTENTE, STAFF_B,
    )
    await clean_db.execute(
        "INSERT INTO tickets (guild_id, ticket_number, channel_id, user_id, claimed_by) VALUES ($1, 1, 5001, $2, $3), ($1, 2, 5002, $2, $3)",
        SERVER, UTENTE, STAFF_A,
    )
    righe = {r.staff_id: r for r in await repo.carico(SERVER, 30, escludi=(BOT,))}
    assert set(righe) == {STAFF_A, STAFF_B}
    assert (righe[STAFF_A].casi, righe[STAFF_A].appelli, righe[STAFF_A].ticket) == (2, 0, 2)
    assert (righe[STAFF_B].casi, righe[STAFF_B].appelli, righe[STAFF_B].ticket) == (0, 1, 0)
    assert STAFF_C in {r.staff_id for r in await repo.carico(SERVER, 90, escludi=(BOT,))}


# ------------------------------------------------------------------ comandi
@pytest.fixture
def cog(monkeypatch, clean_db, repo):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    monkeypatch.setattr(modulo, "staff_carico_repo", repo)
    bot = MagicMock()
    bot.user.id = 999
    return modulo.RischioStaffCog(bot)


@pytest.mark.asyncio
async def test_il_comando_rischio_risponde_in_privato_con_i_motivi(cog, casi):
    await db.set_module_active_for_guild(SERVER, modulo.MODULE_CASE_SYSTEM, True)
    await casi.create_case(SERVER, UTENTE, STAFF_A, "warn", "a")
    membro = fake_member(UTENTE)
    membro.created_at = datetime.now(timezone.utc) - timedelta(days=3)
    membro.joined_at = datetime.now(timezone.utc) - timedelta(days=2)
    i = fake_interaction(guild=fake_guild(SERVER, owner_id=1), user=fake_member(STAFF_A))
    await cog.rischio.callback(cog, i, membro)
    argomenti = i.response.send_message.await_args.kwargs
    assert argomenti["ephemeral"] is True
    assert "1 warn attivi" in argomenti["embed"].description and "account di 3 giorni" in argomenti["embed"].description


@pytest.mark.asyncio
async def test_il_comando_carico_e_il_modulo_spento(cog, casi):
    i = fake_interaction(guild=fake_guild(SERVER, owner_id=1), user=fake_member(STAFF_A))
    await cog.carico.callback(cog, i, 30)  # modulo spento: lo dice e basta
    assert "non è attivo" in i.response.send_message.await_args.args[0]

    await db.set_module_active_for_guild(SERVER, modulo.MODULE_CASE_SYSTEM, True)
    await casi.create_case(SERVER, UTENTE, STAFF_A, "warn", "a")
    i2 = fake_interaction(guild=fake_guild(SERVER, owner_id=1), user=fake_member(STAFF_A))
    await cog.carico.callback(cog, i2, 30)
    assert f"<@{STAFF_A}>" in i2.response.send_message.await_args.kwargs["embed"].description

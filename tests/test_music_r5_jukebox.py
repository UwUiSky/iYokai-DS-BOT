"""
tests/test_music_r5_jukebox.py
==============================
Catalogo MUS (issue #126) giro r5mus: MUS-065, jukebox (un prezzo in monete per mettere un brano in coda).
Logica dell'addebito e del rimborso, scritture sul database (cassa del server), impostazione e percorso di `accoda`.
"""

from tests.support.flotta_finta import FlottaFinta
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import music_jukebox_logic as jl
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import add_coins_in
from core.repositories.music_jukebox_repo import MusicJukeboxRepository

G, U = 100, 7


# ----------------------------- logica -----------------------------
async def test_prezzo_zero_non_tocca_le_monete():
    addebita, rimborsa = AsyncMock(), AsyncMock()
    azione = AsyncMock(return_value=True)
    assert await jl.esegui_con_addebito(0, addebita, rimborsa, azione) == (jl.Esito.LIBERO, True)
    addebita.assert_not_awaited()
    rimborsa.assert_not_awaited()


async def test_senza_monete_l_azione_non_parte():
    azione = AsyncMock(return_value=True)
    esito = await jl.esegui_con_addebito(5, AsyncMock(return_value=False), AsyncMock(), azione)
    assert esito == (jl.Esito.SENZA_MONETE, False)
    azione.assert_not_awaited()


async def test_pagato_se_il_brano_entra():
    rimborsa = AsyncMock()
    esito = await jl.esegui_con_addebito(5, AsyncMock(return_value=True), rimborsa, AsyncMock(return_value=True))
    assert esito == (jl.Esito.PAGATO, True)
    rimborsa.assert_not_awaited()


async def test_rimborso_se_il_brano_non_entra():
    rimborsa = AsyncMock()
    esito = await jl.esegui_con_addebito(5, AsyncMock(return_value=True), rimborsa, AsyncMock(return_value=False))
    assert esito == (jl.Esito.NON_IN_CODA, False)
    rimborsa.assert_awaited_once()


async def test_rimborso_se_l_azione_solleva_e_l_errore_resta():
    rimborsa = AsyncMock()

    async def male():
        raise RuntimeError("lavalink giu'")

    with pytest.raises(RuntimeError):
        await jl.esegui_con_addebito(5, AsyncMock(return_value=True), rimborsa, male)
    rimborsa.assert_awaited_once()


async def test_rimborso_se_il_comando_viene_annullato():
    rimborsa = AsyncMock()
    partita = asyncio.Event()

    async def lenta():
        partita.set()
        await asyncio.sleep(10)

    compito = asyncio.create_task(jl.esegui_con_addebito(5, AsyncMock(return_value=True), rimborsa, lenta))
    await partita.wait()
    compito.cancel()
    with pytest.raises(asyncio.CancelledError):
        await compito
    rimborsa.assert_awaited_once()


async def test_un_rimborso_che_fallisce_non_nasconde_il_problema_dell_azione():
    async def male():
        raise RuntimeError("azione")

    with pytest.raises(RuntimeError, match="azione"):
        await jl.esegui_con_addebito(5, AsyncMock(return_value=True), AsyncMock(side_effect=OSError("db")), male)


def test_prezzo_valido():
    assert jl.PREZZO_MAX > 0
    for ok in (0, 1, jl.PREZZO_MAX):
        assert jl.prezzo_valido(ok) == ok
    for male in (-1, jl.PREZZO_MAX + 1, True, "3", None, 2.5):
        assert jl.prezzo_valido(male) == 0


# ----------------------------- database -----------------------------
@pytest.fixture
async def repo(clean_db):
    return MusicJukeboxRepository(lambda: clean_db)


async def _saldo(pool, uid=U):
    return await pool.fetchval("SELECT coins_total FROM leveling_totals WHERE guild_id=$1 AND user_id=$2", G, uid) or 0


async def _cassa(pool):
    return await pool.fetchval("SELECT balance FROM guild_chest WHERE guild_id=$1", G) or 0


async def _dai(pool, monete, uid=U):
    async with pool.acquire() as conn:
        await add_coins_in(conn, G, uid, monete, classifica=False)


async def test_addebito_va_alla_cassa_con_il_suo_movimento(repo, clean_db):
    await _dai(clean_db, 50)
    assert await repo.addebita(G, U, 20) is True
    assert (await _saldo(clean_db), await _cassa(clean_db)) == (30, 20)
    voci = await GuildChestRepository(lambda: clean_db).list_ledger(G)
    assert [(v.amount, v.reason) for v in voci] == [(20, "music_jukebox")]


async def test_saldo_insufficiente_non_scrive_niente(repo, clean_db):
    await _dai(clean_db, 10)
    assert await repo.addebita(G, U, 20) is False
    assert await repo.addebita(G, 999, 1) is False  # nessuna riga
    assert (await _saldo(clean_db), await _cassa(clean_db)) == (10, 0)
    assert await GuildChestRepository(lambda: clean_db).list_ledger(G) == []


async def test_importi_non_positivi_sono_un_errore_di_chi_chiama(repo):
    for male in (0, -3):
        with pytest.raises(ValueError):
            await repo.addebita(G, U, male)
        with pytest.raises(ValueError):
            await repo.rimborsa(G, U, male)


async def test_doppio_clic_non_spende_piu_del_saldo(repo, clean_db):
    await _dai(clean_db, 50)
    esiti = await asyncio.gather(*(repo.addebita(G, U, 20) for _ in range(6)))
    assert esiti.count(True) == 2
    assert (await _saldo(clean_db), await _cassa(clean_db)) == (10, 40)


async def test_rimborso_rimette_le_monete_e_toglie_dalla_cassa(repo, clean_db):
    await _dai(clean_db, 50)
    await repo.addebita(G, U, 20)
    await repo.rimborsa(G, U, 20)
    assert (await _saldo(clean_db), await _cassa(clean_db)) == (50, 0)
    voci = await GuildChestRepository(lambda: clean_db).list_ledger(G)
    assert sorted(v.amount for v in voci) == [-20, 20]


async def test_rimborso_con_la_cassa_gia_spesa_paga_comunque_chi_ha_perso_le_monete(repo, clean_db):
    await _dai(clean_db, 50)
    await repo.addebita(G, U, 20)
    await clean_db.execute("UPDATE guild_chest SET balance = 5 WHERE guild_id = $1", G)  # qualcuno l'ha spesa
    await repo.rimborsa(G, U, 20)
    assert (await _saldo(clean_db), await _cassa(clean_db)) == (50, 0)  # la cassa non va sotto zero


# ----------------------------- impostazione -----------------------------
async def test_impostazione_default_spenta_e_valori_strani_valgono_zero():
    from core.music_settings_logic import SETTING_JUKEBOX_PRICE, load_music_settings, summary_lines

    class Finto:
        def __init__(self, v):
            self.v = v

        async def get_guild_setting(self, g, chiave, default=None):
            return self.v if chiave == SETTING_JUKEBOX_PRICE else default

    assert (await load_music_settings(Finto(None), 1)).jukebox_price == 0
    assert (await load_music_settings(Finto(25), 1)).jukebox_price == 25
    assert (await load_music_settings(Finto(-4), 1)).jukebox_price == 0
    assert (await load_music_settings(Finto(10**12), 1)).jukebox_price == 0
    riepilogo = summary_lines(await load_music_settings(Finto(25), 1))
    assert any("Jukebox" in r and "25" in r for r in riepilogo)
    assert any("Jukebox" in r and "spento" in r for r in summary_lines(await load_music_settings(Finto(0), 1)))


# ----------------------------- percorso di accoda -----------------------------
from unittest.mock import patch  # noqa: E402

import cogs.music.player as player_module  # noqa: E402
from tests.test_music_f2 import _cog_per_play, _Interazione  # noqa: E402


class _RepoFinto:
    def __init__(self, ok=True):
        self.addebita = AsyncMock(return_value=ok)
        self.rimborsa = AsyncMock()


def _brano():
    return [SimpleNamespace(title="Canzone", length=1000, extras=None, is_stream=False)]


async def test_accoda_con_jukebox_addebita_prima_della_ricerca_e_non_rimborsa_se_entra(monkeypatch):
    cog, _flotta, _canale = _cog_per_play(monkeypatch, music_jukebox_price=10)
    repo = _RepoFinto()
    monkeypatch.setattr(player_module, "music_jukebox_repo", repo)
    i = _Interazione()
    with patch.object(cog, "_cerca", new=AsyncMock(return_value=(_brano(), object()))):
        await cog.play.callback(cog, i, query="https://93.184.216.34/a")
    repo.addebita.assert_awaited_once_with(900, i.user.id, 10)
    repo.rimborsa.assert_not_awaited()
    assert any("10" in m for m in i.followup.inviati)


async def test_accoda_senza_monete_non_cerca_e_non_fa_entrare_il_bot(monkeypatch):
    cog, flotta, canale = _cog_per_play(monkeypatch, music_jukebox_price=10)
    repo = _RepoFinto(ok=False)
    monkeypatch.setattr(player_module, "music_jukebox_repo", repo)
    i = _Interazione()
    cerca = AsyncMock(return_value=(_brano(), object()))
    with patch.object(cog, "_cerca", new=cerca):
        await cog.play.callback(cog, i, query="https://93.184.216.34/a")
    cerca.assert_not_awaited()
    assert canale.cls is None
    assert flotta.rilasci == [(900, 11)]  # lo slot non resta assegnato
    repo.rimborsa.assert_not_awaited()


async def test_accoda_rimborsa_se_non_c_e_nessun_risultato(monkeypatch):
    cog, _flotta, _canale = _cog_per_play(monkeypatch, music_jukebox_price=10)
    repo = _RepoFinto()
    monkeypatch.setattr(player_module, "music_jukebox_repo", repo)
    i = _Interazione()
    with patch.object(cog, "_cerca", new=AsyncMock(return_value=(None, object()))):
        await cog.play.callback(cog, i, query="https://93.184.216.34/a")
    repo.addebita.assert_awaited_once()
    repo.rimborsa.assert_awaited_once_with(900, i.user.id, 10)


async def test_accoda_rimborsa_se_la_ricerca_solleva(monkeypatch):
    cog, _flotta, _canale = _cog_per_play(monkeypatch, music_jukebox_price=10)
    repo = _RepoFinto()
    monkeypatch.setattr(player_module, "music_jukebox_repo", repo)
    i = _Interazione()
    with patch.object(cog, "_cerca", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(RuntimeError):
            await cog.play.callback(cog, i, query="https://93.184.216.34/a")
    repo.rimborsa.assert_awaited_once()


async def test_accoda_con_jukebox_spento_non_tocca_le_monete(monkeypatch):
    cog, _flotta, _canale = _cog_per_play(monkeypatch)
    repo = _RepoFinto()
    monkeypatch.setattr(player_module, "music_jukebox_repo", repo)
    i = _Interazione()
    with patch.object(cog, "_cerca", new=AsyncMock(return_value=(_brano(), object()))):
        await cog.play.callback(cog, i, query="https://93.184.216.34/a")
    repo.addebita.assert_not_awaited()
    repo.rimborsa.assert_not_awaited()

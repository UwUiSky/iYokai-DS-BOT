"""
tests/test_immagini_quarantena.py
=================================
Quarantena dei byte (D61, D62): nome casuale, permessi, registro, scadenza.
"""

import os
import re
import stat

import pytest

from core import immagini_quarantena as q
from tests.support import immagini_finte as f

GUILD = 777000701


@pytest.fixture
def cartella(tmp_path, monkeypatch):
    monkeypatch.setenv(q.VARIABILE_CARTELLA, str(tmp_path / "quar"))
    return tmp_path / "quar"


@pytest.fixture
async def archivio(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    return clean_db


@pytest.mark.asyncio
async def test_salva_con_nome_casuale_e_permessi_stretti(cartella, archivio):
    dati = f.png()
    voce = await q.salva(dati, GUILD, "ab" * 32)
    assert re.fullmatch(r"[0-9a-f]{32}", voce.nome)
    percorso = cartella / voce.nome
    assert percorso.read_bytes() == dati
    assert stat.S_IMODE(percorso.stat().st_mode) == 0o640
    assert stat.S_IMODE(cartella.stat().st_mode) in (0o2750, 0o750)
    riga = await archivio.fetchrow("SELECT * FROM quarantena_file WHERE nome = $1", voce.nome)
    assert riga["guild_id"] == GUILD and riga["sha256"] == "ab" * 32


@pytest.mark.asyncio
async def test_due_salvataggi_hanno_nomi_diversi(cartella, archivio):
    a, b = await q.salva(b"x", GUILD, "00"), await q.salva(b"x", GUILD, "00")
    assert a.nome != b.nome


@pytest.mark.asyncio
async def test_non_sovrascrive_un_file_esistente(cartella, archivio, monkeypatch):
    primo = await q.salva(b"uno", GUILD, "00")
    # Il generatore da' prima un nome gia' in uso, poi uno libero: O_EXCL deve far riprovare.
    chiamate = iter([primo.nome, "f" * 32])
    monkeypatch.setattr(q.secrets, "token_hex", lambda n: next(chiamate))
    nuovo = await q.salva(b"due", GUILD, "00")
    assert nuovo.nome == "f" * 32
    assert (cartella / primo.nome).read_bytes() == b"uno"


@pytest.mark.asyncio
async def test_cancella_toglie_file_e_riga(cartella, archivio):
    voce = await q.salva(b"x", GUILD, "00")
    await q.cancella(voce.nome)
    assert not (cartella / voce.nome).exists()
    assert await archivio.fetchval("SELECT count(*) FROM quarantena_file") == 0
    await q.cancella(voce.nome)  # seconda volta: niente errori


@pytest.mark.asyncio
async def test_nome_non_valido_non_tocca_il_disco(cartella, archivio):
    for nome in ("../etc/passwd", "ABC", "", "a" * 31):
        with pytest.raises(ValueError):
            q.percorso_di(nome)


@pytest.mark.asyncio
async def test_pulizia_toglie_solo_i_scaduti_e_gli_orfani_vecchi(cartella, archivio):
    vecchia = await q.salva(b"v", GUILD, "00", ore=72)
    nuova = await q.salva(b"n", GUILD, "00", ore=72)
    await archivio.execute("UPDATE quarantena_file SET scade_il = now() - interval '1 minute' WHERE nome = $1", vecchia.nome)
    orfano = cartella / ("a" * 32)
    orfano.write_bytes(b"orfano")
    os.utime(orfano, (0, 0))
    recente_orfano = cartella / ("b" * 32)
    recente_orfano.write_bytes(b"recente")
    tolti = await q.pulisci()
    assert tolti == 2
    assert not (cartella / vecchia.nome).exists() and not orfano.exists()
    assert (cartella / nuova.nome).exists() and recente_orfano.exists()

"""
tests/test_archivio_utente_log029.py
====================================
LOG-029 (D121): a ogni sanzione si salva, legato al caso, l'archivio degli eventi dei messaggi di un utente
degli ultimi 3 giorni, presi dal registro eventi già salvato (nessuna raccolta nuova). Database vero.
"""

import pytest

from core import moderation_archivio_utente as arc
from core.database import db
from core.repositories.event_log_repo import event_log_repo
from core.repositories.moderation_repo import moderation_repo

G, U, ALTRO = 910001, 920001, 920002


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    yield


async def _evento(tipo, utente, canale, giorni_fa, gid=G):
    r = await db.pool.fetchval(
        "INSERT INTO event_log (guild_id, event_type, target_user_id, channel_id, details, created_at) "
        "VALUES ($1,$2,$3,$4,$5, NOW() - make_interval(days => $6)) RETURNING id",
        gid, tipo, utente, canale, '{"message_id": 55}', giorni_fa,
    )
    return r


async def test_l_archivio_prende_solo_i_messaggi_dell_utente_degli_ultimi_3_giorni():
    await _evento("message_delete", U, 11, 1)
    await _evento("message_edit", U, 12, 2)
    await _evento("message_delete", U, 13, 5)  # troppo vecchio
    await _evento("message_delete", ALTRO, 11, 1)  # altro utente
    await _evento("member_join", U, None, 1)  # non è un messaggio
    await _evento("message_delete", U, 14, 1, gid=G + 1)  # altro server
    assert await arc.salva(G, 7, U) == 2
    letto = await arc.leggi(G, 7)
    testo = letto[0].decode()
    assert "<#11>" in testo and "<#12>" in testo and "<#13>" not in testo and "<#14>" not in testo
    assert "cancellato" in testo and "modificato" in testo
    assert letto[1] == 2


async def test_senza_eventi_non_si_salva_niente():
    assert await arc.salva(G, 8, U) == 0
    assert await arc.leggi(G, 8) is None


async def test_non_solleva_mai_se_il_database_fallisce(monkeypatch):
    async def rotto(*a, **k):
        raise RuntimeError("giu")

    monkeypatch.setattr(event_log_repo, "get_events_by_user", rotto)
    assert await arc.salva(G, 9, U) == 0


async def test_l_archivio_resta_finche_c_e_il_caso_e_va_con_il_caso():
    await _evento("message_delete", U, 11, 1)
    n = await moderation_repo.create_case(guild_id=G, user_id=U, moderator_id=1, action_type="warn", reason="x")
    await arc.salva(G, n, U)
    # nessuna scadenza: una riga vecchia di un anno resta
    await db.pool.execute("UPDATE moderation_archivio_utente SET creato = NOW() - interval '400 days'")
    assert await arc.leggi(G, n) is not None
    await moderation_repo.delete_case(G, n)
    assert await arc.leggi(G, n) is None


async def test_il_testo_non_pinga_e_non_contiene_testo_dei_messaggi():
    await _evento("message_delete", U, 11, 1)
    await arc.salva(G, 3, U)
    testo = (await arc.leggi(G, 3))[0].decode()
    assert "@everyone" not in testo
    assert "testo" in testo.lower() or "non conserva" in testo.lower()

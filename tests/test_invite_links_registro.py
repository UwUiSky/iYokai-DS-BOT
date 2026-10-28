"""
tests/test_invite_links_registro.py
===================================
Privacy dei link personali e dello storico (D6, #46): cancellazione per utente, invitante
anonimizzato, scadenza.
"""

import pytest

from core import data_registry as reg


@pytest.mark.asyncio
async def test_cancellando_un_utente_sparisce_come_invitato_e_resta_come_zero_come_invitante(clean_db):
    t = reg.tabella("invite_joins")
    await clean_db.execute(
        "INSERT INTO invite_joins (guild_id, user_id, inviter_id, code, kind) VALUES "
        "(1, 10, 99, 'a', 'normale'), (1, 99, NULL, NULL, 'sconosciuto'), (1, 11, 99, 'a', 'personale')"
    )
    assert t.colonne_utente == ("user_id",) and t.attori_da_azzerare() == ("inviter_id",)
    await clean_db.execute(t.sql_cancella_utente(), 99)
    await clean_db.execute(t.sql_azzera_attore("inviter_id"), 99)
    righe = {r["user_id"]: r["inviter_id"] for r in await clean_db.fetch("SELECT user_id, inviter_id FROM invite_joins")}
    assert righe == {10: 0, 11: 0}


@pytest.mark.asyncio
async def test_link_personale_cancellato_con_l_utente_e_scade_dopo_un_anno(clean_db):
    t = reg.tabella("invite_personal_links")
    assert t.utente == "cancella" and t.esporta
    await clean_db.execute(
        "INSERT INTO invite_personal_links (slug, guild_id, user_id, created_at, last_used_at) VALUES "
        "('a-uno', 1, 10, now() - interval '400 days', NULL), "
        "('a-due', 1, 11, now() - interval '400 days', now() - interval '5 days'), "
        "('a-tre', 1, 12, now(), NULL)"
    )
    await clean_db.execute(t.sql_scaduti(), t.scadenza.giorni)
    assert {r["slug"] for r in await clean_db.fetch("SELECT slug FROM invite_personal_links")} == {"a-due", "a-tre"}
    await clean_db.execute(t.sql_cancella_utente(), 12)
    assert {r["slug"] for r in await clean_db.fetch("SELECT slug FROM invite_personal_links")} == {"a-due"}

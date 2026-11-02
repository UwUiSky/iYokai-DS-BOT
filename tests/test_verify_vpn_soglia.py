"""
tests/test_verify_vpn_soglia.py
===============================
D67: il «Lascia passare» degli altri server vale solo con almeno 3 approvazioni di server diversi, a un'ora
di distanza, con founder diversi e admin diversi. Sotto la soglia vale solo nel server che l'ha dato.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import verify_vpn_logic as logica
from tests.test_verify_vpn_flusso import (  # noqa: F401  (la fixture _dati_finti è automatica)
    GUILD, IP_VPN, _ambiente, _dati_finti, _interazione, _prepara, _verifica,
)

ADESSO = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def riga(guild, founder, admin, ore_fa=0.0):
    return {"guild_id": guild, "founder_id": founder, "admin_id": admin, "creato_il": ADESSO - timedelta(hours=ore_fa)}


# ------------------------------------------------------------- logica pura
def test_tre_approvazioni_tutte_diverse_bastano():
    assert logica.storico_basta([riga(1, 11, 21, 0), riga(2, 12, 22, 2), riga(3, 13, 23, 5)])


def test_due_approvazioni_non_bastano():
    assert not logica.storico_basta([riga(1, 11, 21, 0), riga(2, 12, 22, 2)])
    assert not logica.storico_basta([])


def test_stesso_founder_con_tre_server_conta_una_volta():
    assert not logica.storico_basta([riga(1, 11, 21, 0), riga(2, 11, 22, 2), riga(3, 11, 23, 5)])


def test_stesso_admin_in_tre_server_conta_una_volta():
    assert not logica.storico_basta([riga(1, 11, 21, 0), riga(2, 12, 21, 2), riga(3, 13, 21, 5)])


def test_tre_clic_nella_stessa_ora_contano_come_uno():
    assert not logica.storico_basta([riga(1, 11, 21, 0.0), riga(2, 12, 22, 0.2), riga(3, 13, 23, 0.5)])


def test_un_clic_a_meno_di_un_ora_dagli_altri_non_conta_ma_un_quarto_valido_si():
    base = [riga(1, 11, 21, 0.0), riga(2, 12, 22, 0.3), riga(3, 13, 23, 5.0)]
    assert not logica.storico_basta(base)
    assert logica.storico_basta(base + [riga(4, 14, 24, 9.0)])


def test_un_gruppo_valido_si_trova_anche_fra_righe_che_si_scontrano():
    righe = [riga(1, 11, 21, 0), riga(2, 11, 22, 3), riga(3, 12, 23, 6), riga(4, 13, 21, 9), riga(5, 14, 24, 12)]
    assert logica.storico_basta(righe)  # per esempio 1, 3 e 5


def test_esattamente_un_ora_di_distanza_basta():
    assert logica.storico_basta([riga(1, 11, 21, 0), riga(2, 12, 22, 1), riga(3, 13, 23, 2)])


def test_righe_di_prima_della_regola_senza_founder_o_admin_non_contano():
    vecchie = [riga(1, None, None, 0), riga(2, None, 22, 2), riga(3, 13, None, 5)]
    assert not logica.storico_basta(vecchie)
    assert not logica.storico_basta(vecchie + [riga(4, 14, 24, 8), riga(5, 15, 25, 10)])


def test_lo_stesso_server_due_volte_non_conta_due():
    assert not logica.storico_basta([riga(1, 11, 21, 0), riga(1, 12, 22, 3), riga(2, 13, 23, 6)])


def test_il_tetto_di_righe_tiene_il_controllo_corto():
    tante = [riga(i, 11, 21, i) for i in range(500)]  # tutti con lo stesso founder: nessuna combinazione
    assert not logica.storico_basta(tante)


# ------------------------------------------------------------- col database
async def _approva(clean_db, guild, user, founder, admin, ore_fa):
    await clean_db.execute(
        "INSERT INTO verify_vpn_storico (guild_id, user_id, metodo, founder_id, admin_id, creato_il) "
        "VALUES ($1, $2, 'tor', $3, $4, now() - make_interval(hours => $5))",
        guild, user, founder, admin, ore_fa,
    )


@pytest.mark.asyncio
async def test_tre_approvazioni_diverse_fanno_passare_qui_con_avviso(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    await _approva(clean_db, GUILD + 1, 400, 11, 21, 0)
    await _approva(clean_db, GUILD + 2, 400, 12, 22, 3)
    await _approva(clean_db, GUILD + 3, 400, 13, 23, 6)
    ok, _ = await _verifica(amb, 400, IP_VPN)
    assert ok
    assert "già stato accettato da 3 server" in amb.log.send.await_args.kwargs["embed"].description
    assert (await amb.repo.leggi(GUILD, 400))["esito"] == "da_storico"


@pytest.mark.asyncio
@pytest.mark.parametrize("righe", [
    [(11, 21, 0), (12, 22, 3)],  # solo 2
    [(11, 21, 0), (11, 22, 3), (11, 23, 6)],  # stesso founder
    [(11, 21, 0), (12, 21, 3), (13, 21, 6)],  # stesso admin
    [(11, 21, 0.0), (12, 22, 0.2), (13, 23, 0.4)],  # nella stessa ora
], ids=["due", "stesso_founder", "stesso_admin", "stessa_ora"])
async def test_sotto_la_soglia_qui_resta_bloccata(monkeypatch, clean_db, righe):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    for n, (founder, admin, ore) in enumerate(righe, start=1):
        await _approva(clean_db, GUILD + n, 401, founder, admin, ore)
    ok, testo = await _verifica(amb, 401, IP_VPN)
    assert not ok and "vpn" in testo.lower()
    assert (await amb.repo.leggi(GUILD, 401))["esito"] == "bloccato"
    assert "già stato accettato" not in amb.log.send.await_args.kwargs["embed"].description


@pytest.mark.asyncio
async def test_sotto_la_soglia_vale_solo_nel_server_che_l_ha_dato(monkeypatch, clean_db):
    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    assert await amb.repo.lascia_passare(GUILD + 1, 402, founder_id=11, admin_id=21)
    ok, _ = await _verifica(amb, 402, IP_VPN)
    assert not ok  # qui no
    assert await amb.repo.ha_eccezione(GUILD + 1, 402) and not await amb.repo.ha_eccezione(GUILD, 402)


@pytest.mark.asyncio
async def test_il_clic_salva_founder_del_server_e_admin_che_ha_premuto(monkeypatch, clean_db):
    from unittest.mock import AsyncMock

    from core import verify_vpn_staff as staff

    amb = _ambiente(monkeypatch, clean_db)
    await _prepara(clean_db)
    await _verifica(amb, 403, IP_VPN)
    monkeypatch.setattr(staff, "puo_usare", AsyncMock(return_value=True))
    i = _interazione(amb)
    await staff.lascia_passare(i, 403)
    r = await clean_db.fetchrow("SELECT founder_id, admin_id FROM verify_vpn_storico WHERE guild_id = $1 AND user_id = 403", GUILD)
    assert (r["founder_id"], r["admin_id"]) == (amb.guild.owner_id, i.user.id)

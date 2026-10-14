"""
tests/test_ai_router.py
=======================
Lo snodo (SPEC §25.1, §25.10, §25.13, §25.94, §25.95): scelta per tipo e fascia,
quote contate e salto oltre l'85 %, pausa su errore con Retry-After, passaggio
al fornitore successivo, chiavi a pagamento solo con l'interruttore, controllo
delle chiavi. Trasporto finto, nessuna rete.
"""

import pytest

from core.ai_providers import ErroreFornitore, LimitiFornitore
from core.ai_router import MotoreAI, NessunFornitore, StatoFornitori, scegli_fornitori
from tests.support.ai_finto import TrasportoFinto, fornitore


def test_vince_la_fascia_piu_bassa_che_basta():
    alta, bassa, media = fornitore("alta", fascia="alta"), fornitore("bassa"), fornitore("media", fascia="media")
    stato = StatoFornitori()
    assert [f.nome for f in scegli_fornitori([alta, bassa, media], "chat", "bassa", stato)] == ["bassa", "media", "alta"]
    assert [f.nome for f in scegli_fornitori([alta, bassa, media], "chat", "media", stato)] == ["media", "alta"]


def test_solo_chi_sa_fare_il_tipo():
    img = fornitore("img", tipi=("immagine",))
    assert scegli_fornitori([fornitore("t"), img], "immagine", "bassa", StatoFornitori()) == [img]


def test_quota_oltre_85_per_cento_salta_il_fornitore():
    f = fornitore("a", limiti=LimitiFornitore(rpm=10))
    stato = StatoFornitori()
    for _ in range(8):
        stato.registra("a", 1, ora=100)
    assert scegli_fornitori([f], "chat", "bassa", stato, ora=100) == [f]
    stato.registra("a", 1, ora=100)
    assert scegli_fornitori([f], "chat", "bassa", stato, ora=100) == []
    assert scegli_fornitori([f], "chat", "bassa", stato, ora=161) == [f]  # nuovo minuto


def test_quota_dichiarata_dalle_intestazioni():
    f = fornitore("a")
    stato = StatoFornitori()
    stato.leggi_intestazioni("a", {"X-RateLimit-Limit-Requests": "100", "X-RateLimit-Remaining-Requests": "5"}, ora=0)
    assert stato.uso(f, ora=1) == pytest.approx(0.95)
    assert scegli_fornitori([f], "chat", "bassa", stato, ora=1) == []
    assert stato.uso(f, ora=61) == 0


def test_a_pagamento_solo_con_interruttore_e_solo_gratuiti_sotto_tetto():
    pag = fornitore("pag", a_pagamento=True)
    costa = fornitore("costa", costo_cent_milione=50)
    stato = StatoFornitori()
    assert scegli_fornitori([pag], "chat", "bassa", stato) == []
    assert scegli_fornitori([pag], "chat", "bassa", stato, usa_pagamento=True) == [pag]
    assert scegli_fornitori([costa], "chat", "bassa", stato, solo_gratuiti=True) == []


async def test_errore_mette_in_pausa_e_passa_al_successivo():
    a, b = fornitore("a"), fornitore("b")
    trasporto = TrasportoFinto(errori={"a": ErroreFornitore(429, retry_after=30)})
    motore = MotoreAI([a, b], trasporto)
    esito = await motore.esegui("chat", "bassa", messaggi=[{"role": "user", "content": "ciao"}])
    assert esito.fornitore == "b" and esito.testo == "risposta di b"
    assert motore.stato.in_pausa("a")
    trasporto.chiamate.clear()
    await motore.esegui("chat", "bassa", messaggi=[])
    assert [n for n, _ in trasporto.chiamate] == ["b"]  # a resta in pausa


def test_pausa_cresce_senza_retry_after():
    stato = StatoFornitori()
    assert stato.metti_in_pausa("a", None, ora=0) == 60
    assert stato.metti_in_pausa("a", None, ora=0) == 120
    stato.registra("a", 1, ora=0)
    assert stato.metti_in_pausa("a", None, ora=0) == 60


async def test_tutti_fermi_alza_nessun_fornitore():
    motore = MotoreAI([fornitore("a")], TrasportoFinto(errori={"a": ErroreFornitore(500)}))
    with pytest.raises(NessunFornitore):
        await motore.esegui("chat", "bassa", messaggi=[])


async def test_costo_e_conti():
    f = fornitore("a", costo_cent_milione=1000)
    motore = MotoreAI([f], TrasportoFinto())
    esito = await motore.esegui("chat", "bassa", messaggi=[])
    assert (esito.token_in, esito.token_out) == (10, 5)
    assert esito.costo_millesimi == 15
    assert motore.stato.riepilogo(f)["richieste_oggi"] == 1


async def test_controllo_chiavi():
    trasporto = TrasportoFinto()
    trasporto.chiavi_valide["b"] = False
    motore = MotoreAI([fornitore("a"), fornitore("b")], trasporto)
    assert await motore.controlla_chiavi() == {"a": True, "b": False}


def test_avviso_chiavi_solo_quando_cambia():
    from core.ai_router import avviso_chiavi

    testo, segnalati = avviso_chiavi({"a": True, "b": False}, ["a"], frozenset())
    assert "b: la chiave non risponde" in testo and "a: quota" in testo
    assert avviso_chiavi({"a": True, "b": False}, ["a"], segnalati)[0] is None
    testo, segnalati = avviso_chiavi({"a": True, "b": True}, [], segnalati)
    assert testo is None and segnalati == frozenset()


def test_solo_gratuiti_esclude_le_chiavi_a_pagamento_senza_costo():
    """Tetto raggiunto: una chiave a pagamento senza AI_COSTO non passa per gratuita (D13)."""
    pag = fornitore("pag", a_pagamento=True)
    assert scegli_fornitori([pag], "chat", "bassa", StatoFornitori(), usa_pagamento=True, solo_gratuiti=True) == []


async def test_richiesta_rifiutata_non_mette_in_pausa():
    """Un 400 dipende dal testo della persona: si passa oltre, ma il fornitore resta libero per gli altri."""
    a, b = fornitore("a"), fornitore("b")
    motore = MotoreAI([a, b], TrasportoFinto(errori={"a": ErroreFornitore(400)}))
    assert (await motore.esegui("chat", "bassa", messaggi=[])).fornitore == "b"
    assert not motore.stato.in_pausa("a")

"""
core/log_testi_servizio.py
==========================
Il testo dei messaggi dei canali registrati, cifrato e scritto a lotti (LOG-029, D122). I listener chiamano `accoda`
(solo memoria: mai una scrittura per messaggio); un giro periodico chiama `svuota` (una sola transazione) e `pota`
(tetto per server). A ogni sanzione `testi_per_caso` copia, cifrati, i messaggi dell'utente degli ultimi 3 giorni
nell'archivio del caso. Senza chiave nel `.env` non si salva nulla (mai in chiaro).
Funzioni coperte: SPEC §8.18 (LOG-029)
Dipende da: core/log_testi_logic.py, core/repositories/log_testi_repo.py
"""

from __future__ import annotations

import logging
from collections import defaultdict

from core import log_testi_logic as logica
from core.config import config
from core.repositories.log_testi_repo import RigaCifrata, log_testi_repo

logger = logging.getLogger("iyokai.log_testi")

MAX_IN_ATTESA_SERVER = 300  # righe in attesa di scrittura per server: oltre, si scartano (tetto per server)
MAX_IN_ATTESA = 5000  # righe in attesa in tutto
MAX_PER_LOTTO = 2000


def chiave() -> str:
    return logica.chiave_da_config(config)


def attivo() -> bool:
    """Senza chiave il testo non si salva: la risposta e' sempre «no»."""
    return bool(chiave())


class CodaTesti:
    def __init__(self) -> None:
        self._righe: list[RigaCifrata] = []
        self._per_server: dict[int, int] = defaultdict(int)
        self.scartate = 0

    def __len__(self) -> int:
        return len(self._righe)

    def accoda(self, guild_id: int, channel_id: int, message_id: int, user_id: int, evento: str, testo: str, allegati=()) -> bool:
        """Cifra e mette in coda. False se non si salva (senza chiave, evento strano, coda piena)."""
        k = chiave()
        if not k or evento not in logica.EVENTI:
            return False
        if len(self._righe) >= MAX_IN_ATTESA or self._per_server[guild_id] >= MAX_IN_ATTESA_SERVER:
            self.scartate += 1
            return False
        scheda = logica.scheda_allegati(allegati)
        if not testo and not scheda:
            return False
        cifrato = logica.cifra_riga(guild_id, message_id, user_id, evento, testo, scheda, k)
        self._righe.append(RigaCifrata(guild_id, channel_id, message_id, user_id, evento, cifrato))
        self._per_server[guild_id] += 1
        return True

    async def svuota(self) -> int:
        """Scrive tutto quel che e' in coda in poche transazioni. Se la scrittura fallisce il lotto resta in coda."""
        scritte = 0
        while self._righe:
            lotto = self._righe[:MAX_PER_LOTTO]
            try:
                await log_testi_repo.inserisci_lotto(lotto)
            except Exception:  # noqa: BLE001 - al giro dopo si riprova
                logger.warning("Testo dei messaggi: lotto non scritto, si riprova.", exc_info=True)
                break
            del self._righe[:len(lotto)]
            for r in lotto:
                self._per_server[r.guild_id] = max(0, self._per_server[r.guild_id] - 1)
            scritte += len(lotto)
        self._per_server = defaultdict(int, {g: n for g, n in self._per_server.items() if n})
        return scritte


coda = CodaTesti()


async def pota() -> int:
    return await log_testi_repo.pota_per_server(logica.MAX_RIGHE_SERVER)


async def testi_per_caso(guild_id: int, case_number: int, utente_id: int) -> tuple[str, int] | None:
    """(archivio cifrato, quanti messaggi) dei messaggi dell'utente degli ultimi 3 giorni; None se non c'e' nulla o manca la chiave."""
    k = chiave()
    if not k:
        return None
    await coda.svuota()  # i messaggi appena scritti devono entrare nella copia
    righe = await log_testi_repo.dell_utente(guild_id, utente_id, logica.GIORNI_ARCHIVIO, logica.MAX_MESSAGGI_ARCHIVIO)
    messaggi = []
    for r in righe:
        aperta = logica.apri_riga(r.cifrato, r.guild_id, r.message_id, r.user_id, r.evento, k)
        if aperta is None:
            continue
        messaggi.append(logica.MessaggioArchivio(r.creato, r.channel_id, r.message_id, r.evento, aperta[0], tuple(aperta[1])))
    if not messaggi:
        return None
    return logica.cifra_archivio(messaggi, guild_id, case_number, utente_id, k), len(messaggi)

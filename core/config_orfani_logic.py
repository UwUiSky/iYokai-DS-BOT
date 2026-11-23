"""
core/config_orfani_logic.py
===========================
Pulizia ritardata della configurazione (UTL-226, D111): quando un canale o un ruolo citato nelle impostazioni sparisce
si segna la data, senza toccare niente. Se dopo 7 giorni non è tornato (stesso ID, o rimappato da un ripristino che ha
cambiato le impostazioni) si toglie dalla configurazione, con una riga nello storico. Un server colpito da un nuke ha
così 7 giorni per ripristinare tutto. Un solo punto per il lavoro automatico, il comando e il pannello (D16).
Funzioni coperte: SPEC §20 (NF-05), catalogo #128 (UTL-226)
Dipende da: core/config_cleanup_logic.py, core/repositories/config_orfani_repo.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.config_cleanup_logic import orfani_confermati

GIORNI_ATTESA = 7
ATTESA = timedelta(days=GIORNI_ATTESA)


@dataclass
class RigaOrfano:
    tipo: str
    oggetto_id: int
    mancante_dal: datetime
    pulizia_il: datetime
    chiavi: list[str]


def _coppie(voci) -> set[tuple[str, int]]:
    return {(v.tipo, i) for v in voci for i in v.morti}


async def _aggiorna_segni(guild, repo, adesso: datetime):
    """
    Allinea i segni a ciò che manca ora. Restituisce `(voci, segni, settings)`, o None se il server non è caricato
    (senza ruoli non si sa cosa esiste: non si segna e non si toglie niente).
    """
    from core.database import db

    if guild is None or not guild.roles:
        return None
    settings = (await db.get_full_config(guild.id))["settings"]
    voci = await orfani_confermati(guild, settings)
    attuali = _coppie(voci)
    segni = await repo.elenco(guild.id)
    await repo.togli(guild.id, [k for k in segni if k not in attuali])  # tornato, o non più citato
    await repo.segna(guild.id, sorted(k for k in attuali if k not in segni), adesso)
    segni = {k: d for k, d in segni.items() if k in attuali}
    segni.update({k: adesso for k in attuali if k not in segni})
    return voci, segni, settings


async def anteprima(guild, repo, adesso: datetime | None = None) -> list[RigaOrfano]:
    """Cosa verrà pulito e quando. Aggiorna i segni ma non tocca la configurazione."""
    adesso = adesso or datetime.now(timezone.utc)
    stato = await _aggiorna_segni(guild, repo, adesso)
    if stato is None:
        return []
    voci, segni, _ = stato
    righe = [
        RigaOrfano(tipo, i, data, data + ATTESA, sorted(v.chiave for v in voci if v.tipo == tipo and i in v.morti))
        for (tipo, i), data in segni.items()
    ]
    return sorted(righe, key=lambda r: (r.pulizia_il, r.tipo, r.oggetto_id))


async def pulisci_scaduti(guild, repo, adesso: datetime | None = None, *, changed_by: int | None = None) -> int:
    """
    Aggiorna i segni e toglie dalla configurazione solo ciò che manca da almeno 7 giorni ed è ancora assente adesso.
    Restituisce quanti ID ha tolto. Mai prima dei 7 giorni.
    """
    from core.database import db

    adesso = adesso or datetime.now(timezone.utc)
    stato = await _aggiorna_segni(guild, repo, adesso)
    if stato is None:
        return 0
    voci, segni, settings = stato
    scaduti = {k for k, data in segni.items() if adesso - data >= ATTESA}
    tolti = 0
    for voce in voci:
        morti = [i for i in voce.morti if (voce.tipo, i) in scaduti]
        if not morti:
            continue
        valore = settings.get(voce.chiave)
        resta = [v for v in valore if v not in morti] if isinstance(valore, list) else None
        if resta:
            await db.set_guild_setting(guild.id, voce.chiave, resta, changed_by=changed_by)
        else:
            await db.remove_guild_setting(guild.id, voce.chiave, changed_by=changed_by)
        tolti += len(morti)
    await repo.togli(guild.id, sorted(scaduti))
    return tolti

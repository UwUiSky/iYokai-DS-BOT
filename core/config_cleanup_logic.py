"""
core/config_cleanup_logic.py
============================
Pulizia della configurazione di un server (CFG-019, #122): trova e toglie canali, categorie e ruoli
che non esistono più. Un solo punto per il comando e per il futuro pannello (D16).
Funzioni coperte: SPEC §20 (NF-05), catalogo #122
Dipende da: core/database.py (`get_full_config`, `set_guild_setting`, `remove_guild_setting`)

Regole: si guardano solo le chiavi note (che nome portano: canale, categoria o ruolo). Una voce si toglie solo se
Discord conferma che non c'è: se il server non è in memoria (guild None) non si tocca niente. Ogni modifica
finisce nello storico, quindi `/admin config rollback` la annulla.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIPO_CANALE = "canale"
TIPO_RUOLO = "ruolo"

_FINALI_CANALE = ("channel_id", "channel_ids", "category_id")
_FINALI_RUOLO = ("role_id", "role_ids")
_CHIAVI_EXTRA = {
    "policy_canali_ok": TIPO_CANALE,
    "policy_canali_no": TIPO_CANALE,
    "policy_ignora_ruoli": TIPO_RUOLO,
}


def tipo_della_chiave(chiave: str) -> str | None:
    """«canale» o «ruolo» se la chiave contiene ID di quel tipo, altrimenti None (utenti, numeri, testi)."""
    if chiave in _CHIAVI_EXTRA:
        return _CHIAVI_EXTRA[chiave]
    if chiave.endswith(_FINALI_CANALE):
        return TIPO_CANALE
    if chiave.endswith(_FINALI_RUOLO):
        return TIPO_RUOLO
    return None


@dataclass
class VocePulizia:
    chiave: str
    tipo: str
    morti: list[int]
    nuovo: object | None  # None = la chiave sparisce


@dataclass
class EsitoPulizia:
    voci: list[VocePulizia] = field(default_factory=list)
    applicata: bool = False

    @property
    def totale(self) -> int:
        return sum(len(v.morti) for v in self.voci)


def trova_orfani(settings: dict, *, canale_esiste, ruolo_esiste) -> list[VocePulizia]:
    """Le voci da togliere. `canale_esiste(id)` e `ruolo_esiste(id)` rispondono True/False."""
    voci: list[VocePulizia] = []
    for chiave, valore in sorted(settings.items()):
        tipo = tipo_della_chiave(chiave)
        if tipo is None or valore is None:
            continue
        esiste = canale_esiste if tipo == TIPO_CANALE else ruolo_esiste
        if isinstance(valore, list):
            ids = [v for v in valore if isinstance(v, int) and not isinstance(v, bool)]
            morti = [v for v in ids if not esiste(v)]
            if morti:
                resta = [v for v in valore if v not in morti]
                voci.append(VocePulizia(chiave, tipo, morti, resta or None))
        elif isinstance(valore, int) and not isinstance(valore, bool) and not esiste(valore):
            voci.append(VocePulizia(chiave, tipo, [valore], None))
    return voci


async def pulisci_configurazione(guild, *, applica: bool, changed_by: int | None) -> EsitoPulizia:
    """
    Anteprima (`applica=False`) o pulizia vera della configurazione di `guild` (un `discord.Guild`).
    Con `guild=None`, o con un server non ancora caricato (nessun ruolo, nemmeno @everyone), non fa niente.
    """
    from core.database import db

    if guild is None or not guild.roles:
        return EsitoPulizia()
    config = await db.get_full_config(guild.id)
    voci = trova_orfani(
        config["settings"],
        canale_esiste=lambda i: guild.get_channel_or_thread(i) is not None,
        ruolo_esiste=lambda i: guild.get_role(i) is not None,
    )
    if applica:
        for voce in voci:
            if voce.nuovo is None:
                await db.remove_guild_setting(guild.id, voce.chiave, changed_by=changed_by)
            else:
                await db.set_guild_setting(guild.id, voce.chiave, voce.nuovo, changed_by=changed_by)
    return EsitoPulizia(voci=voci, applicata=applica)

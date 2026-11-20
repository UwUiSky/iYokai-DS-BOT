"""
core/config_trasloco.py
=======================
Portare la configurazione di un server su un altro (CFG-043, #122). L'esportazione aggiunge, per ogni canale e
ruolo citato nelle impostazioni, il suo nome (`riferimenti`). L'importazione non scrive mai ID che non esistono nel
server di arrivo: un ID che c'è (stesso server) resta, altrimenti si cerca un solo canale o ruolo con lo stesso nome e
tipo; se non c'è, o ce ne sono due, la voce si toglie e viene contata. Così un file non porta ID di altri server.
Funzioni coperte: SPEC §20 (NF-05), catalogo #122 (CFG-043)
Dipende da: core/config_cleanup_logic.py (quali chiavi contengono canali e ruoli)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import discord

from core.config_cleanup_logic import TIPO_CANALE, TIPO_RUOLO, tipo_della_chiave

CHIAVE_RICHIESTI = "policy_ruoli_richiesti"
MAX_RIFERIMENTI = 2000
MAX_NOME = 100


class ServerNonPronto(RuntimeError):
    """Il server non è in memoria: senza canali e ruoli non si può dire cosa esiste."""


@dataclass
class EsitoRimappa:
    settings: dict
    rimappati: int = 0
    tolti: int = 0
    chiavi_tolte: list[str] = field(default_factory=list)


def _ids(chiave: str, valore) -> list[tuple[int, str]]:
    """Gli ID di una voce con il loro tipo."""
    if chiave == CHIAVE_RICHIESTI and isinstance(valore, dict):
        return [(i, TIPO_RUOLO) for ids in valore.values() if isinstance(ids, list) for i in ids if _e_id(i)]
    tipo = tipo_della_chiave(chiave)
    if tipo is None or valore is None:
        return []
    elementi = valore if isinstance(valore, list) else [valore]
    return [(i, tipo) for i in elementi if _e_id(i)]


def _e_id(i) -> bool:
    return isinstance(i, int) and not isinstance(i, bool) and i > 0


def raccogli_riferimenti(settings: dict, guild: discord.Guild) -> dict[str, dict]:
    """Per l'esportazione: `{id: {"tipo", "nome"}}` dei canali e ruoli che esistono ancora nel server."""
    trovati: dict[str, dict] = {}
    for chiave, valore in settings.items():
        for i, tipo in _ids(chiave, valore):
            oggetto = guild.get_role(i) if tipo == TIPO_RUOLO else guild.get_channel(i)
            if oggetto is not None and len(trovati) < MAX_RIFERIMENTI:
                trovati[str(i)] = {"tipo": tipo, "nome": str(oggetto.name)[:MAX_NOME]}
    return trovati


def errore_riferimenti(riferimenti) -> str | None:
    """Controlla il campo `riferimenti` di un file importato. None = valido (o assente)."""
    if riferimenti is None:
        return None
    if not isinstance(riferimenti, dict) or len(riferimenti) > MAX_RIFERIMENTI:
        return "`riferimenti` deve essere un elenco ID → nome (al massimo 2000 voci)."
    for chiave, voce in riferimenti.items():
        if not (isinstance(chiave, str) and chiave.isascii() and chiave.isdigit() and 0 < int(chiave) < 2**63):
            return "`riferimenti` contiene un ID non valido."
        if not (
            isinstance(voce, dict)
            and voce.get("tipo") in (TIPO_CANALE, TIPO_RUOLO)
            and isinstance(voce.get("nome"), str)
            and 0 < len(voce["nome"]) <= MAX_NOME
        ):
            return "`riferimenti` contiene una voce non valida."
    return None


def _unico_per_nome(guild: discord.Guild, tipo: str, nome: str):
    candidati = guild.roles if tipo == TIPO_RUOLO else guild.channels
    uguali = [c for c in candidati if c.name == nome and not (tipo == TIPO_RUOLO and c.id == guild.id)]
    return uguali[0].id if len(uguali) == 1 else None


def rimappa_impostazioni(guild: discord.Guild, settings: dict, riferimenti: dict | None) -> EsitoRimappa:
    """
    Le impostazioni da scrivere nel server `guild`: solo ID che esistono qui. Non modifica `settings`.
    @everyone (l'ID del server) non è mai un ruolo valido per le impostazioni.
    """
    riferimenti = riferimenti or {}
    esito = EsitoRimappa(settings={})
    cache: dict[tuple[int, str], int | None] = {}

    def risolvi(i: int, tipo: str) -> int | None:
        if not guild.roles:  # senza ruoli in memoria (c'è sempre @everyone) non si può dire cosa esiste
            raise ServerNonPronto(guild.id)
        chiave = (i, tipo)
        if chiave not in cache:
            esiste = (
                (guild.get_role(i) is not None and i != guild.id) if tipo == TIPO_RUOLO else guild.get_channel(i) is not None
            )
            if esiste:
                cache[chiave] = i
            else:
                voce = riferimenti.get(str(i))
                cache[chiave] = _unico_per_nome(guild, tipo, voce["nome"]) if voce and voce["tipo"] == tipo else None
        trovato = cache[chiave]
        if trovato is None:
            esito.tolti += 1
        elif trovato != i:
            esito.rimappati += 1
        return trovato

    for chiave, valore in settings.items():
        if chiave == CHIAVE_RICHIESTI and isinstance(valore, dict):
            nuova = {}
            for percorso, ids in valore.items():
                restano = [r for r in (risolvi(i, TIPO_RUOLO) for i in ids) if r is not None]
                if restano:
                    nuova[percorso] = list(dict.fromkeys(restano))
            if nuova:
                esito.settings[chiave] = nuova
            else:
                esito.chiavi_tolte.append(chiave)
            continue
        tipo = tipo_della_chiave(chiave)
        if tipo is None or valore is None:
            esito.settings[chiave] = valore
        elif isinstance(valore, list):
            if not valore:  # un elenco vuoto non cita niente: resta com'è
                esito.settings[chiave] = valore
                continue
            restano = [r for r in (risolvi(i, tipo) for i in valore) if r is not None]
            if restano:
                esito.settings[chiave] = list(dict.fromkeys(restano))
            else:
                esito.chiavi_tolte.append(chiave)
        else:
            trovato = risolvi(valore, tipo)
            if trovato is None:
                esito.chiavi_tolte.append(chiave)
            else:
                esito.settings[chiave] = trovato
    return esito

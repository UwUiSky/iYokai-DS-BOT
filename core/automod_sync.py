"""
core/automod_sync.py
======================
Logica di sincronizzazione tra ciò che iYokai vuole configurare
nell'AutoMod nativo di Discord e ciò che esiste già su un server —
come funzioni PURE, sullo stesso principio di core/permissions.py:
niente oggetti discord.py qui dentro, solo dataclass con liste di
stringhe. Il cog (cogs/automod/automod.py) fa da ponte, leggendo le
regole vere da Discord e convertendole in ExistingRule prima di
chiamare compute_sync_plan().

Perché "ibrido" e non "il bot crea le sue regole e basta"
--------------------------------------------------------------
L'obiettivo (deciso in fase di progettazione, vedi PROGRESS.md §
Decisioni prese) è: se una regola con lo stesso nome esiste già,
AGGIORNARLA senza MAI cancellare ciò che un amministratore ha
aggiunto a mano dal pannello Discord a quella stessa regola — ma
SENZA impedire a iYokai di far sparire una parola che era sua e che
l'admin ha rimosso dalla configurazione (es. /automod
badword-remove). Le due cose sembrano in tensione ("non cancellare
mai" vs "un comando di rimozione deve funzionare davvero"), e si
risolvono solo distinguendo la PROVENIENZA di ogni parola:

  contenuto finale = (ciò che è nella regola Discord MA NON risulta
                       scritto da iYokai nell'ultimo sync noto)
                      ∪ (ciò che iYokai vuole ORA)

La prima parte, calcolata da `_admin_added()`, è "presumibilmente
aggiunta dall'admin" — e infatti resta per sempre, sync dopo sync.
La seconda parte riflette lo stato attuale della configurazione
salvata: se una parola ne esce, esce anche dalla regola finale
(a meno che non sia stata anche aggiunta a mano dall'admin, nel
qual caso resta comunque, correttamente, come sua).

Limiti reali di Discord rispettati qui
------------------------------------------
- Un rule di tipo KEYWORD accetta al massimo 1000 parole nel filtro
- Al massimo ~10 pattern regex per rule
Se il merge supera questi limiti, il risultato viene TRONCATO (non
si solleva un errore): il chiamante riceve un flag `truncated=True`
per poterlo segnalare all'amministratore, invece di far fallire
silenziosamente la sincronizzazione.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


DEFAULT_MAX_KEYWORDS = 1000
DEFAULT_MAX_REGEX = 10

# Prefisso con cui iYokai marca le regole che gestisce lui stesso.
# Solo le regole con questo prefisso nel nome vengono mai aggiornate:
# qualunque altra regola AutoMod presente sul server (creata a mano
# dall'admin, con un nome diverso) non viene MAI toccata.
IYOKAI_RULE_PREFIX = "iYokai — "


class SyncActionType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    SKIP = "skip"  # la regola esiste già ed è già identica: nessuna chiamata API
    DELETE = "delete"  # non resta più nulla da tenere (né admin né iYokai): la regola va rimossa


@dataclass(frozen=True)
class ExistingRule:
    """Rappresentazione minimale di una regola AutoMod già presente
    su Discord, come la legge il cog da guild.fetch_automod_rules()."""
    name: str
    keywords: tuple[str, ...] = ()
    regex_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class DesiredRule:
    """
    Una regola che iYokai vuole che esista, con il contenuto che
    vorrebbe imporre.

    `previously_synced_*` è la parte che rende possibile distinguere
    "parole che l'admin ha aggiunto a mano dal pannello Discord" da
    "parole che iYokai stesso aveva scritto in un sync precedente e
    che ORA non vuole più" (es. l'admin ha fatto /automod
    badword-remove). Senza questa distinzione, un merge che fa solo
    "esistenti ∪ nuove" non potrebbe mai far sparire una parola: la
    rimozione dalla configurazione salvata non avrebbe alcun effetto
    sulla regola Discord reale, contraddicendo il comando stesso.
    Se lasciato vuoto (default, e caso di una regola mai tracciata
    prima), TUTTO il contenuto esistente viene trattato come
    "aggiunto dall'admin" — la scelta più prudente quando non si sa
    la provenienza di una parola.
    """
    name: str
    keywords: tuple[str, ...] = ()
    regex_patterns: tuple[str, ...] = ()
    previously_synced_keywords: tuple[str, ...] = ()
    previously_synced_regex: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyncAction:
    action: SyncActionType
    name: str
    final_keywords: tuple[str, ...]
    final_regex: tuple[str, ...]
    truncated: bool = False


def _merge_preserving_order(existing: tuple[str, ...], new: tuple[str, ...]) -> list[str]:
    """
    Unisce due liste evitando duplicati, mantenendo per primi gli
    elementi esistenti (così se un domani l'ordine avesse rilevanza
    per l'admin che ha guardato la lista in Discord, non viene
    stravolto ad ogni sync) e aggiungendo in coda solo i nuovi che
    non erano già presenti.
    """
    result = list(existing)
    existing_set = set(existing)
    for item in new:
        if item not in existing_set:
            result.append(item)
            existing_set.add(item)
    return result


def _admin_added(existing: tuple[str, ...], previously_synced: tuple[str, ...]) -> tuple[str, ...]:
    """
    Isola, tra il contenuto ATTUALE della regola Discord, ciò che non
    risulta scritto da iYokai nell'ultimo sync noto — quindi
    presumibilmente aggiunto a mano dall'admin dal pannello Discord.
    Se `previously_synced` è vuoto (prima volta che questa regola
    viene tracciata), tutto il contenuto esistente viene considerato
    "dell'admin": è la scelta prudente quando non si conosce la
    provenienza.
    """
    if not previously_synced:
        return existing
    previously_synced_set = set(previously_synced)
    return tuple(item for item in existing if item not in previously_synced_set)


def compute_sync_plan(
    existing_rules: list[ExistingRule],
    desired_rules: list[DesiredRule],
    max_keywords: int = DEFAULT_MAX_KEYWORDS,
    max_regex: int = DEFAULT_MAX_REGEX,
) -> list[SyncAction]:
    """
    Calcola cosa andrebbe fatto per allineare `existing_rules` a
    `desired_rules`. Non esegue nessuna chiamata API: restituisce
    solo il PIANO. Il cog lo esegue davvero (create/edit su Discord).

    Le regole desiderate SENZA contenuto (keywords e regex_patterns
    entrambi vuoti) vengono ignorate: Discord rifiuta una regola
    KEYWORD senza filtro, e non avrebbe senso crearne una vuota.
    """
    existing_by_name = {rule.name: rule for rule in existing_rules}
    actions: list[SyncAction] = []

    for desired in desired_rules:
        existing = existing_by_name.get(desired.name)

        if existing is None:
            if not desired.keywords and not desired.regex_patterns:
                # Nessun contenuto e nessuna regola da riconciliare:
                # non c'è letteralmente nulla da fare.
                continue

            keywords = list(desired.keywords)
            regex = list(desired.regex_patterns)
            truncated = len(keywords) > max_keywords or len(regex) > max_regex
            actions.append(
                SyncAction(
                    action=SyncActionType.CREATE,
                    name=desired.name,
                    final_keywords=tuple(keywords[:max_keywords]),
                    final_regex=tuple(regex[:max_regex]),
                    truncated=truncated,
                )
            )
            continue

        # La regola esiste già: va SEMPRE ricalcolata, anche quando
        # `desired` è vuoto — è esattamente il caso in cui iYokai ha
        # rimosso tutte le sue parole ma potrebbero restarne di
        # dell'admin da preservare (o, se non ne restano, la regola
        # va eliminata: vedi sotto).
        merged_keywords = _merge_preserving_order(
            _admin_added(existing.keywords, desired.previously_synced_keywords),
            desired.keywords,
        )
        merged_regex = _merge_preserving_order(
            _admin_added(existing.regex_patterns, desired.previously_synced_regex),
            desired.regex_patterns,
        )

        truncated = len(merged_keywords) > max_keywords or len(merged_regex) > max_regex
        final_keywords = tuple(merged_keywords[:max_keywords])
        final_regex = tuple(merged_regex[:max_regex])

        if not final_keywords and not final_regex:
            # Non resta più nulla da tenere in questa regola (né
            # dell'admin né di iYokai): Discord non permette una
            # regola keyword vuota, quindi va eliminata, non
            # aggiornata a vuoto (l'API rifiuterebbe la richiesta).
            actions.append(
                SyncAction(
                    action=SyncActionType.DELETE,
                    name=desired.name,
                    final_keywords=(),
                    final_regex=(),
                    truncated=False,
                )
            )
        elif final_keywords == existing.keywords and final_regex == existing.regex_patterns:
            # Nessuna parola/pattern nuovo da aggiungere: evitiamo
            # una chiamata API inutile.
            actions.append(
                SyncAction(
                    action=SyncActionType.SKIP,
                    name=desired.name,
                    final_keywords=final_keywords,
                    final_regex=final_regex,
                    truncated=truncated,
                )
            )
        else:
            actions.append(
                SyncAction(
                    action=SyncActionType.UPDATE,
                    name=desired.name,
                    final_keywords=final_keywords,
                    final_regex=final_regex,
                    truncated=truncated,
                )
            )

    return actions

"""
core/activity_stats_logic.py
============================
Statistiche di attività (NF-25, #96): aggregazione in memoria per giorno,
sessioni vocali, esclusioni e calcolo dei ruoli per attività.
Niente Discord e niente database: il cog legge gli eventi, qui si somma;
il repository scrive un lotto ogni minuto (costo basso, nessuna riga per
messaggio). Funzioni coperte: SPEC §23 (NF-25); STA-006 (stato della voce), STA-025..027 (filtri), STA-032 (due condizioni)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

MAX_CHIAVI_BUFFER = 20000      # oltre, il cog scrive subito il lotto
MAX_SECONDI_SESSIONE = 86400   # una sessione non vale più di un giorno tra due controlli
MAX_REGOLE_PER_SERVER = 10
MAX_CAMBI_PER_GIRO = 25        # ruoli dati/tolti per regola a ogni giro (limiti di Discord)
GIORNI_CONSERVAZIONE = 90

METRICHE = ("messages", "voice_minutes")


def _utc(quando: datetime) -> datetime:
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


class ActivityBuffer:
    """Somme in memoria: [messaggi, secondi_vocale] per canale, membro e ora."""

    def __init__(self) -> None:
        self._canali: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
        self._membri: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
        self._ore: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
        self._stati: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0])  # STA-006: muto, sordo, AFK

    @property
    def pieno(self) -> bool:
        return len(self._canali) + len(self._membri) + len(self._ore) >= MAX_CHIAVI_BUFFER

    def _somma(self, guild_id: int, canale_id: int, utente_id: int, quando: datetime, i: int, n: int) -> None:
        quando = _utc(quando)
        giorno = quando.date()
        self._canali[(guild_id, giorno, canale_id)][i] += n
        self._membri[(guild_id, giorno, utente_id)][i] += n
        self._ore[(guild_id, giorno, quando.hour)][i] += n

    def add_message(self, guild_id: int, canale_id: int, utente_id: int, quando: datetime) -> None:
        self._somma(guild_id, canale_id, utente_id, quando, 0, 1)

    def add_voice(self, guild_id: int, canale_id: int, utente_id: int, secondi: int, quando: datetime) -> None:
        if secondi > 0:
            self._somma(guild_id, canale_id, utente_id, quando, 1, int(secondi))

    def add_voice_state(self, guild_id: int, utente_id: int, secondi: int, quando: datetime, muto: bool, sordo: bool, afk: bool) -> None:
        """STA-006: ripartisce i secondi per stato (un sottoinsieme del tempo in vocale; l'AFK sta a parte)."""
        if secondi <= 0 or not (muto or sordo or afk):
            return
        riga = self._stati[(guild_id, _utc(quando).date(), utente_id)]
        if afk:
            riga[2] += int(secondi)
            return
        if muto:
            riga[0] += int(secondi)
        if sordo:
            riga[1] += int(secondi)

    def drain_stati(self) -> dict:
        out = dict(self._stati)
        self._stati.clear()
        return out

    def restore_stati(self, stati: dict) -> None:
        for chiave, (m, d, a) in stati.items():
            riga = self._stati[chiave]
            riga[0] += m
            riga[1] += d
            riga[2] += a

    def restore(self, canali: dict, membri: dict, ore: dict) -> None:
        """Rimette in coda un lotto che non è stato scritto."""
        for mio, altro in ((self._canali, canali), (self._membri, membri), (self._ore, ore)):
            for chiave, (m, v) in altro.items():
                mio[chiave][0] += m
                mio[chiave][1] += v

    def drain(self) -> tuple[dict, dict, dict]:
        out = (dict(self._canali), dict(self._membri), dict(self._ore))
        self._canali.clear()
        self._membri.clear()
        self._ore.clear()
        return out


class VoiceTracker:
    """Chi è in vocale e da quando. `tick` accredita il tempo passato e riparte da adesso.

    Ogni sessione ricorda lo stato (muto, sordo, canale AFK): il tempo accreditato si ripartisce
    per stato (STA-006) in `stati`, che il cog svuota con `preleva_stati`.
    """

    def __init__(self) -> None:
        self._sessioni: dict[tuple[int, int], list] = {}
        self.stati: list[tuple[int, int, int, bool, bool, bool]] = []

    def entra(self, guild_id: int, canale_id: int, utente_id: int, quando: datetime,
              muto: bool = False, sordo: bool = False, afk: bool = False) -> None:
        self._sessioni[(guild_id, utente_id)] = [canale_id, _utc(quando), muto, sordo, afk]

    def esce(self, guild_id: int, utente_id: int, quando: datetime) -> list[tuple[int, int, int, int]]:
        sessione = self._sessioni.pop((guild_id, utente_id), None)
        if sessione is None:
            return []
        return self._credito(guild_id, utente_id, sessione, _utc(quando))

    def cambia_stato(self, guild_id: int, utente_id: int, quando: datetime, muto: bool, sordo: bool) -> list[tuple[int, int, int, int]]:
        """STA-006: chiude la fetta di tempo con lo stato di prima e riparte con quello nuovo."""
        sessione = self._sessioni.get((guild_id, utente_id))
        if sessione is None or (sessione[2], sessione[3]) == (muto, sordo):
            return []
        crediti = self._credito(guild_id, utente_id, sessione, _utc(quando))
        sessione[2], sessione[3] = muto, sordo
        return crediti

    def preleva_stati(self) -> list[tuple[int, int, int, bool, bool, bool]]:
        fette, self.stati = self.stati, []
        return fette

    def _credito(self, guild_id, utente_id, sessione, ora) -> list[tuple[int, int, int, int]]:
        secondi = min(int((ora - sessione[1]).total_seconds()), MAX_SECONDI_SESSIONE)
        sessione[1] = ora
        if secondi <= 0:
            return []
        if sessione[2] or sessione[3] or sessione[4]:
            self.stati.append((guild_id, utente_id, secondi, sessione[2], sessione[3], sessione[4]))
        if sessione[4]:  # canale AFK: non conta come tempo in vocale
            return []
        return [(guild_id, utente_id, sessione[0], secondi)]

    def tick(self, quando: datetime) -> list[tuple[int, int, int, int]]:
        ora = _utc(quando)
        crediti: list[tuple[int, int, int, int]] = []
        for (guild_id, utente_id), sessione in self._sessioni.items():
            crediti += self._credito(guild_id, utente_id, sessione, ora)
        return crediti

    def __len__(self) -> int:
        return len(self._sessioni)


def escluso(canale_id: int, ruoli_utente, canali_ignorati, ruoli_ignorati) -> bool:
    return canale_id in set(canali_ignorati) or bool(set(ruoli_utente) & set(ruoli_ignorati))


def conta_secondo_i_filtri(imp, utente_id: int, ruoli_utente, canali_ids) -> bool:
    """STA-025, 026, 027: True se questo messaggio o questa sessione vocale entra nelle statistiche.

    `canali_ids` = il canale, il suo thread-padre e la sua categoria (un elenco con una categoria vale per
    tutti i suoi canali). Modo «escludi»: fuori chi è nell'elenco. Modo «solo»: dentro solo chi è
    nell'elenco (un elenco vuoto non limita nulla). I membri esclusi non contano mai.
    """
    if utente_id in set(getattr(imp, "ignored_members", ()) or ()):
        return False
    if (set(getattr(imp, "sempre_esclusi", ()) or ())) & (set(canali_ids) | set(ruoli_utente)):
        return False  # D127: canali e ruolo dello shadowban
    for elenco, modo, ids in (
        (imp.ignored_channels, getattr(imp, "channel_mode", "escludi"), set(canali_ids)),
        (imp.ignored_roles, getattr(imp, "role_mode", "escludi"), set(ruoli_utente)),
    ):
        if not elenco:
            continue
        trovato = bool(ids & set(elenco))
        if (modo == "escludi" and trovato) or (modo == "solo" and not trovato):
            return False
    return True


def canali_del_messaggio(canale) -> set[int]:
    """Il canale, il padre (se è un thread) e la categoria: gli ID che un filtro può nominare."""
    ids = {canale.id}
    for attributo in ("parent_id", "category_id"):
        valore = getattr(canale, attributo, None)
        if isinstance(valore, int):
            ids.add(valore)
    padre = getattr(canale, "parent", None)
    categoria = getattr(padre, "category_id", None)
    if isinstance(categoria, int):
        ids.add(categoria)
    return ids


def regola_con_due_condizioni(a: set[int], b: set[int] | None, combine: str) -> set[int]:
    """STA-032: chi passa la prima soglia, la seconda, o entrambe (`e` = tutte e due, `o` = una delle due)."""
    if b is None:
        return a
    return a & b if combine == "e" else a | b


def _finestra(ordinati: list[int], limite: int, giro: int) -> list[int]:
    """`limite` elementi a partire da una posizione che avanza a ogni giro (e ricomincia da capo)."""
    if len(ordinati) <= limite:
        return ordinati
    inizio = (giro * limite) % len(ordinati)
    return (ordinati + ordinati)[inizio : inizio + limite]


def ruoli_da_aggiornare(
    eleggibili: set[int], possessori: set[int], rimuovi: bool, limite: int = MAX_CAMBI_PER_GIRO, giro: int = 0
) -> tuple[set[int], set[int]]:
    """(chi riceve il ruolo, a chi si toglie): al massimo `limite` per parte.

    `giro` fa ruotare la finestra: chi non si riesce a cambiare (gerarchia, errore di Discord)
    non occupa per sempre i primi posti e non blocca gli altri.
    """
    dare = _finestra(sorted(eleggibili - possessori), limite, giro)
    togliere = _finestra(sorted(possessori - eleggibili), limite, giro) if rimuovi else []
    return set(dare), set(togliere)


def per_giorno_settimana(per_giorno: dict[date, int]) -> list[int]:
    """Somma per giorno della settimana, lunedì = posizione 0."""
    totali = [0] * 7
    for giorno, valore in per_giorno.items():
        totali[giorno.weekday()] += valore
    return totali

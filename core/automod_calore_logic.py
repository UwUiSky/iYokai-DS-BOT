"""
core/automod_calore_logic.py
============================
Calore delle regole AutoMod: ogni regola che scatta dà punti a chi l'ha fatta scattare, i punti calano da soli
(calo lineare, calcolato quando si legge, nessun ciclo) e un canale fermo da tempo pesa di più. Alla soglia scattano
le azioni scelte dal server. Valori in memoria con tetto. Logica pura, niente Discord.
Funzioni coperte: SPEC §6 (AMD-068, 069, 072)
"""

from __future__ import annotations

from core.automod_advanced_logic import CaloreConfig
from core.automod_regole_logic import Azione
from core.bounded_cache import BoundedCache

TETTO_UTENTI = 20_000
TETTO_CANALI = 20_000
MAX_SOGLIA = 1000
MAX_CALO = 100
MAX_FERMO_MINUTI = 1440
MAX_FERMO_PESO = 10
MAX_TIMEOUT_S = 28 * 24 * 3600


class Termometro:
    """Il calore di ogni persona: (server, utente) -> (valore, ora dell'ultimo calcolo)."""

    def __init__(self, tetto: int = TETTO_UTENTI) -> None:
        self._dati: BoundedCache = BoundedCache(tetto)

    def __len__(self) -> int:
        return len(self._dati)

    def valore(self, guild_id: int, user_id: int, adesso: float, calo_per_minuto: int) -> float:
        voce = self._dati.get((guild_id, user_id))
        if voce is None:
            return 0.0
        valore, ora = voce
        return max(0.0, valore - calo_per_minuto * max(0.0, adesso - ora) / 60)

    def aggiungi(self, guild_id: int, user_id: int, punti: float, adesso: float, calo_per_minuto: int) -> float:
        nuovo = self.valore(guild_id, user_id, adesso, calo_per_minuto) + punti
        self._dati.set((guild_id, user_id), (nuovo, adesso))
        return nuovo

    def azzera(self, guild_id: int, user_id: int) -> None:
        self._dati.delete((guild_id, user_id))


class CanaliFermi:
    """L'ora dell'ultimo messaggio di ogni canale: (server, canale) -> ora."""

    def __init__(self, tetto: int = TETTO_CANALI) -> None:
        self._dati: BoundedCache = BoundedCache(tetto)

    def segna(self, guild_id: int, canale_id: int, adesso: float) -> float | None:
        """Registra il messaggio di adesso e dà l'ora di quello di prima (None se il canale non si era mai visto)."""
        prima = self._dati.get((guild_id, canale_id))
        self._dati.set((guild_id, canale_id), adesso)
        return prima


def punti(calore_regola: int, c: CaloreConfig, ultimo: float | None, adesso: float) -> float:
    """Punti di una violazione: quelli della regola, per il peso se il canale era fermo da `fermo_minuti`."""
    if c.fermo_minuti > 0 and ultimo is not None and adesso - ultimo >= c.fermo_minuti * 60:
        return calore_regola * c.fermo_peso
    return calore_regola


def azioni_calore(c: CaloreConfig) -> tuple[Azione, ...]:
    """Cosa succede alla soglia: avviso, timeout (se scelto) e riga nel log."""
    fuori = []
    if c.warn:
        fuori.append(Azione("warn"))
    if c.timeout_secondi > 0:
        fuori.append(Azione("timeout", (("secondi", c.timeout_secondi),)))
    fuori.append(Azione("log"))
    return tuple(fuori)


def _intero(valore, minimo: int, massimo: int, difetto: int) -> int:
    if isinstance(valore, bool) or not isinstance(valore, int) or not minimo <= valore <= massimo:
        return difetto
    return valore


def config_da_json(dati) -> CaloreConfig:
    """Dal JSON del server: un valore storto torna a quello di base, mai un errore."""
    b = CaloreConfig()
    if not isinstance(dati, dict):
        return b
    return CaloreConfig(
        attivo=dati.get("attivo") is True,
        soglia=_intero(dati.get("soglia"), 1, MAX_SOGLIA, b.soglia),
        calo_per_minuto=_intero(dati.get("calo_per_minuto"), 0, MAX_CALO, b.calo_per_minuto),
        fermo_minuti=_intero(dati.get("fermo_minuti"), 0, MAX_FERMO_MINUTI, b.fermo_minuti),
        fermo_peso=_intero(dati.get("fermo_peso"), 1, MAX_FERMO_PESO, b.fermo_peso),
        timeout_secondi=_intero(dati.get("timeout_secondi"), 0, MAX_TIMEOUT_S, b.timeout_secondi),
        warn=dati.get("warn") is not False,
    )


def config_a_json(c: CaloreConfig) -> dict:
    return {"attivo": c.attivo, "soglia": c.soglia, "calo_per_minuto": c.calo_per_minuto, "fermo_minuti": c.fermo_minuti,
            "fermo_peso": c.fermo_peso, "timeout_secondi": c.timeout_secondi, "warn": c.warn}


def controlla(c: CaloreConfig) -> None:
    """Un valore fuori dai limiti è un errore (ValueError): rileggerlo lo riporterebbe in silenzio a quello di base."""
    if config_da_json(config_a_json(c)) != c:
        raise ValueError("impostazioni del calore fuori dai limiti")

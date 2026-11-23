"""
core/piani.py
=============
I piani del bot (D59): livelli Gratuito, Premium, Ultra, VIP. Un solo punto decide il livello di un server o di
un utente (`livello_server`, `livello_utente`: massimo tra tutte le fonti), un solo punto legge i limiti numerici
per livello (`limite_server`, `limite_di`), un solo punto scrive concessioni, limiti, prezzi e sconti (D16).
Fonti: abbonamento mensile, annuale o a vita (concessioni), boost di un server dell'owner, Patreon, posto premium,
tutte le fonti premium di `core/premium.py`, e la chiave API propria (VIP, `core/ai_chiavi_proprie.py`).
I prezzi li sceglie l'owner (nessun valore nel codice): il bot li mostra e non incassa niente.
Funzioni coperte: CFG-040, CFG-041, D59
Dipende da: core/migrations/0910_piani.sql
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

GRATUITO = "gratuito"
PREMIUM = "premium"
ULTRA = "ultra"
VIP = "vip"
LIVELLI = (GRATUITO, PREMIUM, ULTRA, VIP)
LIVELLI_A_PAGAMENTO = (PREMIUM, ULTRA, VIP)
ETICHETTE = {GRATUITO: "gratuito", PREMIUM: "Premium", ULTRA: "Ultra", VIP: "VIP"}
PERIODI = ("mensile", "annuale", "a_vita")
FONTI = ("mensile", "annuale", "a_vita", "boost", "patreon", "manuale")
GIORNI_PERIODO = {"mensile": 30, "annuale": 365, "a_vita": None}
GIORNI_BOOST = 3  # un boost si rilegge a ogni controllo: la concessione `boost` non si salva, qui solo la durata di grazia

# chiave: (descrizione breve, valori predefiniti per gratuito, premium, ultra, vip)
# I valori predefiniti sono quelli del codice di oggi; l'owner li cambia con `/owner premium piano`.
LIMITI: dict[str, tuple[str, tuple[int, int, int, int]]] = {
    "backup_copie": ("Copie di backup conservate", (10, 10, 10, 10)),
    "programmati_serie": ("Messaggi programmati che si ripetono", (25, 25, 25, 25)),
    "pannelli_ticket": ("Pannelli ticket", (25, 25, 25, 25)),
    "everyone_al_giorno": ("Invii programmati con @everyone o @here al giorno", (2, 2, 2, 2)),
}
MAX_VALORE = 1_000_000


class PianoNonValido(ValueError):
    """Livello, periodo, fonte, limite o valore sconosciuti o fuori misura."""


def rango(livello: str) -> int:
    return LIVELLI.index(livello) if livello in LIVELLI else 0


def livello_massimo(*livelli: str) -> str:
    return max(livelli or (GRATUITO,), key=rango)


def basta(posseduto: str, richiesto: str) -> bool:
    """Il livello posseduto copre quello richiesto?"""
    return rango(posseduto) >= rango(richiesto)


def _pool():
    from core.database import db

    return db.pool


def _controlla_id(valore: int, nome: str) -> None:
    if not isinstance(valore, int) or isinstance(valore, bool) or valore <= 0:
        raise PianoNonValido(nome)


# ---------------------------------------------------------------- concessioni
async def concedi(soggetto: str, soggetto_id: int, livello: str, fonte: str, *, giorni: int | None = None,
                  riferimento: str = "", concesso_da: int | None = None) -> datetime | None:
    """Dà un livello a un utente o a un server. `giorni` None = a vita. Rinnova se esiste già. Restituisce la scadenza."""
    if soggetto not in ("utente", "server"):
        raise PianoNonValido("soggetto")
    _controlla_id(soggetto_id, "id")
    if livello not in LIVELLI_A_PAGAMENTO:
        raise PianoNonValido("livello")
    if fonte not in FONTI:
        raise PianoNonValido("fonte")
    if giorni is not None and not (isinstance(giorni, int) and 0 < giorni <= 3660):
        raise PianoNonValido("giorni")
    from datetime import timedelta

    scade = None if giorni is None else datetime.now(timezone.utc) + timedelta(days=giorni)
    await _pool().execute(
        """
        INSERT INTO piani_concessioni (soggetto, soggetto_id, livello, fonte, riferimento, scade_il, concesso_da)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (soggetto, soggetto_id, fonte, riferimento)
        DO UPDATE SET livello = EXCLUDED.livello, scade_il = EXCLUDED.scade_il, concesso_da = EXCLUDED.concesso_da
        """,
        soggetto, soggetto_id, livello, fonte, riferimento[:100], scade, concesso_da,
    )
    _invalida(soggetto, soggetto_id)
    return scade


async def revoca(soggetto: str, soggetto_id: int, fonte: str | None = None, riferimento: str | None = None) -> int:
    """Toglie le concessioni di un soggetto (tutte, o solo di una fonte/riferimento). Restituisce quante."""
    righe = await _pool().fetch(
        """
        DELETE FROM piani_concessioni WHERE soggetto = $1 AND soggetto_id = $2
          AND ($3::text IS NULL OR fonte = $3) AND ($4::text IS NULL OR riferimento = $4)
        RETURNING id
        """,
        soggetto, soggetto_id, fonte, riferimento,
    )
    if righe:
        _invalida(soggetto, soggetto_id)
    return len(righe)


def _invalida(soggetto: str, soggetto_id: int) -> None:
    from core.premium_cache import invalida_cache_premium

    invalida_cache_premium(soggetto_id if soggetto == "server" else None)


async def _da_concessioni(soggetto: str, soggetto_id: int, fonti_escluse: tuple[str, ...] = ()) -> str:
    righe = await _pool().fetch(
        """
        SELECT livello FROM piani_concessioni
        WHERE soggetto = $1 AND soggetto_id = $2 AND (scade_il IS NULL OR scade_il > now()) AND NOT (fonte = ANY($3))
        """,
        soggetto, soggetto_id, list(fonti_escluse),
    )
    return livello_massimo(*(r["livello"] for r in righe))


# ---------------------------------------------------------------- il livello
def server_boost(config=None) -> tuple[int, ...]:
    """I server dell'owner il cui boost dà il Premium: MAIN_GUILD_ID più PREMIUM_BOOST_GUILD_IDS."""
    if config is None:
        from core.config import config

    ids = []
    principale = getattr(config, "MAIN_GUILD_ID", 0)
    if principale:
        ids.append(int(principale))
    for pezzo in str(getattr(config, "PREMIUM_BOOST_GUILD_IDS", "") or "").split(","):
        if pezzo.strip().isdigit():
            ids.append(int(pezzo.strip()))
    return tuple(dict.fromkeys(ids))


def utente_fa_boost(user_id: int, bot, config=None) -> bool:
    if bot is None:
        return False
    for gid in server_boost(config):
        guild = bot.get_guild(gid)
        membro = guild.get_member(user_id) if guild is not None else None
        if membro is not None and getattr(membro, "premium_since", None) is not None:
            return True
    return False


async def livello_utente(user_id: int, bot=None) -> str:
    """Il livello di una persona: il massimo tra concessioni, Patreon, boost, posto premium e chiave propria."""
    from core import ai_chiavi_proprie, premium_posti_service

    trovati = [await _da_concessioni("utente", user_id)]
    if utente_fa_boost(user_id, bot):
        trovati.append(PREMIUM)
    if await premium_posti_service.stato_utente(user_id) is not None:
        trovati.append(PREMIUM)
    if await ai_chiavi_proprie.ha_chiave("utente", user_id):
        trovati.append(VIP)
    return livello_massimo(*trovati)


async def livello_server(guild_id: int, bot=None, modulo: str = "") -> str:
    """
    Il livello di un server: il massimo tra concessioni del server, tutte le fonti premium (whitelist, cassa,
    boost del proprietario, abbonamenti, posti) e la chiave propria (del server o del suo proprietario: VIP, D59).
    """
    from core import ai_chiavi_proprie, premium

    trovati = [await _da_concessioni("server", guild_id)]
    if await premium.guild_has_premium_access(guild_id, modulo, bot=bot):
        trovati.append(PREMIUM)
    if await ai_chiavi_proprie.ha_chiave("server", guild_id):
        trovati.append(VIP)
    guild = bot.get_guild(guild_id) if bot is not None else None
    proprietario = getattr(guild, "owner_id", None)
    if proprietario:
        trovati.append(await _da_concessioni("utente", proprietario))
        if await ai_chiavi_proprie.ha_chiave("utente", proprietario):
            trovati.append(VIP)
    return livello_massimo(*trovati)


# ---------------------------------------------------------------- limiti
def _controlla_limite(chiave: str, livello: str) -> None:
    if chiave not in LIMITI:
        raise PianoNonValido("limite")
    if livello not in LIVELLI:
        raise PianoNonValido("livello")


async def limite_di(chiave: str, livello: str) -> int:
    """Il limite numerico di quel livello: quello scelto dall'owner, altrimenti il predefinito."""
    _controlla_limite(chiave, livello)
    valore = await _pool().fetchval("SELECT valore FROM piani_limiti WHERE chiave = $1 AND livello = $2", chiave, livello)
    return int(valore) if valore is not None else LIMITI[chiave][1][LIVELLI.index(livello)]


async def limite_server(guild_id: int, chiave: str, bot=None) -> int:
    """Il punto che i moduli chiamano: il limite `chiave` per il livello di questo server."""
    return await limite_di(chiave, await livello_server(guild_id, bot))


async def imposta_limite(chiave: str, livello: str, valore: int | None) -> None:
    """Scrive il limite (None = torna il predefinito)."""
    _controlla_limite(chiave, livello)
    if valore is None:
        await _pool().execute("DELETE FROM piani_limiti WHERE chiave = $1 AND livello = $2", chiave, livello)
        return
    if not isinstance(valore, int) or isinstance(valore, bool) or not 0 <= valore <= MAX_VALORE:
        raise PianoNonValido("valore")
    await _pool().execute(
        "INSERT INTO piani_limiti (chiave, livello, valore) VALUES ($1, $2, $3) "
        "ON CONFLICT (chiave, livello) DO UPDATE SET valore = EXCLUDED.valore",
        chiave, livello, valore,
    )


async def tabella_limiti() -> list[tuple[str, str, list[int]]]:
    """[(chiave, descrizione, [valore per livello])] con i valori in uso."""
    righe = await _pool().fetch("SELECT chiave, livello, valore FROM piani_limiti")
    scelti = {(r["chiave"], r["livello"]): r["valore"] for r in righe}
    return [(c, d, [scelti.get((c, l), base[i]) for i, l in enumerate(LIVELLI)]) for c, (d, base) in LIMITI.items()]


# ---------------------------------------------------------------- prezzi e sconti
@dataclass(frozen=True)
class Sconto:
    nome: str
    percento: int
    livello: str | None
    periodo: str | None
    valido_fino: datetime | None

    def vale(self, livello: str, periodo: str, adesso: datetime) -> bool:
        return ((self.livello in (None, livello)) and (self.periodo in (None, periodo))
                and (self.valido_fino is None or self.valido_fino > adesso))


def prezzo_scontato(centesimi: int, percentuali: list[int]) -> int:
    """Applica gli sconti uno dopo l'altro (mai sotto zero), arrotondando per eccesso al centesimo."""
    valore = centesimi
    for p in percentuali:
        valore = -(-valore * (100 - min(max(p, 0), 100)) // 100)
    return max(valore, 0)


async def imposta_prezzo(livello: str, periodo: str, centesimi: int | None) -> None:
    if livello not in LIVELLI_A_PAGAMENTO or periodo not in PERIODI:
        raise PianoNonValido("prezzo")
    if centesimi is None:
        await _pool().execute("DELETE FROM piani_prezzi WHERE livello = $1 AND periodo = $2", livello, periodo)
        return
    if not isinstance(centesimi, int) or isinstance(centesimi, bool) or not 0 <= centesimi <= 100_000_000:
        raise PianoNonValido("centesimi")
    await _pool().execute(
        "INSERT INTO piani_prezzi (livello, periodo, centesimi) VALUES ($1, $2, $3) "
        "ON CONFLICT (livello, periodo) DO UPDATE SET centesimi = EXCLUDED.centesimi",
        livello, periodo, centesimi,
    )


async def imposta_sconto(nome: str, percento: int | None, livello: str | None = None, periodo: str | None = None,
                         giorni: int | None = None) -> None:
    """Crea o cambia uno sconto; `percento` None lo toglie."""
    nome = nome.strip()
    if not 1 <= len(nome) <= 40:
        raise PianoNonValido("nome")
    if percento is None:
        await _pool().execute("DELETE FROM piani_sconti WHERE nome = $1", nome)
        return
    if not isinstance(percento, int) or not 1 <= percento <= 100:
        raise PianoNonValido("percento")
    if (livello is not None and livello not in LIVELLI_A_PAGAMENTO) or (periodo is not None and periodo not in PERIODI):
        raise PianoNonValido("sconto")
    if giorni is not None and not 0 < giorni <= 3660:
        raise PianoNonValido("giorni")
    from datetime import timedelta

    fino = None if giorni is None else datetime.now(timezone.utc) + timedelta(days=giorni)
    await _pool().execute(
        "INSERT INTO piani_sconti (nome, percento, livello, periodo, valido_fino) VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (nome) DO UPDATE SET percento = EXCLUDED.percento, livello = EXCLUDED.livello, "
        "periodo = EXCLUDED.periodo, valido_fino = EXCLUDED.valido_fino",
        nome, percento, livello, periodo, fino,
    )


async def listino() -> list[tuple[str, str, int, int, list[str]]]:
    """[(livello, periodo, prezzo pieno, prezzo con sconti in centesimi, nomi degli sconti)] dei soli prezzi decisi."""
    adesso = datetime.now(timezone.utc)
    prezzi = await _pool().fetch("SELECT livello, periodo, centesimi FROM piani_prezzi")
    sconti = [Sconto(**dict(r)) for r in await _pool().fetch("SELECT nome, percento, livello, periodo, valido_fino FROM piani_sconti")]
    righe = []
    for r in sorted(prezzi, key=lambda r: (rango(r["livello"]), PERIODI.index(r["periodo"]))):
        validi = [s for s in sconti if s.vale(r["livello"], r["periodo"], adesso)]
        righe.append((r["livello"], r["periodo"], r["centesimi"],
                      prezzo_scontato(r["centesimi"], [s.percento for s in validi]), [s.nome for s in validi]))
    return righe


def euro(centesimi: int) -> str:
    return f"{centesimi // 100},{centesimi % 100:02d} €"


_TESTI_LISTINO = {
    "piani_listino_vuoto": "I prezzi non sono ancora stati decisi.",
    "piani_listino_riga": "{livello} {periodo}: {prezzo}",
    "piani_listino_sconto": "{livello} {periodo}: ~~{pieno}~~ {prezzo} ({sconti})",
    "piani_listino_nota": "Il pagamento non si fa dal bot.",
    "piani_periodo_mensile": "mensile",
    "piani_periodo_annuale": "annuale",
    "piani_periodo_a_vita": "a vita",
}


async def testo_listino(t=None) -> str:
    """
    Il testo dei prezzi per `/premium info`. Il bot non incassa: lo dice. `t(chiave, **parametri)` traduce
    (di solito `testo_per` dell'interazione); senza, escono i testi italiani di base.
    """
    async def tr(chiave: str, **kw) -> str:
        if t is not None:
            return await t(chiave, **kw)
        return _TESTI_LISTINO[chiave].format(**kw)

    righe = await listino()
    if not righe:
        return await tr("piani_listino_vuoto")
    testo = []
    for livello, periodo, pieno, finale, nomi in righe:
        parti = {"livello": ETICHETTE[livello], "periodo": await tr(f"piani_periodo_{periodo}"), "prezzo": euro(finale)}
        if pieno == finale:
            testo.append(await tr("piani_listino_riga", **parti))
        else:
            testo.append(await tr("piani_listino_sconto", pieno=euro(pieno), sconti=", ".join(nomi), **parti))
    testo.append(await tr("piani_listino_nota"))
    return "\n".join(testo)

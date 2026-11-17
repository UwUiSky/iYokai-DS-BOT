"""
core/greetings_logic.py
==========================
Logica pura di Welcome / Goodbye / Boost messages (SPEC.md
§14.4-14.6). Sostituzione dei segnaposto in un template testuale —
nessuna dipendenza da discord.py, il chiamante (cogs/utility/
greetings.py) passa già stringhe/numeri semplici estratti dagli
oggetti Discord reali.

Segnaposto supportati: {user} (mention), {username} (nome semplice,
senza @), {server} (nome del server), {membercount} (numero attuale
di membri).

Nota sul perché {user} e {username} non entrano in conflitto tra
loro nella sostituzione: la stringa esatta "{user}" non è una
sottostringa di "{username}" (dopo "user" in "{username}" segue
"name}", non "}") — l'ordine delle sostituzioni non ha bisogno di
essere garantito in un modo particolare, verificato esplicitamente
con un test dedicato invece di assumerlo.
"""

from __future__ import annotations

import re

import random

from core.role_menu_logic import valida_emoji

DEFAULT_WELCOME_TEMPLATE = (
    "Welcome {user} to **{server}**! We're now {membercount} members strong. 🎉"
)
DEFAULT_GOODBYE_TEMPLATE = "Ciao, è stato bello vederti, **{username}**! 👋"
DEFAULT_BOOST_TEMPLATE = (
    "🚀 {user} just boosted **{server}**! Thank you for the support!"
)


def _ordinale(numero: int) -> str:
    """1234 -> "1.234º" (il numero del membro, RUO-018)."""
    return f"{numero:,}".replace(",", ".") + "º"


_MATH = re.compile(r"\{math:((?:[^{}]|\{(?:membercount|userid|serverid)\})*)\}")
_MATH_VALIDO = re.compile(r"^\s*\d{1,12}(?:\s*[+-]\s*\d{1,12}){0,10}\s*$")


def _calcola(template: str, member_count: int, user_id: int | None, server_id: int | None) -> str:
    """RUO-022: `{math: 3 + {membercount}}`. Solo somme e sottrazioni di interi, mai eval."""

    def _uno(m: re.Match) -> str:
        espressione = m.group(1).replace("{membercount}", str(member_count))
        if user_id is not None:
            espressione = espressione.replace("{userid}", str(user_id))
        if server_id is not None:
            espressione = espressione.replace("{serverid}", str(server_id))
        if not _MATH_VALIDO.match(espressione):
            return m.group(0)
        totale = 0
        for segno, numero in re.findall(r"([+-]?)\s*(\d+)", espressione):
            totale += -int(numero) if segno == "-" else int(numero)
        return str(totale)

    return _MATH.sub(_uno, template)


_SE_NUOVO = re.compile(r"\{se_nuovo:(\d{1,4})\|([^{}]{0,300})\}")
_SE_RUOLO = re.compile(r"\{se_ruolo:(\d{1,22})\|([^{}]{0,300})\}")


def _condizioni(
    template: str, eta_giorni: int | None, ruoli_ids: frozenset[int] | None, tutte_vere: bool
) -> str:
    """
    RUO-026: condizioni semplici, niente linguaggio di script. `{se_nuovo:7|testo}`: il testo esce se
    l'account ha al massimo 7 giorni. `{se_ruolo:ID|testo}`: esce se il membro ha il ruolo. Senza il dato
    (anteprima senza membro) la condizione resta scritta; con `tutte_vere` (misura della lunghezza) vale sempre.
    """

    def nuovo(m: re.Match) -> str:
        if tutte_vere or (eta_giorni is not None and eta_giorni <= int(m.group(1))):
            return m.group(2)
        return m.group(0) if eta_giorni is None else ""

    def ruolo(m: re.Match) -> str:
        if tutte_vere or (ruoli_ids is not None and int(m.group(1)) in ruoli_ids):
            return m.group(2)
        return m.group(0) if ruoli_ids is None else ""

    return _SE_RUOLO.sub(ruolo, _SE_NUOVO.sub(nuovo, template))


def render_template(
    template: str,
    user_mention: str,
    username: str,
    server_name: str,
    member_count: int,
    *,
    user_id: int | None = None,
    display_name: str | None = None,
    server_id: int | None = None,
    invitante: str | None = None,
    inviti_invitante: int | None = None,
    rientri: int | None = None,
    creato_il: int | None = None,
    eta_giorni: int | None = None,
    ruoli_ids: frozenset[int] | None = None,
    condizioni_vere: bool = False,
) -> str:
    """
    Sostituisce i segnaposto. `{invitante}`, `{inviti_invitante}`, `{rientri}` e `{creato_il}` (D69 B13) si
    sostituiscono solo se chi chiama dà il dato. `{userid}`, `{displayname}` e `{serverid}` (RUO-019..021)
    restano scritti se chi chiama non dà il dato; `{ordinal}` (RUO-018) usa il numero dei membri.
    """
    template = _condizioni(template, eta_giorni, ruoli_ids, condizioni_vere)
    template = _calcola(template, member_count, user_id, server_id)
    testo = (
        template.replace("{user}", user_mention)
        .replace("{username}", username)
        .replace("{server}", server_name)
        .replace("{membercount}", str(member_count))
    )
    if "{ordinal}" in testo:
        testo = testo.replace("{ordinal}", _ordinale(member_count))
    if user_id is not None:
        testo = testo.replace("{userid}", str(user_id))
    if display_name is not None:
        testo = testo.replace("{displayname}", display_name)
    if server_id is not None:
        testo = testo.replace("{serverid}", str(server_id))
    if invitante is not None:
        testo = testo.replace("{invitante}", invitante)
    if inviti_invitante is not None:
        testo = testo.replace("{inviti_invitante}", str(inviti_invitante))
    if rientri is not None:
        testo = testo.replace("{rientri}", str(rientri))
    if creato_il is not None:
        testo = testo.replace("{creato_il}", f"<t:{creato_il}:D>")
    return testo


SEGNAPOSTO_INVITI = ("{invitante}", "{inviti_invitante}", "{rientri}")


def usa_segnaposto_inviti(*testi: str | None) -> bool:
    """Vero se un testo vuole dati sull'invito: solo allora si va a cercarli."""
    return any(seg in (t or "") for t in testi for seg in SEGNAPOSTO_INVITI)


# LIM-10 (M 10.2): il messaggio finale è un messaggio normale (2000). La
# lunghezza si misura DOPO i segnaposto, con i valori peggiori di chi non
# si conosce al momento della configurazione: una menzione utente (<@ + 20
# cifre + >) e un nome utente di 32 caratteri.
MAX_MESSAGE_LENGTH = 2000
_LUNGHEZZA_MENZIONE_UTENTE = 23
_LUNGHEZZA_NOME_UTENTE = 32
_LUNGHEZZA_ID = 20


def lunghezza_dopo_segnaposto(template: str, server_name: str, member_count: int) -> int:
    """Lunghezza peggiore del testo dopo la sostituzione dei segnaposto."""
    return len(
        render_template(
            template,
            user_mention="m" * _LUNGHEZZA_MENZIONE_UTENTE,
            username="u" * _LUNGHEZZA_NOME_UTENTE,
            server_name=server_name,
            member_count=member_count,
            user_id=10**_LUNGHEZZA_ID - 1,
            display_name="d" * _LUNGHEZZA_NOME_UTENTE,
            server_id=10**_LUNGHEZZA_ID - 1,
            invitante="m" * _LUNGHEZZA_MENZIONE_UTENTE,
            inviti_invitante=10**6 - 1,
            rientri=10**4 - 1,
            creato_il=10**11,
            condizioni_vere=True,
        )
    )


# RUO-013, 017, 023, 025: DM con testo suo, varianti a caso, reazioni sul benvenuto.
MAX_VARIANTI = 10
MAX_REAZIONI = 5


def analizza_varianti(testo: str) -> tuple[list[str], str | None]:
    """Una variante per riga, senza righe vuote. Ritorna (varianti, errore)."""
    varianti = [riga.strip() for riga in testo.splitlines() if riga.strip()]
    if len(varianti) > MAX_VARIANTI:
        return [], f"Al massimo {MAX_VARIANTI} varianti: ne hai scritte {len(varianti)}."
    for riga in varianti:
        if len(riga) > MAX_MESSAGE_LENGTH:
            return [], f"Una variante supera {MAX_MESSAGE_LENGTH} caratteri."
    return varianti, None


def analizza_reazioni(testo: str) -> tuple[list[str], str | None]:
    """Emoji separate da spazi, senza doppioni. Ritorna (reazioni, errore)."""
    reazioni: list[str] = []
    for parola in testo.split():
        if not valida_emoji(parola):
            return [], f"«{parola[:30]}» non è un'emoji."
        if parola not in reazioni:
            reazioni.append(parola)
    if len(reazioni) > MAX_REAZIONI:
        return [], f"Al massimo {MAX_REAZIONI} reazioni."
    return reazioni, None


def scegli_testo(principale: str, varianti: list[str], rng: random.Random | None = None) -> str:
    """Il testo principale o una delle varianti, a caso con la stessa probabilità."""
    if not varianti:
        return principale
    return (rng or random).choice([principale, *varianti])


class PrimiMessaggi:
    """
    RUO-024: chi è appena entrato e non ha ancora scritto. Solo in memoria e per poco tempo: dopo
    `DURATA_SECONDI` o al primo messaggio il segno sparisce (nessun dato personale su disco).
    Un tetto fisso tiene a bada la memoria anche durante un raid.
    """

    DURATA_SECONDI = 24 * 3600
    MASSIMO = 5000

    def __init__(self) -> None:
        self._scadenze: dict[tuple[int, int], float] = {}

    def registra(self, guild_id: int, user_id: int, ora: float) -> None:
        if len(self._scadenze) >= self.MASSIMO:
            self._scadenze = {k: v for k, v in self._scadenze.items() if v > ora}
        if len(self._scadenze) < self.MASSIMO:
            self._scadenze[(guild_id, user_id)] = ora + self.DURATA_SECONDI

    def consuma(self, guild_id: int, user_id: int, ora: float) -> bool:
        """Vero una sola volta: se il membro era nuovo e il segno non è scaduto."""
        scadenza = self._scadenze.pop((guild_id, user_id), None)
        return scadenza is not None and scadenza > ora

    def dimentica(self, guild_id: int, user_id: int) -> None:
        self._scadenze.pop((guild_id, user_id), None)

    def __len__(self) -> int:
        return len(self._scadenze)

"""
core/global_ban_logic.py
============================
Logica pura del ban globale (SPEC.md §7.3) — nessuna dipendenza da
discord.py o dal database, solo la regola: propaga un ban da un
server all'altro SOLO SE entrambi hanno esplicitamente aderito alla
rete (opt-in reciproco), mai a un server che non ha scelto di
partecipare.

Nota di design (perché questo non è "il" ban globale via fingerprint
di SPEC.md §4.3): il fingerprint/alt-detection lì descritto risolve
un problema diverso — riconoscere che DUE ACCOUNT DIVERSI sono la
stessa persona (un alt), cosa che richiede una raccolta IP/OAuth2
"identify" fatta AL MOMENTO DEL VERIFY, prima che l'account si
comporti male (§4.2, non costruito: un account appena bannato dalla
Spam Trap non collaborerebbe certo a un flusso OAuth2 dopo il fatto,
quindi quella raccolta non potrebbe mai avvenire a ban avvenuto).
Qui invece il problema è più semplice e concretamente risolvibile
oggi: lo STESSO account Discord (stesso user id, nessuna euristica di
somiglianza) viene bannato anche negli altri server che condividono
il bot e hanno aderito alla rete — un ban dello stesso utente, non
un'inferenza su un utente diverso.
"""

from __future__ import annotations


def should_propagate_ban(
    *, source_guild_id: int, target_guild_id: int, source_opted_in: bool, target_opted_in: bool
) -> bool:
    """
    True solo se: il server sorgente (dove è scattato il ban) ha acceso
    "invia" e il server target ha acceso "ricevi" (SIC-046: due
    interruttori separati; qui `source_opted_in` e `target_opted_in` sono
    questi), e non sono lo stesso server (propagare un ban su se stessi non ha
    senso — l'utente è già bannato lì).
    """
    if source_guild_id == target_guild_id:
        return False
    return source_opted_in and target_opted_in


# --- scala di affidabilità del server che manda il ban -----------------------
# Il ban di un server si propaga solo se il server è affidabile. Il punteggio va da 0 a 100.
# Sotto SOGLIA_MINIMA il ban non parte. Il ban automatico (solo se il server che riceve lo ha scelto)
# parte solo da SOGLIA_AUTOMATICA in su; negli altri casi arriva una proposta con i tasti.
SOGLIA_MINIMA = 55
SOGLIA_AUTOMATICA = 85

MIN_MEMBRI = 50  # sotto questa quota il server non fa partire ban globali
MIN_GIORNI_BOT = 7  # il bot deve essere nel server da almeno una settimana
MAX_BAN_ORA = 5  # oltre questo ritmo il server sta bannando a raffica
MAX_BAN_GIORNO = 15  # tetto di ban propagati da un server in un giorno
MAX_SERVER_PER_BAN = 100  # tetto di server che ricevono lo stesso ban
MOTIVO_MIN_CARATTERI = 15
MOTIVI_GENERICI = frozenset({
    "", "ban", "spam", "raid", "nuke", "test", "reason", "motivo", "no reason", "n/a", "-", "spam trap triggered",
})


def motivo_di_qualita(motivo: str | None) -> bool:
    """Un motivo vale se non è vuoto, non è una parola generica ed è abbastanza lungo da spiegare qualcosa."""
    testo = " ".join((motivo or "").casefold().split())
    return testo not in MOTIVI_GENERICI and len(testo) >= MOTIVO_MIN_CARATTERI


def punteggio_affidabilita(
    *,
    membri: int,
    giorni_server: int,
    giorni_bot: int,
    ban_ultima_ora: int,
    ban_oggi: int,
    motivo: str | None,
    con_prova: bool,
    conferme: int,
) -> tuple[int, list[str]]:
    """
    Punteggio 0-100 e i codici di ciò che ha pesato (per spiegarlo allo staff).
    Parte da 40. Più è grande e vecchio il server, più sale; un ritmo alto di ban,
    un motivo vuoto o generico lo fanno scendere; una prova (un caso collegato) e
    le conferme di altri server lo alzano. Server piccolo o bot nuovo: 0, non si discute.
    """
    if membri < MIN_MEMBRI:
        return 0, ["piccolo"]
    if giorni_bot < MIN_GIORNI_BOT:
        return 0, ["bot_nuovo"]
    punti, codici = 40, []
    if giorni_server >= 180:
        punti += 10
        codici.append("server_vecchio")
    elif giorni_server < 30:
        punti -= 15
        codici.append("server_giovane")
    if membri >= 500:
        punti += 10
        codici.append("server_grande")
    if giorni_bot >= 60:
        punti += 5
        codici.append("bot_da_tempo")
    if ban_ultima_ora > MAX_BAN_ORA:
        punti -= 40
        codici.append("ritmo_alto")
    if ban_oggi > MAX_BAN_GIORNO:
        punti -= 40
        codici.append("tetto_giorno")
    if motivo_di_qualita(motivo):
        punti += 10
        codici.append("motivo_buono")
    else:
        punti -= 15
        codici.append("motivo_debole")
    if con_prova:
        punti += 20
        codici.append("con_prova")
    if conferme > 0:
        punti += min(conferme, 3) * 7
        codici.append("conferme")
    return max(0, min(100, punti)), codici


def decisione_propagazione(
    *, punteggio: int, raid_o_nuke_in_corso: bool, invia: bool, ban_oggi: int
) -> str | None:
    """Codice del rifiuto («spento», «attacco», «tetto», «punteggio») o None se il ban può partire."""
    if not invia:
        return "spento"
    if raid_o_nuke_in_corso:
        return "attacco"  # durante un raid o un nuke i ban sono rumore: non si propagano
    if ban_oggi > MAX_BAN_GIORNO:
        return "tetto"
    if punteggio < SOGLIA_MINIMA:
        return "punteggio"
    return None


def modo_di_arrivo(*, punteggio: int, il_server_vuole_automatico: bool) -> str:
    """«automatico» solo se lo staff lo ha scelto E il punteggio è alto; in tutti gli altri casi «proposta»."""
    if il_server_vuole_automatico and punteggio >= SOGLIA_AUTOMATICA:
        return "automatico"
    return "proposta"

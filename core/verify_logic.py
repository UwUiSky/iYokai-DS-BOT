"""
core/verify_logic.py
=======================
Logica pura del Verify Base — stesso principio degli altri moduli
(core/permissions.py, core/spam_trap_logic.py, ecc.): solo numeri e
booleani qui dentro, niente discord.py.

Scope di questa sessione: SPEC.md §4.1 (Verify Base — button/reaction/
captcha/età account/mutual servers/invite tracker, quest'ultimo già
fatto), §4.4 (whitelist), §4.5 (blacklist), §4.6 (log). §4.2
(Verify Avanzato, fingerprint IP/ISP) e §4.3 (Anti-Alt) restano fuori:
dipendono dal Web Panel (SPEC.md §C), non ancora costruito — non
tentati qui, non finti con una versione ridotta.

Nota sul "controllo mutual servers": il bot vede SOLO quanti server,
tra quelli in cui si trova LUI STESSO, contengono anche questo
utente — non tutti i server dell'utente in assoluto (Discord non
espone quel dato a un bot). È un segnale debole, non una prova.
Già annotato così nello schema di progetto originale.
Promemoria, tempo massimo, azione su chi fallisce e verifica solo per gli
account sospetti (VER-008, 011, 012, 013): le regole sono qui sotto.
Funzioni coperte: SPEC §4.1, §4.4-§4.6 (VER-008, 011, 012, 013)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def meets_account_age(
    created_at: datetime, min_age_days: int, now: datetime | None = None
) -> bool:
    """
    True se l'account è abbastanza vecchio. min_age_days=0 significa
    controllo disattivato (passa sempre) — è il default, coerente
    con "tutto spento finché l'admin non lo configura".
    """
    if min_age_days <= 0:
        return True
    current = now or datetime.now(timezone.utc)
    eta = current - created_at
    return eta >= timedelta(days=min_age_days)


def meets_mutual_servers(mutual_count: int, min_required: int) -> bool:
    """min_required=0 significa controllo disattivato."""
    if min_required <= 0:
        return True
    return mutual_count >= min_required


@dataclass(frozen=True)
class VerifyOutcome:
    success: bool
    reason: str  # sempre valorizzato, anche in caso di successo (per il log)


def decide_verify_outcome(
    is_whitelisted: bool,
    is_blacklisted: bool,
    age_ok: bool,
    mutual_ok: bool,
    captcha_ok: bool,
) -> VerifyOutcome:
    """
    Decide l'esito finale del verify, con un ordine di priorità
    preciso:
    1. La blacklist vince SEMPRE, anche su un utente whitelistato per
       errore — un admin che blacklista qualcuno lo sta facendo di
       proposito, non deve poter essere aggirato da una whitelist
       impostata prima per altri motivi.
    2. La whitelist bypassa TUTTI gli altri controlli (età, mutual,
       captcha) — è pensata per gli utenti fidati a cui l'admin vuole
       risparmiare la trafila.
    3. Altrimenti, ogni controllo ABILITATO deve passare. I controlli
       disattivati (soglia 0) risultano già `True` dalle funzioni
       sopra, quindi qui non serve sapere quali sono attivi: basta
       controllare che nessuno dei tre sia `False`.
    """
    if is_blacklisted:
        return VerifyOutcome(False, "User is blacklisted on this server.")

    if is_whitelisted:
        return VerifyOutcome(True, "Whitelisted user — checks bypassed.")

    if not age_ok:
        return VerifyOutcome(False, "Account does not meet the minimum age requirement.")

    if not mutual_ok:
        return VerifyOutcome(False, "Account does not share enough mutual servers.")

    if not captcha_ok:
        return VerifyOutcome(False, MOTIVO_CAPTCHA)

    return VerifyOutcome(True, "All checks passed.")


# ---------------------------------------------------------------- VER-008…013
AZIONI_FALLITA = ("niente", "quarantena", "kick", "ban")
AZIONI_SCADENZA = ("kick", "ban")
GIORNI_ACCOUNT_SOSPETTO = 7
# Captcha sbagliato: si agisce solo dopo questi fallimenti di fila (un errore di battitura capita).
FALLIMENTI_CAPTCHA_PRIMA_DELL_AZIONE = 3
# I fallimenti contano solo se fatti in questa finestra: errori di giorni
# prima non si sommano a quello di oggi.
FINESTRA_FALLIMENTI_CAPTCHA = timedelta(hours=24)


def esiti_nella_finestra(tentativi: list[tuple], adesso: datetime) -> list[bool]:
    """Esiti (dal più recente) dei tentativi `(ok, motivo, quando)` dentro FINESTRA_FALLIMENTI_CAPTCHA."""
    return [ok for ok, _, quando in tentativi if adesso - quando <= FINESTRA_FALLIMENTI_CAPTCHA]
MOTIVO_CAPTCHA = "Captcha verification failed."


def account_sospetto(account_created_at: datetime, has_avatar: bool, now: datetime | None = None) -> bool:
    """VER-013: sospetto = account con meno di GIORNI_ACCOUNT_SOSPETTO giorni o senza avatar."""
    adesso = now or datetime.now(timezone.utc)
    return not has_avatar or adesso - account_created_at < timedelta(days=GIORNI_ACCOUNT_SOSPETTO)


def azione_dopo_fallimento(azione: str, motivo: str, ultimi_esiti: list[bool]) -> str:
    """
    VER-012: l'azione da fare dopo un tentativo fallito. Per il captcha
    sbagliato si aspetta FALLIMENTI_CAPTCHA_PRIMA_DELL_AZIONE fallimenti di
    fila (`ultimi_esiti`: dal più recente, quello appena fatto compreso).
    """
    if azione not in AZIONI_FALLITA or azione == "niente":
        return "niente"
    if motivo == MOTIVO_CAPTCHA:
        n = FALLIMENTI_CAPTCHA_PRIMA_DELL_AZIONE
        if len(ultimi_esiti) < n or any(ultimi_esiti[:n]):
            return "niente"
    return azione


# ---------------------------------------------------------------- VER-019, VER-020
AZIONI_ETA = ("attendi", "kick")


def quando_maggiorenne(account_created_at: datetime, min_age_days: int) -> datetime:
    """VER-019: il momento da cui l'account ha l'età minima richiesta."""
    return account_created_at + timedelta(days=min_age_days)


def sospesa_adesso(fino_epoch: int | None, adesso: datetime | None = None) -> bool:
    """VER-020: la verifica è sospesa (modalità cieca) se la fine è nel futuro."""
    if not fino_epoch:
        return False
    return (adesso or datetime.now(timezone.utc)).timestamp() < fino_epoch

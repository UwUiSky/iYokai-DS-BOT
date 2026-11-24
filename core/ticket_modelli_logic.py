"""
core/ticket_modelli_logic.py
============================
Raccolta di modelli pronti di pannelli ticket (TKT-080): ogni modello ha le domande del modulo, i motivi
del menu e qualche risposta pronta (articolo). Si importano con `/admin-ticket-pannelli modello`; i testi sono
nella lingua del server (italiano o inglese). La raccolta pubblica scambiata fra server resta del pannello web (NF-20).
Funzioni coperte: SPEC §13 (TKT-080)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomandaModello:
    etichetta: str
    segnaposto: str | None = None
    obbligatoria: bool = True
    lunga: bool = False
    minimo: int | None = None
    tipo: str = "testo"
    voci: tuple[str, ...] = ()


@dataclass(frozen=True)
class Modello:
    id: str
    nome: str  # il nome suggerito per il pannello
    descrizione: str  # una riga per l'elenco
    benvenuto: str
    domande: tuple[DomandaModello, ...]
    motivi: tuple[tuple[str, str | None], ...] = ()  # (etichetta, descrizione)
    articoli: tuple[tuple[str, str], ...] = ()  # (titolo, testo)
    voto: bool = False


_D = DomandaModello

_MODELLI = {
    "it": (
        Modello(
            "supporto", "Supporto", "Assistenza generale con una domanda e il voto finale.",
            "Ciao {utente}, grazie per averci scritto. Lo staff ti risponde appena possibile.",
            (_D("Di cosa hai bisogno?", "Descrivi il problema", lunga=True, minimo=15),
             _D("Hai già provato qualcosa?", "Facoltativo", obbligatoria=False, lunga=True)),
            motivi=(("Problema tecnico", "Qualcosa non funziona"), ("Domanda generale", "Vuoi sapere come funziona qualcosa")),
            articoli=(("Come funziona il supporto", "Ciao {utente}! Il ticket {numero} è stato preso in carico. Lo staff risponde in genere entro un giorno."),),
            voto=True,
        ),
        Modello(
            "candidature", "Candidature", "Candidature allo staff con motivazione ed esperienza.",
            "Ciao {utente}, grazie per la candidatura. Lo staff la leggerà con calma.",
            (_D("Quanti anni hai?", "Solo il numero"),
             _D("Perché vuoi entrare nello staff?", "Racconta con parole tue", lunga=True, minimo=50),
             _D("Esperienze precedenti", "Facoltativo", obbligatoria=False, lunga=True)),
            articoli=(("Esito della candidatura", "Ciao {utente}, abbiamo valutato la tua candidatura. Ti scriviamo qui l'esito."),),
        ),
        Modello(
            "segnalazioni", "Segnalazioni", "Segnalare un utente: tipo, chi e cosa è successo.",
            "Ciao {utente}, grazie della segnalazione. Resta riservata: la vede solo lo staff.",
            (_D("Che tipo di problema è?", tipo="scelta", voci=("Spam", "Molestie", "Truffa", "Altro")),
             _D("Chi vuoi segnalare?", obbligatoria=False, tipo="utente"),
             _D("Cosa è successo?", "Date, canali, messaggi", lunga=True, minimo=20)),
            articoli=(("Segnalazione presa in carico", "Ciao {utente}, la tua segnalazione è stata presa in carico da {staff}."),),
        ),
        Modello(
            "partnership", "Partnership", "Proposte di collaborazione fra server.",
            "Ciao {utente}, grazie per la proposta di partnership.",
            (_D("Nome del tuo server", "Come si chiama"),
             _D("Quanti membri ha?", "Un numero"),
             _D("Cosa proponi?", "Spiega la collaborazione", lunga=True, minimo=30)),
        ),
    ),
    "en-US": (
        Modello(
            "supporto", "Support", "General help with one question and a final rating.",
            "Hi {utente}, thanks for writing to us. The staff will reply as soon as possible.",
            (_D("What do you need?", "Describe the problem", lunga=True, minimo=15),
             _D("Have you tried anything?", "Optional", obbligatoria=False, lunga=True)),
            motivi=(("Technical problem", "Something doesn't work"), ("General question", "You want to know how something works")),
            articoli=(("How support works", "Hi {utente}! Ticket {numero} has been picked up. The staff usually replies within a day."),),
            voto=True,
        ),
        Modello(
            "candidature", "Applications", "Staff applications with motivation and experience.",
            "Hi {utente}, thanks for applying. The staff will read it carefully.",
            (_D("How old are you?", "Just the number"),
             _D("Why do you want to join the staff?", "Tell us in your own words", lunga=True, minimo=50),
             _D("Previous experience", "Optional", obbligatoria=False, lunga=True)),
            articoli=(("Application result", "Hi {utente}, we have reviewed your application. We will write the result here."),),
        ),
        Modello(
            "segnalazioni", "Reports", "Reporting a user: type, who and what happened.",
            "Hi {utente}, thanks for the report. It stays private: only the staff sees it.",
            (_D("What kind of problem is it?", tipo="scelta", voci=("Spam", "Harassment", "Scam", "Other")),
             _D("Who do you want to report?", obbligatoria=False, tipo="utente"),
             _D("What happened?", "Dates, channels, messages", lunga=True, minimo=20)),
            articoli=(("Report picked up", "Hi {utente}, your report has been picked up by {staff}."),),
        ),
        Modello(
            "partnership", "Partnership", "Collaboration proposals between servers.",
            "Hi {utente}, thanks for the partnership proposal.",
            (_D("Name of your server", "What it is called"),
             _D("How many members?", "A number"),
             _D("What do you propose?", "Explain the collaboration", lunga=True, minimo=30)),
        ),
    ),
}

IDENTIFICATORI = tuple(m.id for m in _MODELLI["it"])


def modelli(lingua: str) -> tuple[Modello, ...]:
    """I modelli nella lingua data (italiano o inglese; ogni altra lingua usa l'inglese)."""
    return _MODELLI["it"] if lingua == "it" else _MODELLI["en-US"]


def modello(identificatore: str, lingua: str) -> Modello | None:
    return next((m for m in modelli(lingua) if m.id == (identificatore or "").strip().lower()), None)

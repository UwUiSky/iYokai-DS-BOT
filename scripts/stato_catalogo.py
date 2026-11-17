"""
scripts/stato_catalogo.py
=========================
Conta lo stato delle voci del catalogo (`revisione/01-analisi/catalogo/`) e scrive
`revisione/01-analisi/catalogo/STATO.md`. Una voce vale «fatta» se il suo codice (es. MUS-030)
compare nel codice o nei test; «solo nei registri» se compare solo in SPEC, registro o memorie;
altrimenti «non trovata». Le aree con l'issue chiusa sono segnate a parte: lì una voce non
trovata va controllata a mano prima di rifarla (può essere fatta senza il codice nel commento).
Uso: python3 scripts/stato_catalogo.py   (dalla radice del repository; nessuna dipendenza)
"""

from __future__ import annotations

import collections
import datetime
import pathlib
import re

RADICE = pathlib.Path(__file__).resolve().parent.parent
CATALOGO = RADICE / "revisione" / "01-analisi" / "catalogo"
USCITA = CATALOGO / "STATO.md"
# Area del catalogo -> (issue, aperta?). Da aggiornare quando un'issue si chiude o si riapre.
ISSUE = {
    "01-moderazione": (115, False), "02-automod": (116, False), "03-sicurezza-antiraid-antinuke": (117, True),
    "04-verifica": (118, False), "05-log": (119, True), "06-ticket-e-modmail": (120, False),
    "07-backup-e-restore": (121, False), "08-configurazione-pannello-premium": (122, True),
    "09-benvenuto-e-ruoli": (123, True), "10-livelli-e-rank": (124, True), "11-economia-e-giochi": (125, True),
    "12-musica": (126, True), "13-vocali-temporanei": (127, True), "14-utility": (128, False),
    "15-alert-social": (129, True), "16-statistiche": (130, True), "17-divertimento-e-immagini": (131, False),
    "18-ai": (132, False),
}
_RIGA = re.compile(r"^\|\s*([A-Z]{2,4}-\d{3})\s*\|(.*)$")
_CODICE = re.compile(r"\b([A-Z]{2,4})-(\d{3})\b")
# «RUO-042, 043, 090–109, 113»: i numeri dopo il primo ereditano il prefisso.
_ELENCO = re.compile(r"\b([A-Z]{2,4})-(\d{3}(?:\s*(?:,|e|…|\.\.\.|–|-)\s*(?:\1-)?\d{3})+)")
_PEZZO = re.compile(r"(\d{3})(?:\s*(?:…|\.\.\.|–|-)\s*(?:[A-Z]{2,4}-)?(\d{3}))?")


def codici_in(testo: str) -> set[str]:
    """I codici citati in un testo, compresi elenchi e intervalli («MUS-030…035», «RUO-042, 043, 090–109»)."""
    trovati = {f"{p}-{n}" for p, n in _CODICE.findall(testo)}
    for prefisso, elenco in _ELENCO.findall(testo):
        for primo, ultimo in _PEZZO.findall(elenco):
            fine = int(ultimo) if ultimo else int(primo)
            if 0 <= fine - int(primo) < 60:
                trovati.update(f"{prefisso}-{n:03d}" for n in range(int(primo), fine + 1))
    return trovati


def _leggi(modelli: list[str]) -> set[str]:
    trovati: set[str] = set()
    for modello in modelli:
        for percorso in RADICE.glob(modello):
            if percorso.is_file() and percorso != USCITA:
                trovati |= codici_in(percorso.read_text(encoding="utf-8", errors="ignore"))
    return trovati


def voci_del_catalogo() -> dict[str, tuple[str, bool]]:
    """codice -> (area, scartata dall'owner)."""
    voci: dict[str, tuple[str, bool]] = {}
    for percorso in sorted(CATALOGO.glob("[0-9]*.md")):
        for riga in percorso.read_text(encoding="utf-8").splitlines():
            trovata = _RIGA.match(riga)
            if trovata:
                voci[trovata.group(1)] = (percorso.stem, "scelta dell'owner: no" in riga.lower())
    return voci


def calcola() -> tuple[dict[str, collections.Counter], dict[str, list[str]]]:
    nel_codice = _leggi(["cogs/**/*.py", "core/**/*.py", "main.py"]) | _leggi(["tests/**/*.py"])
    nei_registri = _leggi(["revisione/REGISTRO_RISOLTE.md", "revisione/SPEC.md", ".claude/memoria/*.md"])
    conti: dict[str, collections.Counter] = {}
    mancanti: dict[str, list[str]] = {}
    for codice, (area, scartata) in voci_del_catalogo().items():
        conto = conti.setdefault(area, collections.Counter())
        conto["totale"] += 1
        if scartata:
            conto["scartate"] += 1
        elif codice in nel_codice:
            conto["fatte"] += 1
        elif codice in nei_registri:
            conto["registri"] += 1
        else:
            conto["non_trovate"] += 1
            mancanti.setdefault(area, []).append(codice)
    return conti, mancanti


def scrivi() -> str:
    conti, mancanti = calcola()
    righe = [
        "# Stato del catalogo",
        "",
        f"Generato da `scripts/stato_catalogo.py` il {datetime.date.today().isoformat()}. Non modificare a mano: rilancia lo script.",
        "",
        "- **Fatte**: il codice della voce compare nel codice o nei test.",
        "- **Solo registri**: citata in SPEC, registro o memorie ma non nel codice: da controllare.",
        "- **Non trovate**: nessuna traccia. Nelle aree con l'issue **aperta** sono lavoro da fare; nelle aree con",
        "  l'issue **chiusa** vanno controllate a mano (possono essere fatte senza il codice nel commento).",
        "",
        "| Area | Issue | Totale | Fatte | Solo registri | Non trovate | Scartate |",
        "|---|---|---|---|---|---|---|",
    ]
    totale = collections.Counter()
    aperte = collections.Counter()
    for area, conto in conti.items():
        numero, aperta = ISSUE.get(area, (0, True))
        totale.update(conto)
        if aperta:
            aperte.update(conto)
        righe.append(
            f"| {area} | #{numero} {'aperta' if aperta else 'chiusa'} | {conto['totale']} | {conto['fatte']} | "
            f"{conto['registri']} | {conto['non_trovate']} | {conto['scartate']} |"
        )
    righe.append(
        f"| **Totale** | | **{totale['totale']}** | **{totale['fatte']}** | **{totale['registri']}** | "
        f"**{totale['non_trovate']}** | **{totale['scartate']}** |"
    )
    righe += [
        "",
        f"Nelle sole aree con l'issue aperta: {aperte['totale']} voci, {aperte['fatte']} fatte, "
        f"{aperte['registri']} solo nei registri, **{aperte['non_trovate']} da fare**, {aperte['scartate']} scartate.",
        "",
        "## Voci non trovate, per area",
        "",
    ]
    for area, codici in mancanti.items():
        numero, aperta = ISSUE.get(area, (0, True))
        righe.append(f"- **{area}** (#{numero}, {'aperta' if aperta else 'chiusa: controllare a mano'}), {len(codici)}: {', '.join(codici)}")
    testo = "\n".join(righe) + "\n"
    USCITA.write_text(testo, encoding="utf-8")
    return testo


if __name__ == "__main__":
    print("\n".join(scrivi().splitlines()[9:32]))

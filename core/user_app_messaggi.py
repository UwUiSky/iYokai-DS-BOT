"""
core/user_app_messaggi.py
=========================
Logica dei menu sul messaggio di iYokai App (SPEC §B.2): controllo dei link, citazione come immagine,
testo del segnalibro, testo della segnalazione alla rete e istruzioni per l'AI. Funzioni semplici, senza
Discord e senza rete.
Funzioni coperte: SPEC §B.2 (NF-36, #107)
Dipende da: core/phishing_logic.py, core/rank_card_image.py
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from PIL import Image, ImageDraw

from core.ai_testi_logic import ISTRUZIONI, nome_lingua
from core.phishing_logic import domini_nel_testo, e_accorciatore, e_phishing, sembra_phishing
from core.rank_card_image import carica_font, senza_quadrati, taglia_al_largo
from core.safe_image import safe_open_image

MAX_TESTO_SEGNALIBRO = 500
MAX_LINK_CONTROLLATI = 10
MAX_TESTO_AI = 3000
MAX_RIGHE_CITAZIONE = 8
MAX_CARATTERI_CITAZIONE = 400

STATO_LISTA = "lista"
STATO_SOSPETTO = "sospetto"
STATO_ACCORCIATORE = "accorciatore"
STATO_NESSUN_SEGNALE = "nessun_segnale"


@dataclass(frozen=True)
class EsitoLink:
    dominio: str
    stato: str


def testo_segnalibro(contenuto: str) -> str:
    """Il testo del messaggio per il segnalibro: una riga sola, entro 500 caratteri."""
    una_riga = re.sub(r"\s+", " ", contenuto or "").strip()
    return una_riga[:MAX_TESTO_SEGNALIBRO]


def controlla_link(contenuto: str, lista: frozenset[str]) -> list[EsitoLink]:
    """Per ogni dominio nel testo (al massimo 10): nella lista, sospetto, accorciatore o nessun segnale."""
    esiti: list[EsitoLink] = []
    for dominio in dict.fromkeys(domini_nel_testo(contenuto or "")):
        if len(esiti) >= MAX_LINK_CONTROLLATI:
            break
        if e_phishing([dominio], frozenset(lista)) and not sembra_phishing(dominio):
            stato = STATO_LISTA
        elif sembra_phishing(dominio):
            stato = STATO_SOSPETTO
        elif e_accorciatore([dominio]):
            stato = STATO_ACCORCIATORE
        else:
            stato = STATO_NESSUN_SEGNALE
        esiti.append(EsitoLink(dominio, stato))
    return esiti


def istruzioni_ai(funzione: str, lingua: str) -> str:
    """Le istruzioni per tradurre ('traduci') o spiegare ('spiega') nella lingua della persona."""
    base = ISTRUZIONI[funzione]
    return f"{base} Lingua di arrivo: {nome_lingua(lingua)} ({lingua})." if funzione == "traduci" else (
        f"{base} Rispondi in {nome_lingua(lingua)} ({lingua})."
    )


def testo_segnalazione(autore_id: int, autore_nome: str, link: str, contenuto: str, motivo: str) -> str:
    """Il corpo della segnalazione per lo staff della rete: chi, dove, cosa (troncato) e perché."""
    citato = re.sub(r"\s+", " ", contenuto or "").strip()[:700] or "(nessun testo)"
    return (
        f"Autore: {autore_nome[:80]} (ID {autore_id})\nMessaggio: {link}\n"
        f"Testo: {citato}\nMotivo di chi segnala: {motivo[:300]}"
    )


def _righe(draw: ImageDraw.ImageDraw, testo: str, font, larghezza: int) -> list[str]:
    righe: list[str] = []
    attuale = ""
    for parola in testo.split():
        prova = f"{attuale} {parola}".strip()
        if draw.textlength(prova, font=font) <= larghezza:
            attuale = prova
            continue
        if attuale:
            righe.append(attuale)
        attuale = taglia_al_largo(draw, parola, font, larghezza)
    if attuale:
        righe.append(attuale)
    if len(righe) > MAX_RIGHE_CITAZIONE:
        righe = righe[:MAX_RIGHE_CITAZIONE]
        righe[-1] = taglia_al_largo(draw, righe[-1] + " …", font, larghezza)
    return righe


def citazione_png(testo: str, autore: str, avatar: bytes | None = None) -> bytes:
    """L'immagine «citazione»: avatar tondo, testo a capo (al massimo 8 righe) e il nome tra trattini."""
    larghezza, margine, lato = 900, 48, 96
    f_testo, f_autore = carica_font(34), carica_font(26)
    misura = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    pulito = senza_quadrati(re.sub(r"\s+", " ", testo or "").strip()[:MAX_CARATTERI_CITAZIONE], f_testo) or "…"
    righe = _righe(misura, pulito, f_testo, larghezza - 2 * margine)
    altezza = margine * 2 + lato + 24 + len(righe) * 46 + 50
    tela = Image.new("RGB", (larghezza, altezza), (32, 34, 37))
    draw = ImageDraw.Draw(tela)
    foto = Image.new("RGB", (lato, lato), (88, 101, 242))
    if avatar:
        try:
            foto = safe_open_image(avatar).convert("RGB").resize((lato, lato))
        except Exception:  # noqa: BLE001 - file rotto o troppo grande: resta il cerchio pieno
            pass
    maschera = Image.new("L", (lato * 4, lato * 4), 0)
    ImageDraw.Draw(maschera).ellipse((0, 0, lato * 4 - 1, lato * 4 - 1), fill=255)
    tela.paste(foto, (margine, margine), maschera.resize((lato, lato), Image.LANCZOS))
    nome = taglia_al_largo(draw, senza_quadrati(autore[:60], f_autore), f_autore, larghezza - 2 * margine - lato - 24)
    draw.text((margine + lato + 24, margine + lato // 2), f"— {nome}", font=f_autore, fill=(185, 187, 190), anchor="lm")
    y = margine + lato + 24
    for riga in righe:
        draw.text((margine, y), riga, font=f_testo, fill=(255, 255, 255))
        y += 46
    uscita = io.BytesIO()
    tela.save(uscita, format="PNG")
    return uscita.getvalue()

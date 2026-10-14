"""
core/captcha_image.py
=====================
Captcha a immagine: genera il codice, lo disegna storto con un po' di
disturbo e dice se la risposta e' giusta, scaduta o se i tentativi sono finiti.
Funzioni coperte: SPEC §22 (NF-18)

Limiti: immagine piccola (200x80, PNG di pochi KB), codice di 5 caratteri
senza lettere ambigue (0/O, 1/I/L), tempo massimo e tentativi contati dalla sfida.
"""

from __future__ import annotations

import io
import math
import random
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LUNGHEZZA_CODICE = 5
ALFABETO = "ACDEFGHJKMNPQRSTUVWXYZ2345679"  # niente 0/O, 1/I/L, 8/B
LARGHEZZA = 200
ALTEZZA = 80
TEMPO_MASSIMO_SECONDI = 180
TENTATIVI_MASSIMI = 3
ETICHETTA_MAX = 45  # il campo del modulo accetta al massimo 45 caratteri di etichetta

TIPO_TESTO = "testo"
TIPO_IMMAGINE = "immagine"
TIPI = (TIPO_TESTO, TIPO_IMMAGINE)


def genera_codice(rng: secrets.SystemRandom | random.Random | None = None) -> str:
    """Un codice casuale di LUNGHEZZA_CODICE caratteri presi da ALFABETO."""
    rng = rng or secrets.SystemRandom()
    return "".join(rng.choice(ALFABETO) for _ in range(LUNGHEZZA_CODICE))


def normalizza_risposta(testo: str) -> str:
    """Maiuscole e senza spazi: l'utente puo' scrivere «ab c12»."""
    return "".join(testo.split()).upper()


def risposta_giusta(atteso: str, data: str) -> bool:
    # compare_digest su str accetta solo ASCII: una «e» accentata nella risposta darebbe TypeError.
    return secrets.compare_digest(normalizza_risposta(data).encode("utf-8"), atteso.upper().encode("utf-8"))


def disegna_immagine(codice: str, rng: random.Random | None = None) -> bytes:
    """PNG con le lettere ruotate e spostate, linee e punti di disturbo, leggero sfocato."""
    rng = rng or random.Random()
    base = Image.new("RGB", (LARGHEZZA, ALTEZZA), (rng.randint(215, 245),) * 3)
    disegno = ImageDraw.Draw(base)
    for _ in range(6):  # linee sotto le lettere
        disegno.line(
            [(rng.randint(0, LARGHEZZA), rng.randint(0, ALTEZZA)), (rng.randint(0, LARGHEZZA), rng.randint(0, ALTEZZA))],
            fill=tuple(rng.randint(120, 200) for _ in range(3)), width=rng.randint(1, 2),
        )
    font = ImageFont.load_default(size=44)
    passo = LARGHEZZA // (len(codice) + 1)
    for i, carattere in enumerate(codice):
        lettera = Image.new("RGBA", (60, 70), (0, 0, 0, 0))
        ImageDraw.Draw(lettera).text(
            (12, 8), carattere, font=font, fill=tuple(rng.randint(10, 110) for _ in range(3)) + (255,)
        )
        lettera = lettera.rotate(rng.uniform(-28, 28), resample=Image.BICUBIC, expand=False)
        base.paste(lettera, (passo // 2 + i * passo - 6, rng.randint(-2, 8)), lettera)
    for _ in range(180):  # punti di disturbo
        disegno.point((rng.randint(0, LARGHEZZA - 1), rng.randint(0, ALTEZZA - 1)), fill=(rng.randint(0, 150),) * 3)
    for _ in range(3):  # linee sopra le lettere
        y = rng.randint(10, ALTEZZA - 10)
        disegno.line(
            [(0, y), (LARGHEZZA, y + rng.randint(-15, 15))], fill=tuple(rng.randint(40, 120) for _ in range(3)), width=1
        )
    base = _onda(base, rng).filter(ImageFilter.GaussianBlur(0.6))
    uscita = io.BytesIO()
    base.save(uscita, format="PNG", optimize=True)
    return uscita.getvalue()


def _onda(immagine: Image.Image, rng: random.Random) -> Image.Image:
    """Piega l'immagine con un'onda leggera: le lettere restano leggibili ma non uguali tra loro."""
    ampiezza, fase = rng.uniform(2.0, 3.5), rng.uniform(0, math.tau)
    risultato = Image.new("RGB", immagine.size, (235, 235, 235))
    for x in range(immagine.width):
        scarto = int(ampiezza * math.sin(x / 14 + fase))
        risultato.paste(immagine.crop((x, 0, x + 1, immagine.height)), (x, scarto))
    return risultato


@dataclass
class Sfida:
    """Una prova aperta per un utente: il codice, quando scade, quanti tentativi restano."""

    codice: str
    scade_il: datetime
    tentativi_rimasti: int = TENTATIVI_MASSIMI
    chiusa: bool = field(default=False)

    def scaduta(self, adesso: datetime | None = None) -> bool:
        return (adesso or datetime.now(timezone.utc)) >= self.scade_il

    def prova(self, risposta: str, adesso: datetime | None = None) -> str:
        """'ok' | 'sbagliata' (ne restano altre) | 'esaurita' | 'scaduta'. Chiude la sfida a ok, esaurita, scaduta."""
        if self.chiusa or self.scaduta(adesso):
            self.chiusa = True
            return "scaduta"
        if risposta_giusta(self.codice, risposta):
            self.chiusa = True
            return "ok"
        self.tentativi_rimasti -= 1
        if self.tentativi_rimasti <= 0:
            self.chiusa = True
            return "esaurita"
        return "sbagliata"


def nuova_sfida(adesso: datetime | None = None, rng=None) -> Sfida:
    adesso = adesso or datetime.now(timezone.utc)
    return Sfida(genera_codice(rng), adesso + timedelta(seconds=TEMPO_MASSIMO_SECONDI))

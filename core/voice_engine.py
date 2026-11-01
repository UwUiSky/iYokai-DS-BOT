"""
core/voice_engine.py
====================
Il motore della voce di Yokai dietro un'interfaccia sola: riceve frasi e un profilo, restituisce un WAV già filtrato.
Motore di partenza: Piper (voce italiana Paola) via sherpa-onnx, sul processore, in un thread a parte. Si accende
solo se `VOCE_MODELLO_DIR` indica la cartella del modello; cambiare motore non tocca il resto.
Funzioni coperte: SPEC §14.19, §25.102 (AI-R-109, D22, D44)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import wave
from pathlib import Path
from typing import Mapping, Protocol

from core.voice_audio import filtra
from core.voice_profile import VoiceProfile

logger = logging.getLogger("iyokai.voce")

NOME_FILE_MODELLO = "it_IT-paola-medium.onnx"


class MotoreVoce(Protocol):
    nome: str
    versione: str

    async def sintetizza(self, frasi: list[str], profilo: VoiceProfile) -> bytes: ...


def catena_filtri(p: VoiceProfile) -> str:
    """Il filtro Yokai: più corpo, meno naso, più presenza e aria, compressione leggera (valori di scripts/prova_voce.py)."""
    return ",".join([
        "highpass=f=80",
        f"equalizer=f=220:t=q:w=0.8:g={p.calore}",
        f"equalizer=f=1000:t=q:w=1.2:g={p.naso}",
        f"equalizer=f=4500:t=q:w=1.0:g={p.presenza}",
        f"highshelf=f=7000:g={p.aria}",
        f"acompressor=threshold=-22dB:ratio={p.vicinanza}:attack=6:release=140:makeup=2",
        "loudnorm=I=-16:TP=-1.5",
    ])


def wav_da_campioni(campioni, frequenza: int) -> bytes:
    import array

    pcm = array.array("h", (max(-32768, min(32767, int(x * 32767))) for x in campioni))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frequenza)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class MotoreSherpa:
    """Piper (Paola) con sherpa-onnx. Il modello si carica al primo uso e resta in memoria per profilo."""

    nome = "piper-paola"

    def __init__(self, cartella: Path, versione: str = "paola-1") -> None:
        self.cartella = cartella
        self.versione = versione
        self._motori: dict[tuple, object] = {}

    def _motore(self, p: VoiceProfile):
        import sherpa_onnx

        chiave = (p.variazione, p.ritmo, p.lentezza)
        if chiave not in self._motori:
            m = str(self.cartella)
            cfg = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=str(Path(m, NOME_FILE_MODELLO)), tokens=str(Path(m, "tokens.txt")), data_dir=str(Path(m, "espeak-ng-data")),
                        noise_scale=p.variazione, noise_scale_w=p.ritmo, length_scale=p.lentezza,
                    ),
                    num_threads=2, provider="cpu",
                ),
                max_num_sentences=1,
            )
            self._motori[chiave] = sherpa_onnx.OfflineTts(cfg)
        return self._motori[chiave]

    def _grezzo(self, frasi: list[str], p: VoiceProfile) -> bytes:
        tts = self._motore(p)
        campioni: list[float] = []
        frequenza = 22050
        for f in frasi:
            audio = tts.generate(f, sid=0, speed=1.0)
            frequenza = audio.sample_rate
            campioni.extend(audio.samples)
            campioni.extend([0.0] * int(frequenza * p.pause / 1000))
        return wav_da_campioni(campioni, frequenza)

    async def sintetizza(self, frasi: list[str], profilo: VoiceProfile) -> bytes:
        grezzo = await asyncio.to_thread(self._grezzo, frasi, profilo)  # lavoro pesante: fuori dal ciclo principale
        return await filtra(grezzo, catena_filtri(profilo))


def leggi_motore(env: Mapping[str, str] | None = None) -> MotoreVoce | None:
    """Il motore configurato, o None: la voce resta spenta e il bot manda solo il testo."""
    env = os.environ if env is None else env
    if (env.get("VOCE_ATTIVA") or "").strip().lower() == "no":
        return None
    cartella = (env.get("VOCE_MODELLO_DIR") or "").strip()
    if not cartella:
        return None
    percorso = Path(cartella)
    if not (percorso / NOME_FILE_MODELLO).is_file() or not (percorso / "tokens.txt").is_file():
        logger.warning("VOCE_MODELLO_DIR non contiene il modello: la voce resta spenta.")
        return None
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        logger.warning("sherpa-onnx non è installato: la voce resta spenta.")
        return None
    return MotoreSherpa(percorso, (env.get("VOCE_VERSIONE") or "paola-1").strip() or "paola-1")

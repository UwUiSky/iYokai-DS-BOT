"""
scripts/prova_voce.py
=====================
Prova a mano la voce di Yokai con Kokoro-82M, voce italiana "if_sara"
(D22, issue #142, revisione/02-piano/VOCE_YOKAI.md). Tutto in locale,
sul processore. Non fa parte del bot: serve a regolare i profili.

Preparazione, una volta sola:
    pip install kokoro-onnx soundfile numpy
    curl -L -O https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    curl -L -O https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

Uso:
    python3 scripts/prova_voce.py                      # un campione per ogni contesto
    python3 scripts/prova_voce.py --contesto WELCOME "Benvenuta! Dai, vieni a vedere."

Scrive yokai_<contesto>.wav e, se c'è ffmpeg, anche .mp3.
"""

import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass, replace

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro


@dataclass(frozen=True)
class VoiceProfile:
    """Come parla Yokai in un contesto. Il timbro (voice) non cambia mai."""

    voice: str = "if_sara"
    speed: float = 1.0      # 1.0 = parlato normale
    pitch: float = 0.0      # semitoni; restare tra -1 e +1
    volume: float = 0.0     # decibel
    pause: int = 260        # millisecondi tra una frase e l'altra
    style: str = "PUBLIC"


BASE = VoiceProfile()
PROFILI = {
    "PUBLIC": replace(BASE, speed=1.03, pause=230, style="PUBLIC"),
    "WELCOME": replace(BASE, speed=1.0, pause=260, style="WELCOME"),
    "MODERATION": replace(BASE, speed=0.96, pitch=-0.5, pause=380, style="MODERATION"),
    "ANNOUNCEMENT": replace(BASE, speed=0.98, volume=1.0, pause=320, style="ANNOUNCEMENT"),
    "NSFW": replace(BASE, speed=0.94, pitch=-0.3, pause=340, style="NSFW"),
}

ESEMPI = {
    "PUBLIC": "Oh, guarda chi si è fatto vedere! Bentornato nel server. Allora, che mi racconti di bello?",
    "WELCOME": "Benvenuta nel server! Dai, vieni a dare un'occhiata in giro. Se ti perdi, chiamami.",
    "MODERATION": "Attenzione. Questo comportamento non è consentito in questo server. Ti invito a interromperlo.",
    "ANNOUNCEMENT": "Annuncio importante. Stasera, alle nove, serata giochi nel canale vocale. Vi aspetto tutti.",
    "NSFW": "Sei ancora sveglio, a quest'ora? Allora resta un altro po' con me. Non ho nessuna fretta.",
}


def frasi(testo: str) -> list[str]:
    """Divide il testo in frasi: ognuna viene detta da sola, con una pausa dopo."""
    pezzi = re.split(r"(?<=[.!?…])\s+", testo.strip())
    return [p for p in pezzi if p]


def sintetizza(motore: Kokoro, testo: str, profilo: VoiceProfile) -> tuple[np.ndarray, int]:
    pezzi, frequenza = [], 24000
    for frase in frasi(testo):
        audio, frequenza = motore.create(frase, voice=profilo.voice, speed=profilo.speed, lang="it")
        pezzi.append(np.asarray(audio, dtype=np.float32))
        pezzi.append(np.zeros(int(frequenza * profilo.pause / 1000), dtype=np.float32))
    return np.concatenate(pezzi), frequenza


def salva(nome: str, audio: np.ndarray, frequenza: int, profilo: VoiceProfile) -> None:
    sf.write(f"{nome}.wav", audio, frequenza)
    print(nome, round(len(audio) / frequenza, 1), "s")
    if shutil.which("ffmpeg") is None:
        return
    filtri = []
    if profilo.pitch:
        k = 2 ** (profilo.pitch / 12)
        filtri += [f"asetrate={int(frequenza * k)}", f"aresample={frequenza}", f"atempo={1 / k:.5f}"]
    filtri += ["loudnorm=I=-16", f"volume={profilo.volume}dB"]
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", f"{nome}.wav", "-af", ",".join(filtri),
         "-codec:a", "libmp3lame", "-q:a", "3", f"{nome}.mp3"],
        check=True,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Prova la voce di Yokai con Kokoro.")
    p.add_argument("testo", nargs="?", help="se manca, un esempio per ogni contesto")
    p.add_argument("--contesto", choices=sorted(PROFILI), default="PUBLIC")
    p.add_argument("--modello", default="kokoro-v1.0.onnx")
    p.add_argument("--voci", default="voices-v1.0.bin")
    a = p.parse_args()
    motore = Kokoro(a.modello, a.voci)
    lavori = [(a.contesto, a.testo)] if a.testo else list(ESEMPI.items())
    for contesto, testo in lavori:
        audio, frequenza = sintetizza(motore, testo, PROFILI[contesto])
        salva(f"yokai_{contesto.lower()}", audio, frequenza, PROFILI[contesto])


if __name__ == "__main__":
    main()

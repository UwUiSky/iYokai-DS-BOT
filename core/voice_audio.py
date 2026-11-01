"""
core/voice_audio.py
===================
Dal suono della sintesi al vocale di Discord: OGG Opus 48 kHz mono, durata e forma d'onda (256 punti, base64).
Usa ffmpeg; il calcolo della forma d'onda è puro.
Funzioni coperte: SPEC §14.19, §25.102 (AI-R-109)
"""

from __future__ import annotations

import array
import asyncio
import base64

PUNTI_ONDA = 256
FREQ_ONDA = 8000
MAX_SECONDI = 120  # un messaggio vocale di Discord dura al massimo 2 minuti


class ErroreAudio(Exception):
    pass


def forma_onda(pcm16: bytes, punti: int = PUNTI_ONDA) -> str:
    """256 valori 0-255 (ampiezza massima per tratto) in base64, come vuole Discord."""
    campioni = array.array("h")
    campioni.frombytes(pcm16[: len(pcm16) - len(pcm16) % 2])
    if not campioni:
        return base64.b64encode(bytes(punti)).decode()
    passo = max(1, len(campioni) // punti)
    valori = bytearray()
    for i in range(punti):
        tratto = campioni[i * passo : (i + 1) * passo] or campioni[-1:]
        valori.append(min(255, int(max(abs(x) for x in tratto) / 32768 * 255 * 1.6)))
    return base64.b64encode(bytes(valori)).decode()


async def _ffmpeg(args: list[str], ingresso: bytes, timeout: float = 60) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", *args,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        fuori, errore = await asyncio.wait_for(proc.communicate(ingresso), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise ErroreAudio("ffmpeg troppo lento")
    if proc.returncode != 0 or not fuori:
        raise ErroreAudio(errore.decode(errors="replace")[:200] or "ffmpeg fallito")
    return fuori


async def a_ogg_opus(audio: bytes) -> tuple[bytes, float, str]:
    """(ogg, durata in secondi, forma d'onda) da un file audio qualunque (WAV della sintesi)."""
    ogg = await _ffmpeg(["-i", "pipe:0", "-t", str(MAX_SECONDI), "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", "-f", "ogg", "pipe:1"], audio)
    pcm = await _ffmpeg(["-i", "pipe:0", "-t", str(MAX_SECONDI), "-ac", "1", "-ar", str(FREQ_ONDA), "-f", "s16le", "pipe:1"], audio)
    return ogg, round(len(pcm) / 2 / FREQ_ONDA, 2), forma_onda(pcm)


async def filtra(wav: bytes, catena: str) -> bytes:
    """Il filtro Yokai (equalizzazione, compressione, volume) sul WAV della sintesi."""
    return await _ffmpeg(["-i", "pipe:0", "-af", catena, "-f", "wav", "pipe:1"], wav)

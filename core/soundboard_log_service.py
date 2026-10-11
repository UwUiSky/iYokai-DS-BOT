"""
core/soundboard_log_service.py
==================================
Il log dei suoni soundboard (SPEC.md §8.13) ora arriva dagli eventi
gateway di discord.py (`on_soundboard_sound_create/update/delete`),
ascoltati da cogs/logging/advanced_logs.py: non serve più leggere
l'audit log ogni 5 minuti. Questo servizio resta come segnaposto senza
ciclo, così main.py continua a poterlo avviare e fermare; si può togliere
da main.py quando si vuole.
Funzioni coperte: SPEC §8.13, LIM-31
"""

from __future__ import annotations

from discord.ext import commands, tasks


class SoundboardLogService:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    def start(self, bot: commands.Bot) -> None:
        """Niente da avviare: gli eventi arrivano dal gateway."""


soundboard_log_service = SoundboardLogService()

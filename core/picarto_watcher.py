"""
core/picarto_watcher.py
=======================
Controlla le dirette su Picarto (ALR-008): stesso schema di core/kick_watcher.py. L'interfaccia pubblica di
Picarto non ha chiavi né richieste a gruppi: una richiesta per canale (uguale per più server), al massimo 40 per
giro a rotazione, con al massimo 4 insieme. Ogni richiesta passa da `core/safe_http.py`.
Si avvia dal cog (cogs/utility/alert_piattaforme.py). Funzioni coperte: SPEC §10.13 (#129 ALR-008)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from discord.ext import commands, tasks

from core.alert_frequenze_logic import intervallo
from core.alert_messaggio_logic import pulisci_esterno
from core.alert_options_logic import AlertOptions
from core.bot_ready import attendi_bot_pronto
from core.feed_alert_gate import AvvisoUnaVolta, filtra_attive
from core.live_alert_flow import carica_contesto, pubblica_cambio_live
from core.repositories.picarto_subscription_repo import picarto_subscription_repo
from core.safe_http import safe_get
from core.template_renderer import render_template

logger = logging.getLogger("iyokai.picarto_watcher")

KIND = "PC"
URL_CANALE = "https://api.picarto.tv/api/v1/channel/name/{nome}"
MAX_RICHIESTE_PER_GIRO = 40
RICHIESTE_INSIEME = 4


@dataclass(frozen=True)
class StatoPicarto:
    nome: str
    in_diretta: bool
    titolo: str = ""
    categoria: str = ""


def leggi_canale(testo: str | None, nome: str) -> StatoPicarto | None:
    """Lo stato dal JSON di Picarto; None se la risposta non si capisce (il giro lo salta, lo stato non cambia)."""
    try:
        dati = json.loads(testo or "")
    except ValueError:
        return None
    if not isinstance(dati, dict) or not isinstance(dati.get("online"), bool):
        return None
    categorie = dati.get("category")
    prima = categorie[0] if isinstance(categorie, list) and categorie and isinstance(categorie[0], str) else ""
    titolo = dati.get("title") if isinstance(dati.get("title"), str) else ""
    return StatoPicarto(nome, dati["online"], pulisci_esterno(titolo), pulisci_esterno(prima, 100))


class PicartoWatcherService:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None
        self._avvisi = AvvisoUnaVolta()
        self._rotazione = 0

    async def _leggi(self, nome: str) -> StatoPicarto | None:
        return leggi_canale(await safe_get(URL_CANALE.format(nome=nome), max_bytes=300_000), nome)

    async def tick(self, bot: commands.Bot) -> None:
        sottoscrizioni = await filtra_attive(await picarto_subscription_repo.get_all_subscriptions())
        if not sottoscrizioni:
            return
        nomi = list(dict.fromkeys(s.picarto_name.lower() for s in sottoscrizioni))
        if len(nomi) > MAX_RICHIESTE_PER_GIRO:  # a rotazione: nessun canale resta fuori per sempre
            inizio = self._rotazione % len(nomi)
            nomi = (nomi[inizio:] + nomi[:inizio])[:MAX_RICHIESTE_PER_GIRO]
            self._rotazione += MAX_RICHIESTE_PER_GIRO
        semaforo = asyncio.Semaphore(RICHIESTE_INSIEME)

        async def una(nome: str):
            async with semaforo:
                try:
                    return nome, await self._leggi(nome)
                except Exception:
                    logger.exception("Lettura Picarto fallita per un canale")
                    return nome, None

        stati = {n: s for n, s in await asyncio.gather(*(una(n) for n in nomi)) if s is not None}
        opzioni, ruoli = await carica_contesto(KIND, sottoscrizioni)
        for sub in sottoscrizioni:
            stato = stati.get(sub.picarto_name.lower())
            if stato is None or stato.in_diretta == sub.last_known_live:
                continue
            valori = None
            if stato.in_diretta:
                valori = {"label": sub.label, "title": stato.titolo, "login": sub.picarto_name,
                          "game": stato.categoria, "gioco": stato.categoria,
                          "descrizione": f"🎨 {stato.categoria}" if stato.categoria else ""}
                testo = render_template(sub.live_message_template, valori)
            else:
                testo = render_template(sub.offline_message_template, {"label": sub.label, "login": sub.picarto_name})
            await pubblica_cambio_live(
                bot, sub, KIND, in_diretta=stato.in_diretta, testo=testo,
                url=f"https://picarto.tv/{sub.picarto_name}", opz=opzioni.get(sub.id, AlertOptions()),
                ruolo_live_id=ruoli.get(sub.guild_id), repo_stato=picarto_subscription_repo,
                avvisi=self._avvisi, nome="Picarto", titolo=stato.titolo, gioco=stato.categoria, valori=valori,
            )

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=intervallo("picarto"))
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del Picarto watcher")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Picarto watcher avviato (controllo ogni %ds).", intervallo("picarto"))

    def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            self._loop_task = None


picarto_watcher = PicartoWatcherService()

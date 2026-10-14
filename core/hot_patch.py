"""
core/hot_patch.py
=================
Aggiornamento a caldo del bot, riservato al proprietario (#141, D21, SPEC §17.11). Due sorgenti: i file cambiati di un
commit di `main` su GitHub, oppure file allegati dal proprietario (un `.py` per un cog, o uno `.zip`).
Regole di sicurezza:
- solo file `.py` dentro `cogs/` e `core/` (mai `main.py`, mai fuori dalle due cartelle, mai `..`);
- il codice si compila prima di toccare un file; se non compila non cambia niente;
- ogni file sostituito ha la sua copia in `data/hot_patch/<data>/`; se un cog non si ricarica si rimettono tutte
  le copie e si ricaricano i cog di prima;
- ogni tentativo finisce nel registro (`hot_patch_log`): chi, quando, quali file, quale commit;
- un cambio a `core/` non si carica a caldo: il bot dice che serve il riavvio.
Da GitHub si prende solo un commit che sta nella storia di `main`.
Funzioni coperte: SPEC §17.11
Dipende da: core/repositories/hot_patch_log_repo.py, core/migrations/0134_registro_aggiornamenti.sql
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import io
import logging
import os
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

logger = logging.getLogger("iyokai.hot_patch")

RADICE = Path(__file__).resolve().parent.parent
CARTELLE_AMMESSE = ("cogs", "core")
# Il file che fa l'aggiornamento non si aggiorna da solo.
FILE_VIETATI = frozenset({"core/hot_patch.py"})
MAX_BYTE_FILE = 512 * 1024
MAX_FILE = 30
MAX_BYTE_ZIP_DECOMPRESSO = 4 * 1024 * 1024
TIMEOUT_GITHUB_SECONDI = 20
_SEGMENTO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RIFERIMENTO = re.compile(r"^(main|[0-9a-fA-F]{7,40})$")


class PatchRifiutata(ValueError):
    """L'aggiornamento non si fa. Il testo è per il proprietario (nessun segreto dentro)."""


# ----------------------------------------------------------------------
# Percorsi
# ----------------------------------------------------------------------
def valida_percorso(percorso: str) -> str:
    """Il percorso normalizzato (con `/`) se è un `.py` dentro `cogs/` o `core/`; altrimenti `PatchRifiutata`."""
    pulito = percorso.replace("\\", "/").strip()
    parti = pulito.split("/")
    if (
        not pulito
        or pulito.startswith("/")
        or len(parti) < 2
        or parti[0] not in CARTELLE_AMMESSE
        or not pulito.endswith(".py")
        or any(p in ("", ".", "..") for p in parti)
    ):
        raise PatchRifiutata(f"Percorso non ammesso: `{pulito[:80]}` (solo file .py in cogs/ e core/).")
    # fullmatch: con `match` e `$` un «\n» in coda al nome passerebbe.
    if not all(_SEGMENTO.fullmatch(p[:-3] if i == len(parti) - 1 else p) for i, p in enumerate(parti)):
        raise PatchRifiutata(f"Percorso non ammesso: `{pulito[:80]}` (nomi non validi).")
    if pulito in FILE_VIETATI:
        raise PatchRifiutata(f"`{pulito}` non si aggiorna a caldo.")
    return pulito


def modulo_a_percorso(modulo: str) -> str:
    """`cogs.utility.ping` diventa `cogs/utility/ping.py`."""
    return valida_percorso(modulo.strip().replace(".", "/") + ".py")


def percorso_a_modulo(percorso: str) -> str:
    return valida_percorso(percorso)[:-3].replace("/", ".")


# ----------------------------------------------------------------------
# Pacchetti di file
# ----------------------------------------------------------------------
def pacchetto_da_file(modulo: str, dati: bytes) -> dict[str, bytes]:
    """Un solo file allegato, per il modulo indicato."""
    return {modulo_a_percorso(modulo): dati}


def pacchetto_da_zip(dati: bytes) -> dict[str, bytes]:
    """Legge uno `.zip` con file `.py` nei percorsi `cogs/...` e `core/...`. Rifiuta qualsiasi altro contenuto."""
    try:
        archivio = zipfile.ZipFile(io.BytesIO(dati))
    except zipfile.BadZipFile as exc:
        raise PatchRifiutata("L'allegato non è un file zip valido.") from exc
    voci = [v for v in archivio.infolist() if not v.is_dir()]
    if not voci:
        raise PatchRifiutata("Lo zip è vuoto.")
    if len(voci) > MAX_FILE:
        raise PatchRifiutata(f"Troppi file nello zip: il massimo è {MAX_FILE}.")
    if sum(v.file_size for v in voci) > MAX_BYTE_ZIP_DECOMPRESSO:
        raise PatchRifiutata("Lo zip, una volta aperto, è troppo grande.")
    pacchetto: dict[str, bytes] = {}
    for voce in voci:
        percorso = valida_percorso(voce.filename)
        if voce.file_size > MAX_BYTE_FILE:
            raise PatchRifiutata(f"`{percorso}` è troppo grande (massimo {MAX_BYTE_FILE // 1024} KiB).")
        pacchetto[percorso] = archivio.read(voce)
    return pacchetto


def controlla_pacchetto(pacchetto: dict[str, bytes]) -> None:
    """Percorsi ammessi, dimensioni nei limiti, e il codice compila. Non scrive niente."""
    if not pacchetto:
        raise PatchRifiutata("Non c'è nessun file da aggiornare.")
    if len(pacchetto) > MAX_FILE:
        raise PatchRifiutata(f"Troppi file: il massimo è {MAX_FILE}.")
    for percorso, dati in pacchetto.items():
        valida_percorso(percorso)
        if len(dati) > MAX_BYTE_FILE:
            raise PatchRifiutata(f"`{percorso}` è troppo grande (massimo {MAX_BYTE_FILE // 1024} KiB).")
        try:
            compile(dati, percorso, "exec")
        except (SyntaxError, ValueError) as exc:
            riga = getattr(exc, "lineno", None)
            raise PatchRifiutata(f"`{percorso}` non compila{f' (riga {riga})' if riga else ''}: nessun file è stato toccato.") from exc


# ----------------------------------------------------------------------
# Scrittura con copia
# ----------------------------------------------------------------------
@dataclass
class Copie:
    cartella: Path
    # percorso -> file di copia (None = il file non esisteva)
    originali: dict[str, Path | None] = field(default_factory=dict)


def scrivi_con_copia(pacchetto: dict[str, bytes], radice: Path, cartella_copie: Path) -> Copie:
    """Mette da parte i file vecchi e scrive i nuovi (prima in un file temporaneo, poi lo scambio)."""
    copie = Copie(cartella=cartella_copie)
    try:
        for percorso, dati in pacchetto.items():
            destinazione = radice / percorso
            if destinazione.exists():
                copia = cartella_copie / percorso
                copia.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destinazione, copia)
                copie.originali[percorso] = copia
            else:
                copie.originali[percorso] = None
            destinazione.parent.mkdir(parents=True, exist_ok=True)
            temporaneo = destinazione.with_name(destinazione.name + ".nuovo")
            temporaneo.write_bytes(dati)
            os.replace(temporaneo, destinazione)
    except Exception:
        ripristina(copie, radice)
        raise
    return copie


def ripristina(copie: Copie, radice: Path) -> None:
    """Rimette i file com'erano; toglie quelli che prima non c'erano."""
    for percorso, copia in copie.originali.items():
        destinazione = radice / percorso
        if copia is None:
            destinazione.unlink(missing_ok=True)
        else:
            shutil.copy2(copia, destinazione)


# ----------------------------------------------------------------------
# Applicazione
# ----------------------------------------------------------------------
@dataclass
class EsitoPatch:
    esito: str  # ok | ripristinato | rifiutato
    file: list[str] = field(default_factory=list)
    ricaricati: list[str] = field(default_factory=list)
    riavvio_necessario: bool = False
    errori: dict[str, str] = field(default_factory=dict)
    nota: str = ""


# Due aggiornamenti insieme si scambierebbero le copie: la seconda copia sarebbe già il file nuovo.
_blocco = asyncio.Lock()


def e_estensione(dati: bytes) -> bool:
    """True se il file ha `setup` al livello più alto (un cog); gli altri file di `cogs/` sono moduli d'appoggio."""
    try:
        albero = ast.parse(dati)
    except (SyntaxError, ValueError):
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "setup" for n in albero.body)


def _dipendenti(bot, modulo: str, scartati: set[str], radice: Path) -> list[str]:
    """I cog caricati che nominano un modulo d'appoggio (sono da ricaricare, sennò tengono il codice vecchio)."""
    ultimo = modulo.rsplit(".", 1)[-1]
    trovati = []
    for nome in sorted(bot.extensions):
        if nome in scartati or not nome.startswith("cogs."):
            continue
        try:
            testo = (radice / (nome.replace(".", "/") + ".py")).read_text(encoding="utf-8")
        except OSError:
            continue
        if modulo in testo or re.search(rf"\b{re.escape(ultimo)}\b", testo):
            trovati.append(nome)
    return trovati


async def _ricarica(bot, modulo: str) -> None:
    if modulo in bot.extensions:
        await bot.reload_extension(modulo)
    else:
        await bot.load_extension(modulo)


async def applica_patch(bot, pacchetto: dict[str, bytes], **kw) -> "EsitoPatch":
    """Un aggiornamento alla volta (vedi `_applica`)."""
    async with _blocco:
        return await _applica(bot, pacchetto, **kw)


async def _applica(
    bot,
    pacchetto: dict[str, bytes],
    *,
    sorgente: str,
    applicato_da: int,
    commit: str | None = None,
    radice: Path = RADICE,
    cartella_copie: Path | None = None,
    registro=None,
) -> EsitoPatch:
    """
    Controlla, scrive con copia e ricarica i cog cambiati. Se un cog non si ricarica rimette TUTTE le copie e
    ricarica i cog di prima. Registra sempre l'esito. Non solleva `PatchRifiutata`: lo mette nell'esito.
    """
    if registro is None:
        from core.repositories.hot_patch_log_repo import hot_patch_log_repo as registro

    elenco = sorted(pacchetto)
    try:
        controlla_pacchetto(pacchetto)
    except PatchRifiutata as exc:
        await registro.registra(applicato_da, sorgente, commit, elenco, "rifiutato", False, str(exc))
        return EsitoPatch("rifiutato", elenco, nota=str(exc))

    cartella = cartella_copie or radice / "data" / "hot_patch" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    copie = scrivi_con_copia(pacchetto, radice, cartella)
    tutti = sorted(percorso_a_modulo(p) for p in pacchetto if p.startswith("cogs/"))
    # Un file di `cogs/` senza `setup` (viste, logica) non è un cog: caricarlo farebbe fallire tutto l'aggiornamento.
    appoggio = [m for m in tutti if m not in bot.extensions and not e_estensione(pacchetto[m.replace(".", "/") + ".py"])]
    for m in appoggio:
        sys.modules.pop(m, None)
        importlib.invalidate_caches()
    moduli = sorted({m for m in tutti if m not in appoggio} | {d for m in appoggio for d in _dipendenti(bot, m, set(tutti), radice)})
    riavvio = any(p.startswith("core/") for p in pacchetto)
    caricati_prima = {m for m in moduli if m in bot.extensions}

    ricaricati: list[str] = []
    errori: dict[str, str] = {}
    for modulo in moduli:
        try:
            await _ricarica(bot, modulo)
            ricaricati.append(modulo)
        except Exception as exc:  # noqa: BLE001 - qualunque errore del cog nuovo fa tornare indietro
            errori[modulo] = f"{type(exc).__name__}: {str(exc)[:150]}"
            break

    if errori:
        ripristina(copie, radice)
        for modulo in ricaricati:
            try:
                if modulo in caricati_prima:
                    await bot.reload_extension(modulo)
                else:
                    await bot.unload_extension(modulo)
            except Exception as exc:  # noqa: BLE001 - si dice all'owner che il cog di prima non è tornato
                errori[modulo + " (ripristino)"] = f"{type(exc).__name__}: {str(exc)[:150]}"
        nota = "Un cog non si è caricato: i file di prima sono stati rimessi."
        await registro.registra(applicato_da, sorgente, commit, elenco, "ripristinato", False, "; ".join(errori)[:500])
        return EsitoPatch("ripristinato", elenco, [], False, errori, nota)

    await registro.registra(applicato_da, sorgente, commit, elenco, "ok", riavvio, None)
    logger.info("Aggiornamento a caldo (%s): %d file, %d cog ricaricati.", sorgente, len(elenco), len(ricaricati))
    return EsitoPatch("ok", elenco, ricaricati, riavvio)


# ----------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------
class ClienteGitHub:
    """Lettura di un repository GitHub. Solo `api.github.com`; il token (se c'è) non esce mai nei messaggi."""

    BASE = "https://api.github.com"

    def __init__(self, sessione: aiohttp.ClientSession, repo: str, token: str = "") -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise PatchRifiutata("HOT_PATCH_REPO non è nel formato proprietario/repository.")
        self._sessione = sessione
        self._repo = repo
        self._token = token

    def _intestazioni(self, raw: bool = False) -> dict[str, str]:
        h = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json", "User-Agent": "iyokai-bot"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def _get(self, percorso: str, *, raw: bool = False, parametri: dict | None = None):
        url = f"{self.BASE}/repos/{self._repo}/{percorso}"
        try:
            async with self._sessione.get(
                url, headers=self._intestazioni(raw), params=parametri,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_GITHUB_SECONDI),
            ) as risposta:
                if risposta.status == 404:
                    raise PatchRifiutata("GitHub non trova il commit o il file (repository privato senza token?).")
                if risposta.status in (401, 403):
                    raise PatchRifiutata("GitHub ha rifiutato l'accesso (token mancante, scaduto o limite raggiunto).")
                if risposta.status != 200:
                    raise PatchRifiutata(f"GitHub ha risposto con errore {risposta.status}.")
                if raw:
                    if (risposta.content_length or 0) > MAX_BYTE_FILE:
                        raise PatchRifiutata("Un file del commit è troppo grande.")
                    dati = await risposta.content.read(MAX_BYTE_FILE + 1)
                    if len(dati) > MAX_BYTE_FILE:
                        raise PatchRifiutata("Un file del commit è troppo grande.")
                    return dati
                return await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise PatchRifiutata("GitHub non risponde: riprova tra poco.") from exc

    async def risolvi(self, riferimento: str) -> str:
        """Lo SHA completo di `main` o di un commit."""
        if not _RIFERIMENTO.match(riferimento):
            raise PatchRifiutata("Scrivi `main` oppure lo SHA del commit (da 7 a 40 caratteri).")
        dati = await self._get(f"commits/{riferimento}")
        sha = dati.get("sha", "") if isinstance(dati, dict) else ""
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise PatchRifiutata("GitHub ha risposto in un formato inatteso.")
        return sha

    async def sta_in_main(self, sha: str) -> bool:
        """True se il commit sta nella storia di `main` (o è `main`)."""
        dati = await self._get(f"compare/{sha}...main")
        return isinstance(dati, dict) and dati.get("status") in ("ahead", "identical")

    async def file_cambiati(self, base: str, testa: str) -> list[str]:
        """I file aggiunti o modificati tra `base` e `testa`. Sopra i 300 file GitHub taglia: si rifiuta."""
        dati = await self._get(f"compare/{base}...{testa}")
        if not isinstance(dati, dict):
            raise PatchRifiutata("GitHub ha risposto in un formato inatteso.")
        file = dati.get("files", [])
        if len(file) >= 300:
            raise PatchRifiutata("Troppi file cambiati tra i due commit.")
        return [f["filename"] for f in file if f.get("status") in ("added", "modified", "renamed", "changed")]

    async def scarica(self, percorso: str, sha: str) -> bytes:
        return await self._get(f"contents/{percorso}", raw=True, parametri={"ref": sha})


async def pacchetto_da_github(
    cliente: ClienteGitHub, riferimento: str, base: str | None, solo: str | None = None
) -> tuple[dict[str, bytes], str, int]:
    """
    I file `.py` di `cogs/` e `core/` cambiati tra `base` (il commit che gira ora) e il commit scelto; con `solo`
    (un percorso) si prende quel file e basta. Restituisce (pacchetto, sha completo, quanti file ignorati perché
    fuori dalle cartelle ammesse).
    """
    sha = await cliente.risolvi(riferimento)
    if not await cliente.sta_in_main(sha):
        raise PatchRifiutata("Questo commit non è nella storia di `main`: da GitHub si prende solo da `main`.")
    if solo is not None:
        percorso = valida_percorso(solo)
        return {percorso: await cliente.scarica(percorso, sha)}, sha, 0
    if not base:
        raise PatchRifiutata("Non so quale commit sta girando ora: allega i file, oppure indica un modulo.")
    cambiati = await cliente.file_cambiati(base, sha)
    ammessi, ignorati = [], 0
    for nome in cambiati:
        try:
            ammessi.append(valida_percorso(nome))
        except PatchRifiutata:
            ignorati += 1
    if len(ammessi) > MAX_FILE:
        raise PatchRifiutata(f"Troppi file cambiati ({len(ammessi)}): il massimo è {MAX_FILE}.")
    return {p: await cliente.scarica(p, sha) for p in ammessi}, sha, ignorati

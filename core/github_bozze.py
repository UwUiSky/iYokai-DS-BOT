"""
core/github_bozze.py
====================
Apre una pull request in bozza su GitHub con il file della bozza. Il token (`GITHUB_BOZZE_TOKEN`) deve valere solo
per quel repository (`GITHUB_BOZZE_REPO`, forma `utente/nome`). Spento se manca uno dei due. Non unisce mai.
Funzioni coperte: SPEC §25.100 (AI-R-107)
"""

from __future__ import annotations

import base64
import logging
import os
import re
from dataclasses import dataclass
from typing import Mapping

import aiohttp

logger = logging.getLogger("iyokai.github_bozze")
API = "https://api.github.com"
TIMEOUT_SECONDI = 20


@dataclass(frozen=True)
class ConfigGitHub:
    token: str
    repo: str
    base: str = "main"


def leggi_config(env: Mapping[str, str] | None = None) -> ConfigGitHub | None:
    env = os.environ if env is None else env
    token = (env.get("GITHUB_BOZZE_TOKEN") or "").strip()
    repo = (env.get("GITHUB_BOZZE_REPO") or "").strip()
    if not token or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return None
    return ConfigGitHub(token, repo, (env.get("GITHUB_BOZZE_BASE") or "main").strip())


class GitHubBozze:
    def __init__(self, config: ConfigGitHub | None, trasporto=None) -> None:
        self.config = config
        self._trasporto = trasporto or self._http

    @property
    def attivo(self) -> bool:
        return self.config is not None

    async def _http(self, metodo: str, percorso: str, corpo: dict | None) -> dict:
        intestazioni = {"Authorization": f"Bearer {self.config.token}", "Accept": "application/vnd.github+json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDI)) as s:
            async with s.request(metodo, f"{API}/repos/{self.config.repo}/{percorso}", json=corpo, headers=intestazioni) as r:
                if r.status >= 400:
                    raise RuntimeError(f"GitHub: stato {r.status}")
                return await r.json(content_type=None)

    async def apri_bozza(self, ramo: str, percorso_file: str, contenuto: str, titolo: str, corpo: str) -> str | None:
        """L'indirizzo della pull request in bozza, o None se spento o se qualcosa non va."""
        if self.config is None:
            return None
        try:
            base = await self._trasporto("GET", f"git/ref/heads/{self.config.base}", None)
            await self._trasporto("POST", "git/refs", {"ref": f"refs/heads/{ramo}", "sha": base["object"]["sha"]})
            await self._trasporto("PUT", f"contents/{percorso_file}", {
                "message": titolo, "branch": ramo, "content": base64.b64encode(contenuto.encode()).decode(),
            })
            pr = await self._trasporto("POST", "pulls", {"title": titolo, "head": ramo, "base": self.config.base, "body": corpo, "draft": True})
            url = pr.get("html_url")
            return url if isinstance(url, str) else None
        except Exception:  # noqa: BLE001
            logger.warning("Pull request in bozza non aperta.", exc_info=True)
            return None


_servizio: GitHubBozze | None = None


def github_bozze() -> GitHubBozze:
    global _servizio
    if _servizio is None:
        _servizio = GitHubBozze(leggi_config())
    return _servizio


def imposta_github_bozze(s: GitHubBozze | None) -> None:
    """Per i test."""
    global _servizio
    _servizio = s

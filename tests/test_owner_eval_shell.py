"""
tests/test_owner_eval_shell.py
==================================
SEC-13: comportamento REALE di /owner eval, /owner shell e
/owner cog-load. Copre sia D7 (ENABLE_EVAL spegne i tre comandi) sia
i bug minori di REVIEW.md §5 (log scritto prima dell'esecuzione,
defer prima di eseguire, il processo shell viene ucciso al timeout).
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from cogs.utility.owner_premium import (
    OwnerPremiumCog,
    _EvalConfirmView,
    _ShellConfirmView,
)
from core.config import config

_OWNER_ID = config.OWNER_ID


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.deferred = False

    async def send_message(
        self, content: str = None, embed=None, view=None, ephemeral: bool = False
    ) -> None:
        if content is not None:
            self.sent_messages.append(content)

    async def defer(self, *args, **kwargs) -> None:
        self.deferred = True


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeInteraction:
    def __init__(self, user_id: int) -> None:
        self.user = _FakeUser(user_id)
        self.response = _FakeResponse()
        self.edited: list[dict] = []

    async def edit_original_response(self, **kwargs) -> None:
        self.edited.append(kwargs)


class _FakeBot:
    async def load_extension(self, extension: str) -> None:
        raise AssertionError("non deve arrivare a caricare l'estensione")


class _ConfigFinto:
    """Config è un dataclass frozen (per design, vedi core/config.py):
    non è patchabile campo per campo. Stesso schema già usato da
    tests/test_premium_access.py — si sostituisce l'intero nome
    `config` importato nel modulo del cog con un oggetto finto."""

    def __init__(self, owner_id: int, enable_eval: bool) -> None:
        self.OWNER_ID = owner_id
        self.ENABLE_EVAL = enable_eval


def _imposta_enable_eval(monkeypatch, enabled: bool) -> None:
    import cogs.utility.owner_premium as owner_premium_module

    monkeypatch.setattr(
        owner_premium_module, "config", _ConfigFinto(_OWNER_ID, enabled)
    )


@pytest.fixture
def cog() -> OwnerPremiumCog:
    return OwnerPremiumCog(bot=_FakeBot())


class TestEnableEvalDisattivato:
    @pytest.mark.asyncio
    async def test_eval_risponde_disattivato(self, cog, monkeypatch):
        _imposta_enable_eval(monkeypatch, False)
        interaction = _FakeInteraction(_OWNER_ID)

        await cog.eval_code.callback(cog, interaction, "1 + 1")

        assert any("ENABLE_EVAL" in m for m in interaction.response.sent_messages)

    @pytest.mark.asyncio
    async def test_shell_risponde_disattivato(self, cog, monkeypatch):
        _imposta_enable_eval(monkeypatch, False)
        interaction = _FakeInteraction(_OWNER_ID)

        await cog.shell_command.callback(cog, interaction, "echo ciao")

        assert any("ENABLE_EVAL" in m for m in interaction.response.sent_messages)

    @pytest.mark.asyncio
    async def test_cog_load_risponde_disattivato_e_non_carica_nulla(self, cog, monkeypatch):
        _imposta_enable_eval(monkeypatch, False)
        interaction = _FakeInteraction(_OWNER_ID)

        # _FakeBot.load_extension solleva se chiamato: la sola
        # esecuzione senza eccezioni conferma che non è stato
        # raggiunto.
        await cog.owner_cog_load.callback(cog, interaction, "cogs.qualcosa")

        assert any("ENABLE_EVAL" in m for m in interaction.response.sent_messages)

    @pytest.mark.asyncio
    async def test_non_owner_vede_il_rifiuto_di_permesso_non_quello_di_eval(self, cog, monkeypatch):
        # Un non-owner non deve mai scoprire se ENABLE_EVAL è
        # acceso o spento.
        _imposta_enable_eval(monkeypatch, False)
        interaction = _FakeInteraction(_OWNER_ID + 1)

        await cog.eval_code.callback(cog, interaction, "1 + 1")

        assert interaction.response.sent_messages == ["Comando riservato al proprietario del bot."]


class TestEnableEvalAttivato:
    @pytest.mark.asyncio
    async def test_eval_manda_ancora_la_conferma(self, cog, monkeypatch):
        _imposta_enable_eval(monkeypatch, True)
        interaction = _FakeInteraction(_OWNER_ID)

        await cog.eval_code.callback(cog, interaction, "1 + 1")

        assert interaction.response.sent_messages == []  # niente testo semplice: è un embed+view


class TestDeferELogPrimaDiEseguire:
    @pytest.mark.asyncio
    async def test_eval_fa_defer_e_scrive_il_log_prima_di_eseguire(self, monkeypatch):
        import cogs.utility.owner_premium as owner_premium_module

        ordine: list[str] = []

        async def log_started_finto(executor_id, kind, code_or_command):
            ordine.append("log_started")
            return 42

        async def mark_result_finto(log_id, success):
            ordine.append(f"mark_result({log_id},{success})")

        monkeypatch.setattr(
            owner_premium_module.eval_shell_log_repo, "log_started", log_started_finto
        )
        monkeypatch.setattr(
            owner_premium_module.eval_shell_log_repo, "mark_result", mark_result_finto
        )

        cog = OwnerPremiumCog(bot=None)

        async def _run_eval_finto(code, interaction):
            ordine.append("esecuzione")
            return "ok", True

        cog._run_eval = _run_eval_finto

        view = _EvalConfirmView(cog, "1 + 1")
        interaction = _FakeInteraction(_OWNER_ID)

        await view.children[0].callback(interaction)

        assert interaction.response.deferred is True
        assert ordine == ["log_started", "esecuzione", "mark_result(42,True)"]
        assert len(interaction.edited) == 1  # edit_original_response, non response.edit_message


class TestShellUccideIlProcessoAlTimeout:
    @pytest.mark.asyncio
    async def test_processo_appeso_viene_ucciso_al_timeout(self, monkeypatch):
        import cogs.utility.owner_premium as owner_premium_module

        class _ProcessoFinto:
            def __init__(self) -> None:
                self.killed = False
                self.waited = False
                self.returncode = None

            async def communicate(self):
                await asyncio.sleep(9999)  # non completa mai entro il timeout

            def kill(self) -> None:
                self.killed = True

            async def wait(self) -> None:
                self.waited = True

        processo_finto = _ProcessoFinto()

        async def create_subprocess_shell_finto(*args, **kwargs):
            return processo_finto

        monkeypatch.setattr(
            owner_premium_module.asyncio,
            "create_subprocess_shell",
            create_subprocess_shell_finto,
        )
        monkeypatch.setattr(owner_premium_module, "SHELL_TIMEOUT_SECONDS", 0.05)

        cog = OwnerPremiumCog(bot=None)
        output, success = await cog._run_shell("sleep 999999")

        assert success is False
        assert "Timeout" in output
        assert processo_finto.killed is True
        assert processo_finto.waited is True

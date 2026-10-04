"""
tests/test_owner_eval_shell.py
==================================
SEC-13: comportamento REALE di /owner eval, /owner shell e
/owner cog-load. Copre sia D7 (ENABLE_EVAL spegne i tre comandi) sia
i bug minori di REVIEW.md §5 (log scritto prima dell'esecuzione,
defer prima di eseguire, il processo shell viene ucciso al timeout).

BUG-23: il timeout di /owner shell si prova con processi veri — deve
morire tutto l'albero del comando (non solo la shell) e la risposta
deve arrivare subito.
"""

import asyncio
import os
import subprocess
import time
from unittest.mock import AsyncMock, create_autospec

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


def _processi_con(marcatore: str) -> list[str]:
    """Le righe di `ps` dei processi vivi il cui comando contiene il marcatore."""
    righe = subprocess.run(
        ["ps", "-eo", "pid,args"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [riga for riga in righe if marcatore in riga]


async def _aspetta_che_spariscano(marcatore: str, secondi: float = 3.0) -> list[str]:
    scadenza = time.monotonic() + secondi
    while _processi_con(marcatore) and time.monotonic() < scadenza:
        await asyncio.sleep(0.05)
    return _processi_con(marcatore)


@pytest.mark.skipif(os.name != "posix", reason="usa sh, sleep e ps")
class TestShellConProcessiVeri:
    """
    BUG-23: comandi veri, non un processo finto. Ogni test usa una
    durata di `sleep` unica, così `ps` riconosce il SUO processo.
    """

    @pytest.fixture(autouse=True)
    def _timeout_corto(self, monkeypatch):
        import cogs.utility.owner_premium as owner_premium_module

        monkeypatch.setattr(owner_premium_module, "SHELL_TIMEOUT_SECONDS", 0.5)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "comando,marcatore",
        [
            ("sleep 60.0231", "sleep 60.0231"),
            # Il comando vero è figlio della shell e tiene aperta la pipe.
            ("sleep 60.0232 | cat", "sleep 60.0232"),
            ("echo x; sleep 60.0233", "sleep 60.0233"),
            # Un nipote lanciato in background, che sopravvive alla shell.
            ("(sleep 60.0234 &) ; sleep 60.0234", "sleep 60.0234"),
        ],
        ids=["sleep", "pipe", "echo-poi-sleep", "nipote-in-background"],
    )
    async def test_al_timeout_risponde_subito_e_non_lascia_processi(self, comando, marcatore):
        cog = OwnerPremiumCog(bot=None)
        inizio = time.monotonic()

        # Se _run_shell restasse bloccato, wait_for fa fallire il test
        # invece di lasciarlo appeso per 60 secondi.
        output, successo = await asyncio.wait_for(cog._run_shell(comando), timeout=10)

        assert time.monotonic() - inizio < 5
        assert successo is False
        assert "Timeout" in output
        assert await _aspetta_che_spariscano(marcatore) == []

    @pytest.mark.asyncio
    async def test_comando_normale_restituisce_output_ed_esito(self):
        cog = OwnerPremiumCog(bot=None)

        assert await cog._run_shell("echo ciao") == ("ciao\n", True)
        assert await cog._run_shell("echo errore >&2; exit 3") == ("errore\n", False)
        assert await cog._run_shell("true") == ("(nessun output)", True)

    @pytest.mark.asyncio
    async def test_errore_di_avvio_torna_come_output_del_comando(self):
        # Un byte NUL nel comando fa fallire davvero l'avvio del processo.
        cog = OwnerPremiumCog(bot=None)

        output, successo = await cog._run_shell("echo \x00")

        assert successo is False
        assert "ValueError" in output


class TestShellRamoWindows:
    """
    Il ramo Windows non si può eseguire su Linux: qui si controlla che
    vengano scelti i parametri giusti (nuovo gruppo di processi alla
    creazione, `taskkill /T /F` al timeout).
    """

    @pytest.fixture
    def su_windows(self, monkeypatch):
        import cogs.utility.owner_premium as owner_premium_module

        monkeypatch.setattr(owner_premium_module, "SU_WINDOWS", True)
        # La costante esiste solo nel modulo subprocess di Windows.
        monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
        return owner_premium_module

    def test_il_comando_parte_in_un_nuovo_gruppo_di_processi(self, su_windows):
        assert su_windows._opzioni_nuovo_gruppo() == {"creationflags": 0x200}

    def test_su_posix_il_comando_parte_in_una_nuova_sessione(self, monkeypatch):
        import cogs.utility.owner_premium as owner_premium_module

        monkeypatch.setattr(owner_premium_module, "SU_WINDOWS", False)

        assert owner_premium_module._opzioni_nuovo_gruppo() == {"start_new_session": True}

    @pytest.mark.asyncio
    async def test_al_timeout_usa_taskkill_su_tutto_l_albero(self, su_windows, monkeypatch):
        taskkill = create_autospec(asyncio.subprocess.Process, instance=True)
        avvia = AsyncMock(return_value=taskkill)
        monkeypatch.setattr(su_windows.asyncio, "create_subprocess_exec", avvia)

        await su_windows._uccidi_albero(4321)

        assert avvia.await_args.args == ("taskkill", "/T", "/F", "/PID", "4321")
        taskkill.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_se_il_processo_non_muore_la_risposta_arriva_lo_stesso(self, monkeypatch):
        # taskkill (o killpg) può fallire: l'attesa finale ha un suo
        # timeout, quindi il comando risponde comunque.
        import cogs.utility.owner_premium as owner_premium_module

        async def _non_uccide(pid: int) -> None:
            return None

        monkeypatch.setattr(owner_premium_module, "_uccidi_albero", _non_uccide)
        monkeypatch.setattr(owner_premium_module, "SHELL_TIMEOUT_SECONDS", 0.2)
        monkeypatch.setattr(owner_premium_module, "SHELL_KILL_WAIT_SECONDS", 0.2)
        cog = OwnerPremiumCog(bot=None)

        try:
            output, successo = await asyncio.wait_for(
                cog._run_shell("sleep 3.0235"), timeout=2.5
            )
        finally:
            await _aspetta_che_spariscano("sleep 3.0235", secondi=5)

        assert successo is False
        assert "Timeout" in output
        assert "ancora in esecuzione" in output

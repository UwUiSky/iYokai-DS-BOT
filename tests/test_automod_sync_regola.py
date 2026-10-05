"""
tests/test_automod_sync_regola.py
=================================
Sincronizzazione delle regole AutoMod su Discord (LIM-29): la modifica
di una regola non deve cancellare ciò che l'admin ha messo a mano
(espressioni regolari, lista delle eccezioni, parole), e i tetti di
Discord (6 regole a parole chiave, 60 caratteri per parola) danno un
messaggio chiaro invece di un errore.

Il server è finto ma "ricorda": una regola modificata con edit() viene
riletta com'è al giro dopo, come su Discord. Il database è vero.
"""

from unittest.mock import MagicMock, create_autospec

import discord
import pytest

import cogs.automod.automod as modulo_automod
from core.repositories.automod_repo import AutomodRepository
from tests.support.discord_fakes import fake_guild

GUILD_ID = 666


def _regola_finta(nome: str, **campi_trigger) -> MagicMock:
    """Regola AutoMod finta con un trigger vero; edit() la aggiorna."""
    regola = create_autospec(discord.AutoModRule, instance=True)
    regola.name = nome
    regola.trigger = discord.AutoModTrigger(
        type=discord.AutoModRuleTriggerType.keyword, **campi_trigger
    )

    async def _edit(**kwargs):
        if "trigger" in kwargs:
            regola.trigger = kwargs["trigger"]
        return regola

    regola.edit.side_effect = _edit
    return regola


def _server_con(regole: list) -> MagicMock:
    server = fake_guild(guild_id=GUILD_ID)
    server.fetch_automod_rules.return_value = regole
    return server


def _errore_http(status: int = 400) -> discord.HTTPException:
    risposta = MagicMock()
    risposta.status = status
    risposta.reason = "Bad Request"
    return discord.HTTPException(risposta, "errore finto di Discord")


@pytest.fixture
def repo(clean_db, monkeypatch) -> AutomodRepository:
    vero = AutomodRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo_automod, "automod_repo", vero)
    return vero


async def test_modifica_conserva_eccezioni_e_regex_messe_a_mano(repo):
    regola = _regola_finta(
        modulo_automod.RULE_NAME_BADWORDS,
        keyword_filter=["vecchia"],
        regex_patterns=[r"sp+am"],
        allow_list=["spamalot"],
    )
    server = _server_con([regola])
    await repo.add_badword(GUILD_ID, "nuova")

    avviso = await modulo_automod._sync_guild(server)

    assert avviso is None
    regola.edit.assert_awaited_once()
    trigger = regola.edit.call_args.kwargs["trigger"]
    assert trigger.keyword_filter == ["vecchia", "nuova"]
    assert trigger.regex_patterns == [r"sp+am"]
    assert trigger.allow_list == ["spamalot"]


async def test_regola_inviti_conserva_parole_ed_eccezioni_messe_a_mano(repo):
    regola = _regola_finta(
        modulo_automod.RULE_NAME_INVITES,
        keyword_filter=["invito privato"],
        regex_patterns=[r"altro\.sito/\S+"],
        allow_list=["discord.gg/ufficiale"],
    )
    server = _server_con([regola])
    await repo.set_block_invites(GUILD_ID, True)

    await modulo_automod._sync_guild(server)

    trigger = regola.edit.call_args.kwargs["trigger"]
    assert trigger.keyword_filter == ["invito privato"]
    assert trigger.allow_list == ["discord.gg/ufficiale"]
    assert trigger.regex_patterns[0] == r"altro\.sito/\S+"
    assert set(modulo_automod.INVITE_REGEX_PATTERNS) <= set(trigger.regex_patterns)


async def test_parola_messa_a_mano_resta_anche_dopo_piu_sincronizzazioni(repo):
    regola = _regola_finta(modulo_automod.RULE_NAME_BADWORDS, keyword_filter=["a mano"])
    server = _server_con([regola])

    await repo.add_badword(GUILD_ID, "prima")
    await modulo_automod._sync_guild(server)
    await repo.add_badword(GUILD_ID, "seconda")
    await modulo_automod._sync_guild(server)
    await repo.remove_badword(GUILD_ID, "prima")
    await modulo_automod._sync_guild(server)

    assert regola.trigger.keyword_filter == ["a mano", "seconda"]


async def test_sesta_regola_gia_presente_messaggio_chiaro(repo):
    regole = [_regola_finta(f"Regola dell'admin {n}", keyword_filter=["x"]) for n in range(6)]
    server = _server_con(regole)
    await repo.add_badword(GUILD_ID, "spam")

    avviso = await modulo_automod._sync_guild(server)

    server.create_automod_rule.assert_not_awaited()
    assert "6" in avviso
    assert "regole" in avviso.lower()
    # Niente è stato scritto su Discord: al prossimo giro si riprova.
    assert await repo.get_last_synced(GUILD_ID, modulo_automod.RULE_NAME_BADWORDS) == ((), ())


async def test_parola_troppo_lunga_gia_salvata_viene_saltata(repo):
    lunga = "x" * 61
    await repo.add_badword(GUILD_ID, lunga)
    await repo.add_badword(GUILD_ID, "spam")
    server = _server_con([])

    avviso = await modulo_automod._sync_guild(server)

    trigger = server.create_automod_rule.call_args.kwargs["trigger"]
    assert trigger.keyword_filter == ["spam"]
    assert "60" in avviso


async def test_errore_di_discord_diventa_un_messaggio(repo):
    regola = _regola_finta(modulo_automod.RULE_NAME_BADWORDS, keyword_filter=["vecchia"])
    regola.edit.side_effect = _errore_http()
    server = _server_con([regola])
    await repo.add_badword(GUILD_ID, "nuova")

    avviso = await modulo_automod._sync_guild(server)

    assert "Discord" in avviso
    assert await repo.get_last_synced(GUILD_ID, modulo_automod.RULE_NAME_BADWORDS) == ((), ())

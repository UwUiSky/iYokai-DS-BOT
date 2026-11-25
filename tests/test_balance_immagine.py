"""
tests/test_balance_immagine.py
==============================
`/monete balance` con l'opzione `immagine` (D137): sì = la vecchia immagine del portafoglio (era `/monete conto portafoglio`).
Senza l'opzione il saldo resta il messaggio di testo. Il comando `conto portafoglio` non esiste più.
Funzioni coperte: D137, ECO-017
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from cogs.leveling import leveling as modulo
from cogs.leveling.leveling import LevelingCog


async def test_con_immagine_si_disegna_il_portafoglio_del_membro(monkeypatch):
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))
    invia = AsyncMock()
    monkeypatch.setattr("cogs.leveling._portafoglio.invia_portafoglio", invia)
    cog = LevelingCog(bot=None)
    interaction, membro = MagicMock(), MagicMock()
    await LevelingCog.balance.callback(cog, interaction, membro, True)
    invia.assert_awaited_once_with(interaction, membro)


async def test_senza_immagine_resta_il_testo(monkeypatch):
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))
    invia = AsyncMock()
    monkeypatch.setattr("cogs.leveling._portafoglio.invia_portafoglio", invia)
    monkeypatch.setattr(modulo.leveling_repo, "get_totals", AsyncMock(return_value=MagicMock(coins_total=7)))
    monkeypatch.setattr(modulo.leveling_repo, "get_coins_position", AsyncMock(return_value=2))
    cog = LevelingCog(bot=None)
    monkeypatch.setattr(cog, "_moneta", AsyncMock(return_value="monete"))
    monkeypatch.setattr(cog, "_con_moneta", AsyncMock(return_value=None))
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.user.mention = "@io"
    await LevelingCog.balance.callback(cog, interaction, None, False)
    invia.assert_not_awaited()
    assert "**7** monete" in interaction.response.send_message.await_args.kwargs["embed"].description


async def test_conto_portafoglio_non_esiste_piu():
    from core.command_groups import GRUPPI
    from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, falliti
        conto = GRUPPI["monete"].get_command("conto")
        assert conto.get_command("portafoglio") is None
        balance = GRUPPI["monete"].get_command("balance")
        assert "immagine" in {p.name for p in balance.parameters}
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()

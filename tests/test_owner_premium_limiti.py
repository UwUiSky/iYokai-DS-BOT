"""
tests/test_owner_premium_limiti.py
=====================================
M 10.12 (LIM-22): liste e pannello dell'owner entro i limiti di Discord:
risposte a pagine, pannello premium con al massimo 25 voci per tendina,
Range su codice di eval, comando shell e annuncio.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.owner_premium as op
from cogs.utility.owner_premium import OwnerPremiumCog, _PremiumPanelView, _build_premium_panel_embed
from core.config import config
from core.premium import PremiumModule, PremiumRegistry
from tests.support.discord_fakes import fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo


def _moduli(n, premium_capable=True):
    return [
        PremiumModule(
            name=f"modulo_{i:02d}", display_name=f"Modulo numero {i:02d}",
            description="d", premium_capable=premium_capable, category="utility",
        )
        for i in range(n)
    ]


def _owner_interaction():
    return fake_interaction(user=fake_member(user_id=config.OWNER_ID))


def _testo_pagine(vista) -> str:
    """Tutto il testo di tutte le pagine di una lista dell'owner."""
    return "\n".join(vista.pagine)


def _invio(interazione, dopo_defer=False):
    mock = interazione.followup.send if dopo_defer else interazione.response.send_message
    return mock.await_args.kwargs


@pytest.mark.asyncio
async def test_premium_list_con_40_moduli_risposta_valida(monkeypatch):
    reg = PremiumRegistry()
    for m in _moduli(40, premium_capable=False):
        reg.register(m)
    monkeypatch.setattr(op, "registry", reg)
    interazione = _owner_interaction()
    cog = OwnerPremiumCog(MagicMock())

    await cog.premium_list.callback(cog, interazione)

    kwargs = _invio(interazione)
    assert len(kwargs["embed"].description) <= 4096
    vista = kwargs.get("view")
    tutto = _testo_pagine(vista) if vista else kwargs["embed"].description
    assert all(f"modulo_{i:02d}" in tutto for i in range(40))


@pytest.mark.asyncio
async def test_premium_list_a_pagine_non_perde_nessun_modulo(monkeypatch):
    reg = PremiumRegistry()
    for m in _moduli(60, premium_capable=False):
        reg.register(m)
    monkeypatch.setattr(op, "registry", reg)
    interazione = _owner_interaction()
    cog = OwnerPremiumCog(MagicMock())

    await cog.premium_list.callback(cog, interazione)

    vista = _invio(interazione)["view"]
    assert all(len(p) <= 4000 for p in vista.pagine)
    assert all(f"modulo_{i:02d}" in _testo_pagine(vista) for i in range(60))


@pytest.mark.asyncio
async def test_whitelist_list_non_taglia_ma_pagina(monkeypatch):
    voci = [
        {"guild_id": 1000 + i, "added_by": 1, "reason": "r" * 100, "added_at": datetime(2026, 1, 1)}
        for i in range(80)
    ]
    monkeypatch.setattr(op.db, "list_premium_whitelist", AsyncMock(return_value=voci))
    interazione = _owner_interaction()
    cog = OwnerPremiumCog(MagicMock())

    await cog.whitelist_list.callback(cog, interazione)

    vista = _invio(interazione)["view"]
    assert all(str(1000 + i) in _testo_pagine(vista) for i in range(80))
    assert all(len(p) <= 4000 for p in vista.pagine)


@pytest.mark.asyncio
async def test_abbonamenti_a_pagine(monkeypatch):
    from core.repositories.module_subscription_repo import module_subscription_repo

    abbonamenti = [
        SimpleNamespace(module_name=f"modulo_{i:03d}", expires_at=datetime(2027, 1, 1)) for i in range(300)
    ]
    monkeypatch.setattr(module_subscription_repo, "list_for_guild", AsyncMock(return_value=abbonamenti))
    interazione = _owner_interaction()
    cog = OwnerPremiumCog(MagicMock())

    await cog.premium_subscriptions.callback(cog, interazione, "123")

    vista = _invio(interazione)["view"]
    assert len(vista.pagine) > 1
    assert all(f"modulo_{i:03d}" in _testo_pagine(vista) for i in range(300))


@pytest.mark.asyncio
async def test_status_all_a_pagine_dopo_il_defer(monkeypatch):
    guilds = [SimpleNamespace(id=9000 + i, name=f"Server numero {i}") for i in range(150)]
    bot = SimpleNamespace(guilds=guilds)
    monkeypatch.setattr(
        op, "get_guild_premium_breakdown",
        AsyncMock(return_value={"whitelisted": True, "boosts_main_guild": False,
                                "cassa_active": False, "subscription_count": 0}),
    )
    interazione = _owner_interaction()
    interazione.client = bot
    cog = OwnerPremiumCog(MagicMock())

    await cog.premium_status_all.callback(cog, interazione)

    interazione.response.defer.assert_awaited_once()
    vista = _invio(interazione, dopo_defer=True)["view"]
    assert "150 server totali" in vista.pagine[0]
    assert all(str(9000 + i) in _testo_pagine(vista) for i in range(150))


@pytest.mark.asyncio
async def test_liste_blacklist_a_pagine(monkeypatch):
    import core.repositories.blacklist_repo as br

    utenti = [{"user_id": 10_000 + i, "reason": "x" * 60} for i in range(120)]
    server = [{"guild_id": 20_000 + i, "reason": "x" * 60} for i in range(120)]
    monkeypatch.setattr(br.blacklist_repo, "list_users", AsyncMock(return_value=utenti))
    monkeypatch.setattr(br.blacklist_repo, "list_guilds", AsyncMock(return_value=server))
    cog = OwnerPremiumCog(MagicMock())

    for metodo, primo in (("blacklist_user_list", "10000"), ("blacklist_guild_list", "20000")):
        interazione = _owner_interaction()
        await getattr(cog, metodo).callback(cog, interazione)
        vista = _invio(interazione)["view"]
        assert all(len(p) <= 4000 for p in vista.pagine)
        assert primo in vista.pagine[0]
        assert len(vista.pagine) > 1


@pytest.mark.asyncio
async def test_i_bottoni_delle_pagine_li_usa_solo_l_owner(monkeypatch):
    monkeypatch.setattr(op.db, "list_premium_whitelist", AsyncMock(return_value=[
        {"guild_id": 1000 + i, "added_by": 1, "reason": "r" * 100, "added_at": datetime(2026, 1, 1)}
        for i in range(80)
    ]))
    owner = _owner_interaction()
    cog = OwnerPremiumCog(MagicMock())
    await cog.whitelist_list.callback(cog, owner)
    vista = _invio(owner)["view"]

    import core.ui_base as ui_base

    monkeypatch.setattr(ui_base, "_utente_o_server_in_blacklist", AsyncMock(return_value=False))
    estraneo = fake_interaction(user=fake_member(user_id=config.OWNER_ID + 1))
    assert await vista.interaction_check(estraneo) is False
    estraneo.response.send_message.assert_awaited_once()
    assert await vista.interaction_check(owner) is True


@pytest.mark.asyncio
async def test_pannello_premium_con_40_moduli_tendina_da_25_al_massimo():
    moduli = _moduli(40)
    vista = _PremiumPanelView(MagicMock(), moduli)

    select = next(c for c in vista.children if isinstance(c, discord.ui.Select))
    assert isinstance(select, discord.ui.Select)
    assert len(select.options) <= 25
    assert len(_build_premium_panel_embed(moduli[:25]).fields) <= 25

    # La pagina dopo mostra gli altri; nessun modulo resta fuori.
    visti = {o.value for o in select.options}
    vista2 = _PremiumPanelView(MagicMock(), moduli, pagina=1)
    visti |= {o.value for c in vista2.children if isinstance(c, discord.ui.Select) for o in c.options}
    assert visti == {m.name for m in moduli}


def test_embed_del_pannello_non_supera_i_limiti_con_nomi_lunghi():
    moduli = [
        PremiumModule(name="n" * 60, display_name="D" * 400, description="d", category="utility")
        for _ in range(25)
    ]
    embed = _build_premium_panel_embed(moduli)
    opzioni = _PremiumPanelView(MagicMock(), moduli).children[-1].options
    assert all(len(o.label) <= 100 for o in opzioni)
    assert len(embed) <= 6000
    assert all(len(f.name) <= 256 and len(f.value) <= 1024 for f in embed.fields)


@pytest.mark.asyncio
async def test_limiti_di_eval_shell_e_annuncio():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await op.setup(bot)
    try:
        for percorso, nome in (("system eval", "code"), ("system shell", "command"), ("system announce", "message")):
            opzioni = {o["name"]: o for o in comando_nel_gruppo("owner", percorso).to_dict(bot.tree)["options"]}
            assert opzioni[nome]["max_length"] == 4000, percorso
    finally:
        await bot.remove_cog("OwnerPremiumCog")

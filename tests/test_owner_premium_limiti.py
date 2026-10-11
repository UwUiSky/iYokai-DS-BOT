"""
tests/test_owner_premium_limiti.py
=====================================
M 10.12 (LIM-22): liste e pannello dell'owner entro i limiti di Discord:
risposte a pagine, pannello premium con al massimo 25 voci per tendina,
Range su codice di eval, comando shell e annuncio.
"""

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


def _tutte_le_risposte(interazione):
    invii = [c for c in interazione.response.send_message.await_args_list]
    invii += [c for c in interazione.followup.send.await_args_list]
    return invii


@pytest.mark.asyncio
async def test_premium_list_con_40_moduli_risposta_valida(monkeypatch):
    reg = PremiumRegistry()
    for m in _moduli(40, premium_capable=False):
        reg.register(m)
    monkeypatch.setattr(op, "registry", reg)
    interazione = _owner_interaction()
    cog = OwnerPremiumCog(MagicMock())

    await cog.premium_list.callback(cog, interazione)

    interazione.response.send_message.assert_awaited_once()
    contenuto = interazione.response.send_message.await_args.args[0]
    assert len(contenuto) <= 2000
    assert "modulo_39" in contenuto or "view" in interazione.response.send_message.await_args.kwargs


@pytest.mark.asyncio
async def test_premium_list_a_pagine_non_perde_nessun_modulo(monkeypatch):
    reg = PremiumRegistry()
    for m in _moduli(60, premium_capable=False):
        reg.register(m)
    monkeypatch.setattr(op, "registry", reg)
    interazione = _owner_interaction()
    cog = OwnerPremiumCog(MagicMock())

    await cog.premium_list.callback(cog, interazione)

    kwargs = interazione.response.send_message.await_args.kwargs
    vista = kwargs["view"]
    visti = set()
    for _ in range(len(vista.pagine)):
        testo = vista.testo_pagina()
        assert len(testo) <= 2000
        visti |= {f"modulo_{i:02d}" for i in range(60) if f"modulo_{i:02d}" in testo}
        vista.indice = min(vista.indice + 1, len(vista.pagine) - 1)
    assert len(visti) == 60


@pytest.mark.asyncio
async def test_whitelist_list_non_taglia_ma_pagina(monkeypatch):
    voci = [
        {"guild_id": 1000 + i, "added_by": 1, "reason": "r" * 100, "added_at": __import__("datetime").datetime(2026, 1, 1)}
        for i in range(80)
    ]
    monkeypatch.setattr(op.db, "list_premium_whitelist", AsyncMock(return_value=voci))
    interazione = _owner_interaction()
    cog = OwnerPremiumCog(MagicMock())

    await cog.whitelist_list.callback(cog, interazione)

    vista = interazione.response.send_message.await_args.kwargs["view"]
    tutto = "\n".join(vista.pagine)
    assert all(str(1000 + i) in tutto for i in range(80))
    assert all(len(p) <= 1900 for p in vista.pagine)


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
        vista = interazione.response.send_message.await_args.kwargs["view"]
        assert all(len(p) <= 1900 for p in vista.pagine)
        assert primo in vista.pagine[0]
        assert len(vista.pagine) > 1


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
        PremiumModule(name="n" * 60, display_name="D" * 100, description="d", category="utility")
        for _ in range(25)
    ]
    embed = _build_premium_panel_embed(moduli)
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

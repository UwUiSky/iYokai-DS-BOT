"""
tests/test_command_groups_cog.py
================================
Il modo unico per mettere il comando di un cog in un gruppo condiviso:
`@comando_di_gruppo`, `CogConGruppi`, `registra_comandi_del_cog`.
Albero vero (`commands.Bot` non collegato) e il cog vero BasicLogsCog.
Funzioni coperte: NF-05 (issue #76)
"""

from __future__ import annotations

import types

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from cogs.logging import basic_logs
from core import command_access as ca
from core import command_groups as cg
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import (
    CogConGruppi,
    comando_di_gruppo,
    registra_comandi_del_cog,
    togli_comandi_del_cog,
)
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel
from tests.test_command_tree_invariants import conta_caratteri


class _FakeDb:
    def __init__(self):
        self.scritti = {}

    async def get_guild_setting(self, guild_id, key, default=None):
        return self.scritti.get((guild_id, key), default)

    async def set_guild_setting(self, guild_id, key, value, changed_by=None):
        self.scritti[(guild_id, key)] = value


@pytest.fixture(autouse=True)
def _finti(monkeypatch):
    monkeypatch.setattr(ca, "db", _FakeDb())
    monkeypatch.setattr(ca, "config", types.SimpleNamespace(OWNER_ID=1))


def _ix(perm=None, **kw):
    membro = fake_member(
        user_id=3,
        guild_permissions=discord.Permissions(**{perm: True}) if perm else discord.Permissions.none(),
    )
    return fake_interaction(guild=fake_guild(guild_id=77, owner_id=2), user=membro, **kw)


def _bot():
    return commands.Bot(command_prefix="!", intents=discord.Intents.default())


class CogProva(CogConGruppi, commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.gruppi_yokai = cg.costruisci_gruppi()
        self.chiamate = []

    @autocomplete_protetto(Livello.ADMIN)
    async def _autocompleta(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name="a", value="a")]

    @comando_di_gruppo("admin", nome="prova", descrizione="Comando di prova", sottogruppo=("config", "Impostazioni"))
    @app_commands.describe(valore="Un numero", scelta="Una scelta", testo="Un testo")
    @app_commands.choices(scelta=[app_commands.Choice(name="Uno", value="1")])
    @app_commands.rename(valore="numero")
    @app_commands.autocomplete(testo=_autocompleta)
    @app_commands.checks.cooldown(1, 60)
    async def prova(
        self,
        interaction: discord.Interaction,
        valore: app_commands.Range[int, 1, 9],
        scelta: str,
        testo: str,
    ) -> None:
        self.chiamate.append((valore, scelta, testo))

    @comando_di_gruppo("ticket", nome="aperto", descrizione="Gruppo aperto")
    async def aperto(self, interaction: discord.Interaction) -> None:
        self.chiamate.append("aperto")


def _trova(cog, gruppo="admin", sotto="config", nome="prova"):
    nodo = cog.gruppi_yokai[gruppo]
    if sotto:
        nodo = nodo.get_command(sotto)
    return nodo.get_command(nome)


# ----------------------------------------------------------------------
# Il decoratore e il binding
# ----------------------------------------------------------------------
async def test_il_decoratore_lascia_il_callback_chiamabile_come_prima():
    cog = CogProva(_bot())
    ix = _ix()
    await CogProva.prova.callback(cog, ix, 3, "1", "x")
    await cog.prova.callback(cog, ix, 4, "1", "y")
    assert cog.chiamate == [(3, "1", "x"), (4, "1", "y")]


async def test_il_comando_registrato_ha_il_callback_legato_al_cog():
    bot = _bot()
    cog = CogProva(bot)
    await bot.add_cog(cog)
    cmd = _trova(cog)
    assert cmd.binding is cog
    await cmd._do_call(_ix(), {"valore": 5, "scelta": "1", "testo": "t"})
    assert cog.chiamate == [(5, "1", "t")]


async def test_describe_choices_rename_autocomplete_range_e_cooldown_restano():
    bot = _bot()
    cog = CogProva(bot)
    await bot.add_cog(cog)
    cmd = _trova(cog)
    par = {p.name: p for p in cmd.parameters}
    assert set(par) == {"valore", "scelta", "testo"}
    assert par["valore"].display_name == "numero"
    assert par["valore"].description == "Un numero"
    assert (par["valore"].min_value, par["valore"].max_value) == (1, 9)
    assert [c.value for c in par["scelta"].choices] == ["1"]
    assert par["testo"].autocomplete is True
    assert len(cmd.checks) == 1  # il cooldown


async def test_autocomplete_protetto_dentro_il_gruppo_blocca_chi_non_puo():
    cog = CogProva(_bot())
    assert await cog._autocompleta(_ix(), "") == []
    assert len(await cog._autocompleta(_ix("manage_guild"), "")) == 1


# ----------------------------------------------------------------------
# Posto nell'albero
# ----------------------------------------------------------------------
async def test_il_comando_sta_nel_gruppo_e_non_al_primo_livello():
    bot = _bot()
    cog = CogProva(bot)
    await bot.add_cog(cog)
    radici = {c.name for c in bot.tree.get_commands()}
    assert radici == {"admin", "ticket"}
    assert "prova" not in radici and "aperto" not in radici
    assert _trova(cog) is not None
    assert _trova(cog, "ticket", None, "aperto") is not None
    sotto = cog.gruppi_yokai["admin"].get_command("config")
    assert isinstance(sotto, ca.GruppoYokai)


async def test_check_can_run_blocca_chi_non_ha_il_livello():
    bot = _bot()
    cog = CogProva(bot)
    await bot.add_cog(cog)
    cmd = _trova(cog)
    with pytest.raises(ca.AccessoNegato):
        await cmd._check_can_run(_ix())
    ok = _ix("manage_guild")
    ok.created_at = discord.utils.utcnow()  # serve al cooldown del comando
    assert await cmd._check_can_run(ok) is True
    # il gruppo aperto non chiede niente
    assert await _trova(cog, "ticket", None, "aperto")._check_can_run(_ix()) is True


# ----------------------------------------------------------------------
# Ricaricamento e scaricamento
# ----------------------------------------------------------------------
async def test_il_ricaricamento_non_duplica():
    bot = _bot()
    cog = CogProva(bot)
    await bot.add_cog(cog)
    await bot.remove_cog("CogProva")
    nuovo = CogProva(bot)
    nuovo.gruppi_yokai = cog.gruppi_yokai
    await bot.add_cog(nuovo)
    sotto = cog.gruppi_yokai["admin"].get_command("config")
    assert [c.name for c in sotto.commands] == ["prova"]
    assert sotto.get_command("prova").binding is nuovo
    assert [c.name for c in bot.tree.get_commands()].count("admin") == 1


async def test_registrare_due_volte_lo_stesso_cog_non_duplica():
    bot = _bot()
    cog = CogProva(bot)
    registra_comandi_del_cog(cog, gruppi=cog.gruppi_yokai, tree=bot.tree)
    registra_comandi_del_cog(cog, gruppi=cog.gruppi_yokai, tree=bot.tree)
    assert len(cog.gruppi_yokai["admin"].get_command("config").commands) == 1
    togli_comandi_del_cog(cog)
    assert bot.tree.get_commands() == []


async def test_lo_scaricamento_toglie_comando_sottogruppo_e_gruppo_vuoto():
    bot = _bot()
    cog = CogProva(bot)
    await bot.add_cog(cog)
    await bot.remove_cog("CogProva")
    assert cog.gruppi_yokai["admin"].commands == []
    assert cog.gruppi_yokai["ticket"].commands == []
    assert bot.tree.get_commands() == []


async def test_lo_scaricamento_lascia_i_comandi_degli_altri_cog():
    bot = _bot()
    cog = CogProva(bot)
    await bot.add_cog(cog)

    class Altro(CogConGruppi, commands.Cog):
        gruppi_yokai = cog.gruppi_yokai

        def __init__(self, bot):
            self.bot = bot

        @comando_di_gruppo("ticket", nome="altro", descrizione="Di un altro cog")
        async def altro(self, interaction: discord.Interaction) -> None: ...

    await bot.add_cog(Altro(bot))
    await bot.remove_cog("CogProva")
    assert [c.name for c in cog.gruppi_yokai["ticket"].commands] == ["altro"]
    assert [c.name for c in bot.tree.get_commands()] == ["ticket"]


# ----------------------------------------------------------------------
# Conflitti
# ----------------------------------------------------------------------
async def test_un_group_del_cog_con_lo_stesso_nome_del_gruppo_condiviso_da_errore():
    bot = _bot()
    bot.tree.add_command(app_commands.Group(name="ticket", description="Vecchio gruppo del cog"))
    cog = CogProva(bot)
    with pytest.raises(ValueError, match="ticket"):
        await bot.add_cog(cog)


async def test_un_altro_cog_non_ruba_il_nome_di_un_comando():
    bot = _bot()
    cog = CogProva(bot)
    await bot.add_cog(cog)

    class Ladro(CogConGruppi, commands.Cog):
        gruppi_yokai = cog.gruppi_yokai

        def __init__(self, bot):
            self.bot = bot

        @comando_di_gruppo("ticket", nome="aperto", descrizione="Stesso nome")
        async def ladro(self, interaction: discord.Interaction) -> None: ...

    with pytest.raises(ValueError, match="aperto"):
        await bot.add_cog(Ladro(bot))
    assert _trova(cog, "ticket", None, "aperto").binding is cog


def test_un_group_semplice_sotto_un_gruppo_protetto_resta_vietato():
    gruppi = cg.costruisci_gruppi()
    with pytest.raises(TypeError):
        gruppi["admin"].add_command(app_commands.Group(name="x", description="y"))


def test_gruppo_sconosciuto_da_errore_chiaro():
    with pytest.raises(KeyError):

        class _Cattivo(CogConGruppi, commands.Cog):
            @comando_di_gruppo("non-esiste", nome="x", descrizione="y")
            async def x(self, interaction: discord.Interaction) -> None: ...

        registra_comandi_del_cog(_Cattivo())


# ----------------------------------------------------------------------
# Il cog vero: BasicLogsCog nel gruppo /log
# ----------------------------------------------------------------------
@pytest.fixture
async def log_cog(monkeypatch):
    database = _FakeDb()
    monkeypatch.setattr(basic_logs, "db", database)
    bot = _bot()
    cog = basic_logs.BasicLogsCog(bot)
    await bot.add_cog(cog)
    yield bot, cog, database
    await bot.remove_cog("BasicLogsCog")


async def test_basic_logs_mette_i_comandi_in_log_e_non_al_primo_livello(log_cog):
    bot, cog, _ = log_cog
    radici = {c.name: c for c in bot.tree.get_commands()}
    assert "logs-setup" not in radici and "logs-status" not in radici
    assert {c.name for c in radici["log"].commands} == {"canale", "stato"}


async def test_log_canale_blocca_chi_non_ha_il_livello(log_cog):
    bot, cog, _ = log_cog
    cmd = bot.tree.get_command("log").get_command("canale")
    with pytest.raises(ca.AccessoNegato):
        await cmd._check_can_run(_ix())
    assert await cmd._check_can_run(_ix("manage_guild")) is True


async def test_callback_di_log_canale_funziona_come_oggi(log_cog):
    _, cog, database = log_cog
    canale = fake_text_channel(channel_id=555)
    ix = _ix("manage_guild")
    await cog.logs_setup.callback(cog, ix, canale)
    assert database.scritti[(77, basic_logs.SETTING_LOG_CHANNEL)] == 555
    ix.response.send_message.assert_awaited_once()


async def test_callback_legato_dal_comando_vero(log_cog):
    bot, cog, database = log_cog
    cmd = bot.tree.get_command("log").get_command("canale")
    await cmd._do_call(_ix("manage_guild"), {"channel": fake_text_channel(channel_id=556)})
    assert database.scritti[(77, basic_logs.SETTING_LOG_CHANNEL)] == 556


async def test_caratteri_del_gruppo_log_entro_i_limiti(log_cog):
    bot, _, _ = log_cog
    gruppo = bot.tree.get_command("log")
    assert conta_caratteri(gruppo) < 6800
    for cmd in gruppo.commands:
        assert len(cmd.description) <= 100
        assert not cmd.description.startswith("[")


async def test_reload_e_unload_di_basic_logs(monkeypatch):
    monkeypatch.setattr(basic_logs, "db", _FakeDb())
    bot = _bot()
    await bot.add_cog(basic_logs.BasicLogsCog(bot))
    await bot.remove_cog("BasicLogsCog")
    assert bot.tree.get_command("log") is None
    await bot.add_cog(basic_logs.BasicLogsCog(bot))
    await bot.add_cog(basic_logs.BasicLogsCog(bot), override=True)
    assert [c.name for c in bot.tree.get_command("log").commands].count("canale") == 1
    await bot.remove_cog("BasicLogsCog")
    assert bot.tree.get_command("log") is None
    assert cg.GRUPPI["log"].commands == []


# ----------------------------------------------------------------------
# /owner non entra mai nell'albero globale; il reload non dà falsi conflitti
# ----------------------------------------------------------------------
def _cog_owner():
    class CogOwnerProva(CogConGruppi, commands.Cog):
        def __init__(self, bot):
            self.bot = bot
            self.gruppi_yokai = cg.costruisci_gruppi()

        @comando_di_gruppo("owner", nome="prova", descrizione="Comando owner di prova", sottogruppo=("system", "Sistema"))
        async def prova(self, interaction: discord.Interaction) -> None: ...

    return CogOwnerProva


async def test_un_cog_owner_caricato_e_ricaricato_non_mette_owner_nell_albero_globale():
    bot = _bot()
    classe = _cog_owner()
    cog = classe(bot)
    await bot.add_cog(cog)
    assert bot.tree.get_command("owner") is None
    assert cog.gruppi_yokai["owner"].get_command("system").get_command("prova") is not None
    await bot.add_cog(classe(bot), override=True)  # come /owner cog reload
    assert bot.tree.get_command("owner") is None
    await bot.remove_cog("CogOwnerProva")
    assert bot.tree.get_command("owner") is None


async def test_una_classe_ricreata_dal_reload_non_e_un_altro_cog():
    bot = _bot()
    primo = _cog_owner()(bot)
    registra_comandi_del_cog(primo, tree=bot.tree)
    secondo = _cog_owner()(bot)
    secondo.gruppi_yokai = primo.gruppi_yokai  # stesso albero di gruppi, classe ricreata
    assert type(primo) is not type(secondo)
    registra_comandi_del_cog(secondo, tree=bot.tree)  # niente ValueError
    assert bot.tree.get_command("owner") is None

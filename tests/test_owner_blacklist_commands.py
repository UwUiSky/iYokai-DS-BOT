"""
tests/test_owner_blacklist_commands.py
===========================================
Test del comportamento REALE dei comandi blacklist/leave-guild in
OwnerPremiumCog — non solo che il cog carica (già in test_owner_
premium_cog_smoke.py), ma che il controllo owner-only funziona
davvero e che le azioni hanno l'effetto atteso, contro PostgreSQL
reale. app_commands.Command.callback invocato direttamente (verificato
prima di scrivere questi test che è il modo corretto di chiamare il
codice sotto un @group.command senza passare per il dispatch completo
di discord.py).
"""

import discord
import pytest

from cogs.utility.owner_premium import OwnerPremiumCog
from core.config import config
from core.database import Database

_OWNER_ID = config.OWNER_ID  # valore reale già impostato dall'ambiente di test (conftest.py)


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list = []
        self.deferred = False

    async def send_message(self, content: str = None, embed=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)

    async def defer(self, ephemeral: bool = False) -> None:
        self.deferred = True


class _FakeFollowup:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def send(self, content: str, ephemeral: bool = False) -> None:
        # Stesso elenco di sent_messages della response: ai fini dei
        # test non importa se il messaggio è arrivato come risposta
        # diretta o come followup dopo un defer, conta solo cosa è
        # stato detto all'utente.
        self._response.sent_messages.append(content)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeInteraction:
    def __init__(self, user_id: int) -> None:
        self.user = _FakeUser(user_id)
        self.response = _FakeResponse()
        self.followup = _FakeFollowup(self.response)


class _FakeGuildToLeave:
    def __init__(self, guild_id: int, name: str = "Server di prova") -> None:
        self.id = guild_id
        self.name = name
        self.left = False

    async def leave(self) -> None:
        self.left = True


class _FakeBot:
    def __init__(self, guilds: dict[int, _FakeGuildToLeave] | None = None) -> None:
        self._guilds = guilds or {}

    def get_guild(self, guild_id: int):
        return self._guilds.get(guild_id)


@pytest.mark.asyncio
async def test_blacklist_user_add_rifiuta_non_owner(monkeypatch):
    cog = OwnerPremiumCog(_FakeBot())
    interaction = _FakeInteraction(user_id=_OWNER_ID + 1)  # non l'owner

    await cog.blacklist_user_add.callback(cog, interaction, user_id="1", reason=None)

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_blacklist_user_add_e_remove_funzionano_davvero(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute("DELETE FROM user_blacklist WHERE user_id = 555")
    
        from core.repositories.blacklist_repo import blacklist_repo
        original_provider = blacklist_repo._pool_provider
        blacklist_repo._pool_provider = lambda: database.pool

        try:
            cog = OwnerPremiumCog(_FakeBot())
            interaction = _FakeInteraction(user_id=_OWNER_ID)  # l'owner

            await cog.blacklist_user_add.callback(cog, interaction, user_id="555", reason="test")
            assert await blacklist_repo.is_user_blacklisted(555) is True

            interaction2 = _FakeInteraction(user_id=_OWNER_ID)
            await cog.blacklist_user_remove.callback(cog, interaction2, user_id="555")
            assert await blacklist_repo.is_user_blacklisted(555) is False
        finally:
            blacklist_repo._pool_provider = original_provider
    finally:
        await database.pool.execute("DELETE FROM user_blacklist WHERE user_id = 555")
        await database.close()


@pytest.mark.asyncio
async def test_blacklist_guild_add_fa_uscire_il_bot_se_gia_presente(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute("DELETE FROM guild_blacklist WHERE guild_id = 777")
    
        from core.repositories.blacklist_repo import blacklist_repo
        original_provider = blacklist_repo._pool_provider
        blacklist_repo._pool_provider = lambda: database.pool

        try:
            guild = _FakeGuildToLeave(777)
            cog = OwnerPremiumCog(_FakeBot(guilds={777: guild}))
            interaction = _FakeInteraction(user_id=_OWNER_ID)

            await cog.blacklist_guild_add.callback(
                cog, interaction, guild_id="777", reason="raid"
            )

            assert guild.left is True
            assert await blacklist_repo.is_guild_blacklisted(777) is True
        finally:
            blacklist_repo._pool_provider = original_provider
    finally:
        await database.pool.execute("DELETE FROM guild_blacklist WHERE guild_id = 777")
        await database.close()


@pytest.mark.asyncio
async def test_leave_guild_esce_dal_server_indicato(monkeypatch):
    guild = _FakeGuildToLeave(888, name="Server da abbandonare")
    cog = OwnerPremiumCog(_FakeBot(guilds={888: guild}))
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.leave_guild.callback(cog, interaction, guild_id="888")

    assert guild.left is True
    assert "Server da abbandonare" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_leave_guild_server_non_presente_non_solleva(monkeypatch):
    cog = OwnerPremiumCog(_FakeBot(guilds={}))
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.leave_guild.callback(cog, interaction, guild_id="999999")

    assert "non risulta presente" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_cog_load_rifiuta_non_owner():
    cog = OwnerPremiumCog(_FakeBot())
    interaction = _FakeInteraction(user_id=_OWNER_ID + 1)

    await cog.owner_cog_load.callback(cog, interaction, extension="cogs.utility.poll")

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_cog_load_unload_reload_ciclo_reale():
    # Un cog VERO e piccolo del progetto (poll, autonomo, nessuna
    # dipendenza da DB al caricamento) - carica, ricarica, scarica
    # per davvero, non un mock del bot.
    from discord.ext import commands as dpy_commands

    bot = dpy_commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = OwnerPremiumCog(bot)
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.owner_cog_load.callback(cog, interaction, extension="cogs.utility.poll")
    assert bot.get_cog("PollCog") is not None
    assert "Caricato" in interaction.response.sent_messages[-1]

    interaction2 = _FakeInteraction(user_id=_OWNER_ID)
    await cog.owner_cog_reload.callback(cog, interaction2, extension="cogs.utility.poll")
    assert bot.get_cog("PollCog") is not None
    assert "Ricaricato" in interaction2.response.sent_messages[-1]

    interaction3 = _FakeInteraction(user_id=_OWNER_ID)
    await cog.owner_cog_unload.callback(cog, interaction3, extension="cogs.utility.poll")
    assert bot.get_cog("PollCog") is None
    assert "Scaricato" in interaction3.response.sent_messages[-1]


@pytest.mark.asyncio
async def test_cog_load_modulo_inesistente_non_solleva():
    from discord.ext import commands as dpy_commands

    bot = dpy_commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = OwnerPremiumCog(bot)
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    # Non deve sollevare — un nome di modulo sbagliato è un errore
    # dell'admin, non un crash del bot.
    await cog.owner_cog_load.callback(cog, interaction, extension="cogs.questo.non.esiste")

    assert "Impossibile caricare" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_cog_unload_modulo_non_caricato_non_solleva():
    from discord.ext import commands as dpy_commands

    bot = dpy_commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = OwnerPremiumCog(bot)
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.owner_cog_unload.callback(cog, interaction, extension="cogs.utility.poll")

    assert "Impossibile scaricare" in interaction.response.sent_messages[0]


class _FakePermissionsPerAnnounce:
    def __init__(self, send_messages: bool) -> None:
        self.send_messages = send_messages


class _FakeChannelPerAnnounce:
    def __init__(self, can_send: bool) -> None:
        self._can_send = can_send
        self.sent_embeds: list = []

    def permissions_for(self, member):
        return _FakePermissionsPerAnnounce(send_messages=self._can_send)

    async def send(self, embed=None) -> None:
        self.sent_embeds.append(embed)


class _FakeGuildForAnnounce:
    def __init__(self, guild_id: int, can_send: bool) -> None:
        self.id = guild_id
        self.name = f"Server {guild_id}"
        self.me = object()
        self.owner = None
        self.owner_id = 999
        canale = _FakeChannelPerAnnounce(can_send)
        canale._can_send = can_send
        self.system_channel = canale if can_send else None
        self.text_channels = [canale] if can_send else []
        self._canale = canale

    async def fetch_member(self, member_id: int):
        raise __import__("discord").HTTPException(
            response=_FakeHTTPResponse(), message="non trovato"
        )


class _FakeBotForAnnounce:
    def __init__(self, guilds: list) -> None:
        self.guilds = guilds

    async def _send_embed_with_fallback(self, guild, embed, contesto="messaggio"):
        # Riusa la logica reale: prova a scrivere sul canale finto,
        # restituisce True/False come farebbe iYokaiBot davvero.
        if guild.system_channel is not None:
            await guild.system_channel.send(embed=embed)
            return True
        return False


@pytest.mark.asyncio
async def test_announce_rifiuta_non_owner():
    cog = OwnerPremiumCog(_FakeBotForAnnounce(guilds=[]))
    interaction = _FakeInteraction(user_id=_OWNER_ID + 1)

    await cog.announce.callback(cog, interaction, message="Ciao a tutti")

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_announce_conta_correttamente_raggiunti_e_falliti():
    guild_raggiungibile = _FakeGuildForAnnounce(100, can_send=True)
    guild_non_raggiungibile = _FakeGuildForAnnounce(200, can_send=False)
    bot = _FakeBotForAnnounce(guilds=[guild_raggiungibile, guild_non_raggiungibile])
    cog = OwnerPremiumCog(bot)
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.announce.callback(cog, interaction, message="Nuovo aggiornamento!")

    testo_risposta = interaction.response.sent_messages[-1]
    assert "1 server" in testo_risposta
    assert "1 non raggiunti" in testo_risposta
    assert len(guild_raggiungibile._canale.sent_embeds) == 1


class _FakeGuildForStats:
    def __init__(self, member_count: int) -> None:
        self.member_count = member_count


class _FakeBotForStats:
    def __init__(self, guilds: list, latency: float = 0.05, latencies: list | None = None) -> None:
        self.guilds = guilds
        self.latency = latency
        self.latencies = latencies or []


@pytest.mark.asyncio
async def test_stats_rifiuta_non_owner():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
    interaction = _FakeInteraction(user_id=_OWNER_ID + 1)

    await cog.stats.callback(cog, interaction)

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_stats_mostra_numeri_reali(monkeypatch):
    # command_counter/error_counter sono singleton GLOBALI condivisi
    # da tutta la suite - altri test (test_premium_error_handler.py)
    # incrementano il contatore errori vero senza isolarlo. Qui
    # servono valori deterministici, quindi verifichiamo solo che
    # siano numeri validi non negativi, non un "0" esatto.
    guilds = [_FakeGuildForStats(100), _FakeGuildForStats(50)]
    bot = _FakeBotForStats(guilds=guilds, latency=0.123, latencies=[(0, 0.1), (1, 0.2)])
    cog = OwnerPremiumCog(bot)
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.stats.callback(cog, interaction)

    assert len(interaction.response.sent_embeds) == 1
    embed = interaction.response.sent_embeds[0]
    valori_per_campo = {campo.name: campo.value for campo in embed.fields}

    assert valori_per_campo["Server"] == "2"
    assert valori_per_campo["Membri totali (stimati)"] == "150"
    assert valori_per_campo["Latenza"] == "123 ms"
    assert "Shard 0: 100 ms" in valori_per_campo["Shard"]
    assert "Shard 1: 200 ms" in valori_per_campo["Shard"]
    # Comandi/errori: valori non negativi e coerenti col tipo, non un
    # "0" esatto - il contatore è globale e condiviso con altri test
    # della suite che lo incrementano legittimamente nella stessa
    # finestra di 60s.
    assert int(valori_per_campo["Comandi (ultimo minuto)"]) >= 0
    assert int(valori_per_campo["Errori (ultimo minuto)"]) >= 0


class _FakeResponseForPanel:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list = []
        self.edited_embeds: list = []
        self.edited_views: list = []

    async def send_message(self, content: str = None, embed=None, view=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)

    async def edit_message(self, embed=None, view=None) -> None:
        self.edited_embeds.append(embed)
        self.edited_views.append(view)


class _FakeInteractionForPanel:
    def __init__(self, user_id: int) -> None:
        self.user = _FakeUser(user_id)
        self.response = _FakeResponseForPanel()


@pytest.mark.asyncio
async def test_premium_panel_rifiuta_non_owner():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
    interaction = _FakeInteractionForPanel(user_id=_OWNER_ID + 1)

    await cog.premium_panel.callback(cog, interaction)

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_premium_panel_ciclo_completo_selezione_e_conferma(monkeypatch):
    import cogs.utility.owner_premium as owner_premium_module
    from core.premium import PremiumModule, PremiumRegistry

    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM premium_module_flags WHERE module_name = 'modulo_test_panel'"
        )
        await database.pool.execute(
            "DELETE FROM premium_toggle_history WHERE module_name = 'modulo_test_panel'"
        )

        registry_isolato = PremiumRegistry()
        registry_isolato.register(
            PremiumModule(
                name="modulo_test_panel",
                display_name="Modulo Test Panel",
                description="Per il test del pannello",
                premium_capable=True,
            )
        )
        monkeypatch.setattr(owner_premium_module, "registry", registry_isolato)
        monkeypatch.setattr(owner_premium_module, "db", database)

        cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))

        # Step 0: apre il pannello.
        interaction_apertura = _FakeInteractionForPanel(user_id=_OWNER_ID)
        await cog.premium_panel.callback(cog, interaction_apertura)
        assert len(interaction_apertura.response.sent_embeds) == 1

        # Step 1: seleziona il modulo dal menu (nessun modulo è
        # ancora premium -> il toggle proposto sarà True). Il fake
        # non salva la view passata a send_message, quindi ne
        # costruiamo una equivalente direttamente per invocarne il
        # Select.
        from cogs.utility.owner_premium import _PremiumPanelView

        panel_view = _PremiumPanelView(cog, [registry_isolato.get("modulo_test_panel")])
        select = panel_view.children[0]
        select._values = ["modulo_test_panel"]

        interaction_selezione = _FakeInteractionForPanel(user_id=_OWNER_ID)
        await select.callback(interaction_selezione)

        assert len(interaction_selezione.response.edited_embeds) == 1
        assert "Conferma richiesta" in interaction_selezione.response.edited_embeds[0].title
        confirm_view = interaction_selezione.response.edited_views[0]

        # Step 2: conferma.
        interaction_conferma = _FakeInteractionForPanel(user_id=_OWNER_ID)
        conferma_button = confirm_view.children[0]  # "Conferma"
        await conferma_button.callback(interaction_conferma)

        assert registry_isolato.get("modulo_test_panel").is_premium_active is True
        assert "aggiornato" in interaction_conferma.response.edited_embeds[0].title.lower()

        riga_storico = await database.pool.fetchrow(
            "SELECT * FROM premium_toggle_history WHERE module_name = 'modulo_test_panel'"
        )
        assert riga_storico is not None
        assert riga_storico["new_value"] is True
        assert riga_storico["changed_by"] == _OWNER_ID
    finally:
        await database.pool.execute(
            "DELETE FROM premium_module_flags WHERE module_name = 'modulo_test_panel'"
        )
        await database.pool.execute(
            "DELETE FROM premium_toggle_history WHERE module_name = 'modulo_test_panel'"
        )
        await database.close()


@pytest.mark.asyncio
async def test_premium_panel_annulla_non_applica_nulla(monkeypatch):
    import cogs.utility.owner_premium as owner_premium_module
    from core.premium import PremiumModule, PremiumRegistry

    database = Database()
    await database.connect()
    try:
        await database.run_migrations()

        registry_isolato = PremiumRegistry()
        registry_isolato.register(
            PremiumModule(
                name="modulo_test_annulla",
                display_name="Modulo Test Annulla",
                description="Per il test di annullamento",
                premium_capable=True,
            )
        )
        monkeypatch.setattr(owner_premium_module, "registry", registry_isolato)
        monkeypatch.setattr(owner_premium_module, "db", database)

        cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
        from cogs.utility.owner_premium import _PremiumConfirmView

        confirm_view = _PremiumConfirmView(
            cog, registry_isolato.get("modulo_test_annulla"), nuovo_stato=True
        )
        interaction_annulla = _FakeInteractionForPanel(user_id=_OWNER_ID)
        annulla_button = confirm_view.children[1]  # "Annulla"
        await annulla_button.callback(interaction_annulla)

        assert registry_isolato.get("modulo_test_annulla").is_premium_active is False
        assert "Annullato" in interaction_annulla.response.edited_embeds[0].title
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_eval_rifiuta_non_owner():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
    interaction = _FakeInteractionForPanel(user_id=_OWNER_ID + 1)

    await cog.eval_code.callback(cog, interaction, code="1+1")

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_run_eval_espressione_semplice():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
    interaction = _FakeInteractionForPanel(user_id=_OWNER_ID)

    output, successo = await cog._run_eval("return 1 + 1", interaction)

    assert successo is True
    assert "2" in output


@pytest.mark.asyncio
async def test_run_eval_con_await():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
    interaction = _FakeInteractionForPanel(user_id=_OWNER_ID)

    output, successo = await cog._run_eval(
        "import asyncio\nawait asyncio.sleep(0)\nreturn 'fatto'", interaction
    )

    assert successo is True
    assert "fatto" in output


@pytest.mark.asyncio
async def test_run_eval_con_print_cattura_stdout():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
    interaction = _FakeInteractionForPanel(user_id=_OWNER_ID)

    output, successo = await cog._run_eval("print('ciao dal test')", interaction)

    assert successo is True
    assert "ciao dal test" in output


@pytest.mark.asyncio
async def test_run_eval_codice_che_solleva_restituisce_traceback():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
    interaction = _FakeInteractionForPanel(user_id=_OWNER_ID)

    output, successo = await cog._run_eval("raise ValueError('errore di prova')", interaction)

    assert successo is False
    assert "ValueError" in output
    assert "errore di prova" in output


@pytest.mark.asyncio
async def test_run_shell_comando_semplice():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))

    output, successo = await cog._run_shell("echo ciao")

    assert successo is True
    assert "ciao" in output


@pytest.mark.asyncio
async def test_run_shell_comando_con_exit_code_diverso_da_zero():
    cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))

    output, successo = await cog._run_shell("exit 1")

    assert successo is False


@pytest.mark.asyncio
async def test_eval_ciclo_completo_conferma_esegue_e_logga(monkeypatch):
    import cogs.utility.owner_premium as owner_premium_module
    from core.repositories.eval_shell_log_repo import EvalShellLogRepository

    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM eval_shell_log WHERE code_or_command = 'return 40 + 2'"
        )
        monkeypatch.setattr(
            owner_premium_module,
            "eval_shell_log_repo",
            EvalShellLogRepository(pool_provider=lambda: database.pool),
        )

        cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
        from cogs.utility.owner_premium import _EvalConfirmView

        view = _EvalConfirmView(cog, "return 40 + 2")
        interaction = _FakeInteractionForPanel(user_id=_OWNER_ID)
        esegui_button = view.children[0]

        await esegui_button.callback(interaction)

        assert "42" in interaction.response.edited_embeds[0].description

        riga = await database.pool.fetchrow(
            "SELECT * FROM eval_shell_log WHERE code_or_command = 'return 40 + 2'"
        )
        assert riga is not None
        assert riga["success"] is True
        assert riga["executor_id"] == _OWNER_ID
    finally:
        await database.pool.execute(
            "DELETE FROM eval_shell_log WHERE code_or_command = 'return 40 + 2'"
        )
        await database.close()


@pytest.mark.asyncio
async def test_eval_annulla_non_esegue_ne_logga(monkeypatch):
    import cogs.utility.owner_premium as owner_premium_module
    from core.repositories.eval_shell_log_repo import EvalShellLogRepository

    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute(
            "DELETE FROM eval_shell_log WHERE code_or_command = 'return 99'"
        )
        monkeypatch.setattr(
            owner_premium_module,
            "eval_shell_log_repo",
            EvalShellLogRepository(pool_provider=lambda: database.pool),
        )

        cog = OwnerPremiumCog(_FakeBotForStats(guilds=[]))
        from cogs.utility.owner_premium import _EvalConfirmView

        view = _EvalConfirmView(cog, "return 99")
        interaction = _FakeInteractionForPanel(user_id=_OWNER_ID)
        annulla_button = view.children[1]

        await annulla_button.callback(interaction)

        assert "Annullato" in interaction.response.edited_embeds[0].title
        riga = await database.pool.fetchrow(
            "SELECT * FROM eval_shell_log WHERE code_or_command = 'return 99'"
        )
        assert riga is None
    finally:
        await database.close()

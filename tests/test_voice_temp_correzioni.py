"""
tests/test_voice_temp_correzioni.py
===================================
Correzioni ai vocali temporanei (issue #63, voci M 7.x).

Database vero (clean_db) e repository vero. I canali si creano con il
codice di produzione (`_create_temp_channel`, lo stesso del canale
generatore e del pannello); di Discord ci sono solo i finti fedeli di
tests/support/discord_fakes.py.
"""

import asyncio
from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.voice_temp.voice_temp as modulo
import core.channel_rename as rinomina
from cogs.voice_temp.voice_temp import VoiceTempCog, _create_temp_channel
from core.repositories.voice_temp_repo import voice_temp_repo
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_voice_channel,
)

ID_SERVER = 100
ID_PROPRIETARIO = 10
ID_OSPITE = 20


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    rinomina.rename_tracker._renames.clear()
    yield
    rinomina.rename_tracker._renames.clear()
    database_module.db._modules_cache.clear()


def _errore_http(stato: int = 400) -> discord.HTTPException:
    return discord.HTTPException(MagicMock(status=stato, reason="errore"), "errore finto")


class Scena:
    """Un server finto con una categoria che crea vocali numerati da 2000."""

    def __init__(self) -> None:
        self.guild = fake_guild(ID_SERVER)
        self.guild.default_role = fake_role(role_id=ID_SERVER, name="@everyone", position=0)
        self.membri: dict[int, MagicMock] = {}
        self.guild.get_member.side_effect = self.membri.get
        self.canali: dict[int, MagicMock] = {}
        self.guild.get_channel.side_effect = self.canali.get
        self.categoria = create_autospec(discord.CategoryChannel, instance=True)
        self.categoria.id = 900
        self.categoria.channels = []
        self.categoria.create_voice_channel.side_effect = self._crea_canale

    async def _crea_canale(self, name, **kwargs):
        canale = fake_voice_channel(2000 + len(self.canali), name)
        canale.guild = self.guild
        # Come il vero: un canale nuovo non ha override per @everyone.
        canale.overwrites_for.return_value = discord.PermissionOverwrite()
        self.canali[canale.id] = canale
        return canale

    def membro(self, user_id: int, *, bot: bool = False, manage_channels: bool = False):
        if user_id not in self.membri:
            membro = fake_member(
                user_id,
                bot=bot,
                guild_permissions=discord.Permissions(manage_channels=manage_channels),
            )
            membro.guild = self.guild
            membro.display_name = f"utente{user_id}"
            membro.voice = None
            self.membri[user_id] = membro
        return self.membri[user_id]

    def entra(self, membro, canale):
        membro.voice = create_autospec(discord.VoiceState, instance=True)
        membro.voice.channel = canale
        canale.members.append(membro)
        return membro

    async def crea_canale_di(self, proprietario):
        """Crea il vocale temporaneo come fa il bot e ci mette dentro il proprietario."""
        config = await voice_temp_repo.get_config(ID_SERVER)
        canale = await _create_temp_channel(self.guild, proprietario, self.categoria, config)
        self.entra(proprietario, canale)
        return canale

    def interazione(self, utente):
        return fake_interaction(guild=self.guild, user=utente)


def _testo(chiamata) -> str:
    return chiamata.args[0] if chiamata.args else chiamata.kwargs.get("content", "")


def _con_ruolo(membro, posizione: int, **permessi):
    membro.top_role = fake_role(role_id=500 + posizione, name=f"r{posizione}", position=posizione)
    if permessi:
        membro.guild_permissions = discord.Permissions(**permessi)
    return membro


# ====================================================================
# M 7.1 — /voice rename: nome fino a 100 caratteri
# M 7.2 — terza rinomina in 10 minuti: messaggio, nessuna attesa
# ====================================================================
async def test_voice_rename_dichiara_da_1_a_100_caratteri():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot.add_cog(VoiceTempCog(bot))

    comando = bot.tree.get_command("voice").get_command("rename")
    opzioni = {o["name"]: o for o in comando.to_dict(bot.tree)["options"]}

    assert opzioni["name"]["min_length"] == 1
    assert opzioni["name"]["max_length"] == 100


async def _rinomina(scena, utente, nome: str):
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(utente)
    await cog.rename.callback(cog, interazione, nome)
    return interazione


async def test_la_terza_rinomina_risponde_subito_riprova_tra():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)

    for nome in ("Ranked", "Chill"):
        riuscita = await _rinomina(scena, proprietario, nome)
        riuscita.response.defer.assert_awaited_once()
        assert nome in _testo(riuscita.followup.send.call_args)
    terza = await _rinomina(scena, proprietario, "Terzo nome")

    assert [c.kwargs["name"] for c in canale.edit.call_args_list] == ["Ranked", "Chill"]
    risposta = terza.response.send_message.call_args
    assert "Riprova tra circa 10 minuti" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True
    terza.response.defer.assert_not_awaited()


async def test_rinomina_rifiutata_da_discord_risposta_chiara():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.edit.side_effect = _errore_http(400)

    interazione = await _rinomina(scena, proprietario, "nome vietato")

    assert "Non sono riuscito a rinominare" in _testo(interazione.followup.send.call_args)
    # Un errore non consuma una delle due rinomine.
    assert rinomina.rename_tracker.seconds_until_allowed(canale.id) == 0


async def test_rinomina_con_discord_in_attesa_non_resta_appesa(monkeypatch):
    monkeypatch.setattr(rinomina, "RENAME_TIMEOUT_SECONDS", 0.05)
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)

    async def _attesa_infinita(**kwargs):
        await asyncio.sleep(600)

    canale.edit.side_effect = _attesa_infinita

    interazione = await asyncio.wait_for(_rinomina(scena, proprietario, "nuovo"), timeout=2)

    assert "Riprova tra circa 10 minuti" in _testo(interazione.followup.send.call_args)


async def test_il_nome_nella_conferma_non_puo_menzionare_nessuno():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    await scena.crea_canale_di(proprietario)

    interazione = await _rinomina(scena, proprietario, "@everyone")

    menzioni = interazione.followup.send.call_args.kwargs["allowed_mentions"]
    assert menzioni.to_dict() == discord.AllowedMentions.none().to_dict()


@pytest.mark.parametrize("comando", ("limit", "lock", "unlock", "kick"))
async def test_gli_altri_comandi_di_gestione_gestiscono_l_errore_di_discord(comando):
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 5)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.entra(scena.membro(ID_OSPITE), canale)
    scena.guild.me.top_role = fake_role(role_id=900, name="bot", position=50)
    canale.edit.side_effect = _errore_http(403)
    canale.set_permissions.side_effect = _errore_http(403)
    ospite.move_to.side_effect = _errore_http(403)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)

    if comando == "limit":
        await cog.limit.callback(cog, interazione, 5)
    elif comando == "kick":
        await cog.kick.callback(cog, interazione, ospite)
    else:
        await getattr(cog, comando).callback(cog, interazione)

    risposta = interazione.response.send_message.call_args
    assert "Non sono riuscito" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True


# ====================================================================
# M 7.4 — /voice transfer sposta i permessi del canale (BUG-18)
# ====================================================================
PERMESSI_DEL_PROPRIETARIO = ("manage_channels", "move_members", "mute_members")


async def _trasferisci(scena, chi, a_chi):
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(chi)
    await cog.transfer.callback(cog, interazione, a_chi)
    return interazione


def _permessi_dati(canale) -> dict:
    """bersaglio -> PermissionOverwrite (o None se tolto) delle chiamate a set_permissions."""
    esito = {}
    for chiamata in canale.set_permissions.call_args_list:
        bersaglio = chiamata.args[0]
        if "overwrite" in chiamata.kwargs:
            esito[bersaglio.id] = chiamata.kwargs["overwrite"]
        else:
            permessi = {k: v for k, v in chiamata.kwargs.items() if k != "reason"}
            esito[bersaglio.id] = discord.PermissionOverwrite(**permessi)
    return esito


async def test_transfer_sposta_i_permessi_e_il_nuovo_proprietario_puo_rinominare():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)

    interazione = await _trasferisci(scena, vecchio, nuovo)

    assert await voice_temp_repo.get_owner(canale.id) == ID_OSPITE
    permessi = _permessi_dati(canale)
    for nome in PERMESSI_DEL_PROPRIETARIO:
        assert getattr(permessi[ID_OSPITE], nome) is True, nome
    assert permessi[ID_PROPRIETARIO] is None  # al vecchio proprietario vengono tolti
    assert nuovo.mention in _testo(interazione.response.send_message.call_args)

    # Il nuovo proprietario gestisce il canale, il vecchio non più.
    riuscita = await _rinomina(scena, nuovo, "Nuovo nome")
    assert canale.edit.call_args.kwargs["name"] == "Nuovo nome"
    assert "Nuovo nome" in _testo(riuscita.followup.send.call_args)
    rifiutata = await _rinomina(scena, vecchio, "Ci riprovo")
    assert "Solo il proprietario" in _testo(rifiutata.response.send_message.call_args)
    assert canale.edit.await_count == 1


async def test_transfer_fatto_dallo_staff_toglie_i_permessi_al_vero_proprietario():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)
    staff = scena.entra(scena.membro(30, manage_channels=True), canale)

    await _trasferisci(scena, staff, nuovo)

    permessi = _permessi_dati(canale)
    assert permessi[ID_PROPRIETARIO] is None
    assert 30 not in permessi
    assert await voice_temp_repo.get_owner(canale.id) == ID_OSPITE


async def test_transfer_permessi_rifiutati_da_discord_la_proprieta_non_cambia():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)
    canale.set_permissions.side_effect = _errore_http(403)

    interazione = await _trasferisci(scena, vecchio, nuovo)

    assert await voice_temp_repo.get_owner(canale.id) == ID_PROPRIETARIO
    risposta = interazione.response.send_message.call_args
    assert "Non sono riuscito" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True


async def test_transfer_a_chi_e_gia_proprietario_non_fa_nulla():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)

    interazione = await _trasferisci(scena, proprietario, proprietario)

    canale.set_permissions.assert_not_awaited()
    assert "già il proprietario" in _testo(interazione.response.send_message.call_args)


async def test_transfer_con_il_vecchio_proprietario_uscito_dal_server():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)
    staff = scena.entra(scena.membro(30, manage_channels=True), canale)
    del scena.membri[ID_PROPRIETARIO]  # non è più nel server

    await _trasferisci(scena, staff, nuovo)

    assert await voice_temp_repo.get_owner(canale.id) == ID_OSPITE
    assert list(_permessi_dati(canale)) == [ID_OSPITE]


# ====================================================================
# M 7.5 — pulizia all'avvio dei canali rimasti orfani
# ====================================================================
def _bot_con(scena):
    bot = create_autospec(commands.Bot, instance=True)
    bot.get_guild.side_effect = lambda guild_id: scena.guild if guild_id == ID_SERVER else None
    return bot


async def _invecchia_i_canali(clean_db) -> None:
    """Fa passare il tempo: i canali risultano creati dieci minuti fa."""
    await clean_db.execute(
        "UPDATE voice_temp_channels SET created_at = now() - interval '10 minutes'"
    )


async def _canale_vuoto(scena, user_id: int):
    """Un vocale temporaneo il cui proprietario è uscito mentre il bot era spento."""
    membro = scena.membro(user_id)
    canale = await scena.crea_canale_di(membro)
    canale.members.clear()
    return canale


async def test_canale_vuoto_all_avvio_viene_cancellato(clean_db):
    scena = Scena()
    vuoto = await _canale_vuoto(scena, ID_PROPRIETARIO)
    await _invecchia_i_canali(clean_db)

    await VoiceTempCog(_bot_con(scena)).on_ready()

    vuoto.delete.assert_awaited_once()
    assert await voice_temp_repo.get_owner(vuoto.id) is None


async def test_canale_con_persone_dentro_all_avvio_resta(clean_db):
    scena = Scena()
    pieno = await scena.crea_canale_di(scena.membro(ID_PROPRIETARIO))
    await _invecchia_i_canali(clean_db)

    await VoiceTempCog(_bot_con(scena)).on_ready()

    pieno.delete.assert_not_awaited()
    assert await voice_temp_repo.get_owner(pieno.id) == ID_PROPRIETARIO


async def test_canale_che_non_esiste_piu_viene_tolto_dal_registro(clean_db):
    scena = Scena()
    sparito = await _canale_vuoto(scena, ID_PROPRIETARIO)
    del scena.canali[sparito.id]  # cancellato a mano mentre il bot era spento
    await _invecchia_i_canali(clean_db)

    await VoiceTempCog(_bot_con(scena)).on_ready()

    sparito.delete.assert_not_awaited()
    assert await voice_temp_repo.get_owner(sparito.id) is None


async def test_canale_appena_creato_e_ancora_vuoto_non_viene_toccato():
    """
    Dal pannello il canale nasce vuoto e l'utente entra dopo. on_ready
    arriva anche a ogni riconnessione: non deve cancellarglielo sotto
    i piedi.
    """
    scena = Scena()
    appena_creato = await _canale_vuoto(scena, ID_PROPRIETARIO)

    await VoiceTempCog(_bot_con(scena)).on_ready()

    appena_creato.delete.assert_not_awaited()
    assert await voice_temp_repo.get_owner(appena_creato.id) == ID_PROPRIETARIO


async def test_un_canale_che_non_si_riesce_a_cancellare_non_ferma_gli_altri(clean_db):
    scena = Scena()
    bloccato = await _canale_vuoto(scena, ID_PROPRIETARIO)
    bloccato.delete.side_effect = discord.Forbidden(
        MagicMock(status=403, reason="Forbidden"), "Missing Permissions"
    )
    secondo = await _canale_vuoto(scena, ID_OSPITE)
    await _invecchia_i_canali(clean_db)

    await VoiceTempCog(_bot_con(scena)).on_ready()

    # Resta nel registro: si riprova al prossimo avvio.
    assert await voice_temp_repo.get_owner(bloccato.id) == ID_PROPRIETARIO
    secondo.delete.assert_awaited_once()
    assert await voice_temp_repo.get_owner(secondo.id) is None


async def test_canale_gia_cancellato_da_discord_viene_tolto_dal_registro(clean_db):
    scena = Scena()
    canale = await _canale_vuoto(scena, ID_PROPRIETARIO)
    canale.delete.side_effect = discord.NotFound(
        MagicMock(status=404, reason="Not Found"), "Unknown Channel"
    )
    await _invecchia_i_canali(clean_db)

    await VoiceTempCog(_bot_con(scena)).on_ready()

    assert await voice_temp_repo.get_owner(canale.id) is None


async def test_server_non_raggiungibile_all_avvio_i_suoi_canali_restano(clean_db):
    """Un server in outage non è nella cache: non si decide niente su di lui."""
    scena = Scena()
    canale = await _canale_vuoto(scena, ID_PROPRIETARIO)
    await _invecchia_i_canali(clean_db)
    bot = _bot_con(scena)
    bot.get_guild.side_effect = lambda guild_id: None

    await VoiceTempCog(bot).on_ready()

    canale.delete.assert_not_awaited()
    assert await voice_temp_repo.get_owner(canale.id) == ID_PROPRIETARIO


async def test_cancellazione_fallita_all_uscita_il_canale_resta_nel_registro(clean_db):
    """
    Se Discord non cancella il canale quando esce l'ultima persona, il
    canale deve restare registrato: così la pulizia all'avvio lo ritrova.
    """
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.members.clear()
    canale.delete.side_effect = discord.DiscordServerError(
        MagicMock(status=503, reason="Service Unavailable"), "upstream"
    )
    prima = create_autospec(discord.VoiceState, instance=True)
    prima.channel = canale
    dopo = create_autospec(discord.VoiceState, instance=True)
    dopo.channel = None
    cog = VoiceTempCog(_bot_con(scena))

    await cog.on_voice_state_update(proprietario, prima, dopo)

    assert await voice_temp_repo.get_owner(canale.id) == ID_PROPRIETARIO

    # Al riavvio Discord risponde di nuovo: il canale sparisce.
    canale.delete.side_effect = None
    await _invecchia_i_canali(clean_db)
    await cog.on_ready()
    assert await voice_temp_repo.get_owner(canale.id) is None


# ====================================================================
# M 7.6 — i bottoni piattaforma sopravvivono a un riavvio (LIM-26)
# ====================================================================
ID_RUOLO_PC = 601
ID_RUOLO_MOBILE = 603


async def _configura_piattaforme(scena) -> dict[int, MagicMock]:
    """Configura i vocali e due ruoli piattaforma con i comandi veri dell'admin."""
    scena.guild.me.top_role = fake_role(role_id=1, position=50)
    admin = scena.membro(1)
    admin.top_role = fake_role(role_id=2, position=40)
    ruoli = {
        ID_RUOLO_PC: fake_role(ID_RUOLO_PC, "PC", position=5),
        ID_RUOLO_MOBILE: fake_role(ID_RUOLO_MOBILE, "Mobile", position=4),
    }
    scena.guild.get_role.side_effect = ruoli.get
    cog = VoiceTempCog(bot=None)
    await cog.voicetemp_setup.callback(
        cog, scena.interazione(admin), fake_voice_channel(800, "Crea"), scena.categoria
    )
    await cog.voicetemp_platform_setup.callback(
        cog, scena.interazione(admin), ruoli[ID_RUOLO_PC], None, ruoli[ID_RUOLO_MOBILE]
    )
    return ruoli


async def _bot_riavviato() -> commands.Bot:
    """Un bot nuovo, come dopo un riavvio: carica il cog e nient'altro."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    return bot


def _bottone_persistente(bot, chiave: str):
    for vista in bot.persistent_views:
        for elemento in vista.children:
            if elemento.custom_id == f"iyokai_voice_temp_platform_{chiave}":
                return elemento
    raise AssertionError(f"Nessuna view persistente registrata per il bottone {chiave}")


async def test_il_messaggio_del_canale_ha_bottoni_che_non_scadono():
    scena = Scena()
    await _configura_piattaforme(scena)

    canale = await scena.crea_canale_di(scena.membro(ID_PROPRIETARIO))

    vista = canale.send.call_args.kwargs["view"]
    assert vista.timeout is None
    assert vista.is_persistent()
    # Solo le piattaforme configurate.
    assert [b.custom_id for b in vista.children] == [
        "iyokai_voice_temp_platform_pc",
        "iyokai_voice_temp_platform_mobile",
    ]


async def test_la_view_del_messaggio_non_resta_in_memoria_e_il_clic_arriva_lo_stesso():
    """
    Con il registro delle view vero di discord.py: la view legata al
    singolo messaggio viene fermata (niente accumulo, una per canale),
    e il clic su quel messaggio arriva alla view registrata all'avvio.
    """
    scena = Scena()
    await _configura_piattaforme(scena)
    bot = await _bot_riavviato()
    try:
        registro = bot._connection._view_store
        canale = await scena.crea_canale_di(scena.membro(ID_PROPRIETARIO))
        vista = canale.send.call_args.kwargs["view"]
        id_messaggio = 123456
        registro.add_view(vista, id_messaggio)  # ciò che fa channel.send dopo l'invio
        vista.stop()  # già chiamato dal codice: qui vale per il registro vero

        assert vista.is_finished()
        assert id_messaggio not in registro._views
        chiave = (discord.ComponentType.button.value, "iyokai_voice_temp_platform_pc")
        assert registro._views[None][chiave] is _bottone_persistente(bot, "pc")
    finally:
        await bot.close()


async def test_dopo_un_riavvio_il_bottone_assegna_ancora_il_ruolo():
    scena = Scena()
    ruoli = await _configura_piattaforme(scena)
    await scena.crea_canale_di(scena.membro(ID_PROPRIETARIO))
    bot = await _bot_riavviato()
    try:
        giocatore = scena.membro(ID_OSPITE)
        giocatore.roles = [ruoli[ID_RUOLO_MOBILE]]  # aveva scelto Mobile
        interazione = scena.interazione(giocatore)

        await _bottone_persistente(bot, "pc").callback(interazione)

        giocatore.add_roles.assert_awaited_once()
        assert giocatore.add_roles.call_args.args == (ruoli[ID_RUOLO_PC],)
        giocatore.remove_roles.assert_awaited_once()
        assert giocatore.remove_roles.call_args.args == (ruoli[ID_RUOLO_MOBILE],)
        risposta = interazione.response.send_message.call_args
        assert "Piattaforma impostata" in _testo(risposta)
        assert risposta.kwargs["ephemeral"] is True
    finally:
        await bot.close()


async def test_bottone_di_una_piattaforma_non_piu_configurata_lo_dice():
    """Un vecchio messaggio ha ancora il bottone Console, tolto poi dall'admin."""
    scena = Scena()
    await _configura_piattaforme(scena)
    bot = await _bot_riavviato()
    try:
        giocatore = scena.membro(ID_OSPITE)
        interazione = scena.interazione(giocatore)

        await _bottone_persistente(bot, "console").callback(interazione)

        giocatore.add_roles.assert_not_awaited()
        assert "non è più configurata" in _testo(interazione.response.send_message.call_args)
    finally:
        await bot.close()


# ====================================================================
# #134 — /voice kick: l'utente non è nel canale
# ====================================================================
async def test_kick_di_chi_non_e_nel_canale_lo_dice_e_non_dice_espulso():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    await scena.crea_canale_di(proprietario)
    assente = scena.membro(ID_OSPITE)  # non connesso a nessun vocale
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)

    await cog.kick.callback(cog, interazione, assente)

    assente.move_to.assert_not_awaited()
    risposta = interazione.response.send_message.call_args
    assert "non è nel canale" in _testo(risposta)
    assert "espulso" not in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True


async def test_kick_di_chi_e_nel_canale_lo_espelle():
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 5)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.entra(scena.membro(ID_OSPITE), canale)
    scena.guild.me.top_role = fake_role(role_id=900, name="bot", position=50)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)

    await cog.kick.callback(cog, interazione, ospite)

    ospite.move_to.assert_awaited_once()
    assert "espulso" in _testo(interazione.response.send_message.call_args)


# ====================================================================
# #134 — /voice lock cambia solo "Connetti" per @everyone
# ====================================================================
def _overwrite_finale(canale, ruolo) -> discord.PermissionOverwrite | None:
    chiamata = canale.set_permissions.call_args
    assert chiamata.args[0] is ruolo
    if "overwrite" in chiamata.kwargs:
        return chiamata.kwargs["overwrite"]
    return discord.PermissionOverwrite(
        **{k: v for k, v in chiamata.kwargs.items() if k != "reason"}
    )


async def test_lock_cambia_solo_connetti_e_lascia_gli_altri_permessi_di_everyone():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.overwrites_for.return_value = discord.PermissionOverwrite(
        speak=False, view_channel=True
    )
    cog = VoiceTempCog(bot=None)

    await cog.lock.callback(cog, scena.interazione(proprietario))

    finale = _overwrite_finale(canale, scena.guild.default_role)
    assert finale.connect is False
    assert finale.speak is False
    assert finale.view_channel is True


async def test_unlock_toglie_solo_connetti_e_lascia_gli_altri_permessi_di_everyone():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.overwrites_for.return_value = discord.PermissionOverwrite(
        connect=False, speak=False
    )
    cog = VoiceTempCog(bot=None)

    await cog.unlock.callback(cog, scena.interazione(proprietario))

    finale = _overwrite_finale(canale, scena.guild.default_role)
    assert finale.connect is None
    assert finale.speak is False


async def test_unlock_senza_altri_permessi_toglie_l_overwrite():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.overwrites_for.return_value = discord.PermissionOverwrite(connect=False)
    cog = VoiceTempCog(bot=None)

    await cog.unlock.callback(cog, scena.interazione(proprietario))

    assert _overwrite_finale(canale, scena.guild.default_role) is None


# ====================================================================
# #144 — /voice kick: controllo di gerarchia (core/permissions.py)
# ====================================================================
async def _kick(scena, proprietario, ospite):
    scena.guild.me.top_role = fake_role(role_id=900, name="bot", position=50)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)
    await cog.kick.callback(cog, interazione, ospite)
    return interazione


async def test_kick_di_un_membro_con_ruolo_piu_alto_e_negato():
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 2)
    canale = await scena.crea_canale_di(proprietario)
    ospite = _con_ruolo(scena.entra(scena.membro(ID_OSPITE), canale), 5)

    interazione = await _kick(scena, proprietario, ospite)

    ospite.move_to.assert_not_awaited()
    risposta = interazione.response.send_message.call_args
    assert "espulso" not in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True


async def test_kick_di_un_amministratore_e_negato_anche_con_ruolo_basso():
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 5)
    canale = await scena.crea_canale_di(proprietario)
    admin = _con_ruolo(
        scena.entra(scena.membro(ID_OSPITE, manage_channels=True), canale),
        1,
        administrator=True,
    )

    interazione = await _kick(scena, proprietario, admin)

    admin.move_to.assert_not_awaited()
    assert interazione.response.send_message.call_args.kwargs["ephemeral"] is True


async def test_kick_di_un_moderatore_e_negato_anche_con_ruolo_basso():
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 5)
    canale = await scena.crea_canale_di(proprietario)
    moderatore = _con_ruolo(
        scena.entra(scena.membro(ID_OSPITE), canale), 1, moderate_members=True
    )

    await _kick(scena, proprietario, moderatore)

    moderatore.move_to.assert_not_awaited()


async def test_kick_di_un_membro_con_ruolo_piu_basso_funziona():
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 5)
    canale = await scena.crea_canale_di(proprietario)
    ospite = _con_ruolo(scena.entra(scena.membro(ID_OSPITE), canale), 2)

    interazione = await _kick(scena, proprietario, ospite)

    ospite.move_to.assert_awaited_once()
    assert "espulso" in _testo(interazione.response.send_message.call_args)
# ====================================================================
# #144 — /voice unlock ripristina il "Connetti" che @everyone aveva prima
# ====================================================================
async def test_unlock_ripristina_il_connetti_che_c_era_prima_del_lock():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    cog = VoiceTempCog(bot=None)
    canale.overwrites_for.return_value = discord.PermissionOverwrite(connect=True, speak=False)
    await cog.lock.callback(cog, scena.interazione(proprietario))
    canale.overwrites_for.return_value = _overwrite_finale(canale, scena.guild.default_role)

    await cog.unlock.callback(cog, scena.interazione(proprietario))

    finale = _overwrite_finale(canale, scena.guild.default_role)
    assert finale.connect is True
    assert finale.speak is False


async def test_unlock_dopo_due_lock_ripristina_il_valore_originale():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    cog = VoiceTempCog(bot=None)
    canale.overwrites_for.return_value = discord.PermissionOverwrite(connect=True)
    await cog.lock.callback(cog, scena.interazione(proprietario))
    canale.overwrites_for.return_value = _overwrite_finale(canale, scena.guild.default_role)
    await cog.lock.callback(cog, scena.interazione(proprietario))  # già bloccato

    await cog.unlock.callback(cog, scena.interazione(proprietario))

    assert _overwrite_finale(canale, scena.guild.default_role).connect is True


async def test_unlock_dopo_un_riavvio_ripristina_il_valore_salvato_nel_database():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.overwrites_for.return_value = discord.PermissionOverwrite(connect=True)
    prima = VoiceTempCog(bot=None)
    await prima.lock.callback(prima, scena.interazione(proprietario))
    canale.overwrites_for.return_value = _overwrite_finale(canale, scena.guild.default_role)

    dopo_il_riavvio = VoiceTempCog(bot=None)
    await dopo_il_riavvio.unlock.callback(dopo_il_riavvio, scena.interazione(proprietario))

    assert _overwrite_finale(canale, scena.guild.default_role).connect is True
    assert await voice_temp_repo.togli_blocco(canale.id) is None


async def test_unlock_fallito_lascia_il_ricordo_per_il_tentativo_dopo():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.overwrites_for.return_value = discord.PermissionOverwrite(connect=True)
    cog = VoiceTempCog(bot=None)
    await cog.lock.callback(cog, scena.interazione(proprietario))
    canale.overwrites_for.return_value = _overwrite_finale(canale, scena.guild.default_role)
    canale.set_permissions.side_effect = _errore_http()

    await cog.unlock.callback(cog, scena.interazione(proprietario))
    canale.set_permissions.side_effect = None
    await cog.unlock.callback(cog, scena.interazione(proprietario))

    assert _overwrite_finale(canale, scena.guild.default_role).connect is True


# ====================================================================
# #127 — catalogo vocali temporanei: claim, permit, deny, bitrate, nascondi
# ====================================================================
async def test_claim_con_proprietario_assente_passa_la_proprieta():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.members.remove(proprietario)  # il proprietario e' uscito
    ospite = scena.entra(scena.membro(ID_OSPITE), canale)
    cog = VoiceTempCog(bot=None)

    await cog.claim.callback(cog, scena.interazione(ospite))

    assert await voice_temp_repo.get_owner(canale.id) == ID_OSPITE
    canale.set_permissions.assert_any_await(
        ospite, reason="Nuovo proprietario del vocale temporaneo", **modulo.OWNER_PERMISSIONS
    )


async def test_claim_con_proprietario_presente_e_rifiutato():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.entra(scena.membro(ID_OSPITE), canale)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(ospite)

    await cog.claim.callback(cog, interazione)

    assert await voice_temp_repo.get_owner(canale.id) == ID_PROPRIETARIO
    assert "ancora nel canale" in _testo(interazione.response.send_message.call_args)


async def test_permit_apre_il_canale_a_un_utente_senza_toccare_gli_altri_permessi():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.membro(ID_OSPITE)
    canale.overwrites_for.return_value = discord.PermissionOverwrite(speak=False)
    cog = VoiceTempCog(bot=None)

    await cog.permit.callback(cog, scena.interazione(proprietario), ospite)

    finale = _overwrite_finale(canale, ospite)
    assert finale.connect is True and finale.speak is False


async def test_deny_chiude_l_accesso_ed_espelle_chi_e_dentro():
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 5)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.entra(scena.membro(ID_OSPITE), canale)
    scena.guild.me.top_role = fake_role(role_id=900, name="bot", position=50)
    canale.overwrites_for.return_value = discord.PermissionOverwrite()
    cog = VoiceTempCog(bot=None)

    await cog.deny.callback(cog, scena.interazione(proprietario), ospite)

    assert _overwrite_finale(canale, ospite).connect is False
    ospite.move_to.assert_awaited_once()


async def test_deny_rispetta_la_gerarchia_e_non_colpisce_il_proprietario():
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 5)
    canale = await scena.crea_canale_di(proprietario)
    superiore = _con_ruolo(scena.membro(ID_OSPITE), 9)
    scena.guild.me.top_role = fake_role(role_id=900, name="bot", position=50)
    cog = VoiceTempCog(bot=None)

    interazione = scena.interazione(proprietario)
    await cog.deny.callback(cog, interazione, superiore)
    canale.set_permissions.assert_not_awaited()

    interazione = scena.interazione(proprietario)
    await cog.deny.callback(cog, interazione, proprietario)
    canale.set_permissions.assert_not_awaited()


async def test_bitrate_oltre_il_limite_del_server_e_rifiutato():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    scena.guild.bitrate_limit = 96000
    cog = VoiceTempCog(bot=None)

    interazione = scena.interazione(proprietario)
    await cog.bitrate.callback(cog, interazione, 128)
    canale.edit.assert_not_awaited()
    assert "96" in _testo(interazione.response.send_message.call_args)

    await cog.bitrate.callback(cog, scena.interazione(proprietario), 64)
    canale.edit.assert_awaited_once_with(bitrate=64000)


def _permessi_veri(canale, iniziali=None):
    """Il canale tiene davvero gli override: overwrites_for ne restituisce una copia, set_permissions li salva."""
    stato = dict(iniziali or {})

    def leggi(chi):
        return discord.PermissionOverwrite(**dict(stato.get(chi, discord.PermissionOverwrite())))

    async def scrivi(chi, *, overwrite=None, reason=None, **kw):
        if overwrite is None and kw:
            overwrite = discord.PermissionOverwrite(**kw)
        if overwrite is None or overwrite.is_empty():
            stato.pop(chi, None)
        else:
            stato[chi] = overwrite

    canale.overwrites_for.side_effect = leggi
    canale.set_permissions.side_effect = scrivi
    return stato


async def test_nascondi_dopo_il_comando_proprietario_ospiti_e_bot_vedono_ancora_il_canale():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.entra(scena.membro(ID_OSPITE), canale)
    stato = _permessi_veri(canale, {scena.guild.default_role: discord.PermissionOverwrite(connect=False)})
    cog = VoiceTempCog(bot=None)

    await cog.nascondi.callback(cog, scena.interazione(proprietario), True)

    assert stato[scena.guild.default_role].view_channel is False
    assert stato[scena.guild.default_role].connect is False  # il resto di @everyone non cambia
    for chi in (proprietario, ospite, scena.guild.me):
        assert stato[chi].view_channel is True and stato[chi].connect is True


async def test_nascondi_non_perde_i_permessi_di_gestione_del_proprietario():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    stato = _permessi_veri(canale, {proprietario: discord.PermissionOverwrite(**modulo.OWNER_PERMISSIONS)})
    cog = VoiceTempCog(bot=None)

    await cog.nascondi.callback(cog, scena.interazione(proprietario), True)

    assert stato[proprietario].manage_channels is True and stato[proprietario].view_channel is True


async def test_mostrare_di_nuovo_toglie_solo_il_nascondi_di_everyone():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    stato = _permessi_veri(canale, {scena.guild.default_role: discord.PermissionOverwrite(view_channel=False)})
    cog = VoiceTempCog(bot=None)

    await cog.nascondi.callback(cog, scena.interazione(proprietario), False)

    assert scena.guild.default_role not in stato


async def test_due_claim_insieme_ne_vince_uno_solo():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.members.remove(proprietario)
    a = scena.entra(scena.membro(ID_OSPITE), canale)
    b = scena.entra(scena.membro(ID_OSPITE + 1), canale)
    cog = VoiceTempCog(bot=None)
    ia, ib = scena.interazione(a), scena.interazione(b)

    await asyncio.gather(cog.claim.callback(cog, ia), cog.claim.callback(cog, ib))

    vincitore = await voice_temp_repo.get_owner(canale.id)
    assert vincitore in (ID_OSPITE, ID_OSPITE + 1)
    perdente = ib if vincitore == ID_OSPITE else ia
    dati = [c for c in canale.set_permissions.await_args_list if c.kwargs.get("manage_channels")]
    assert len(dati) == 1  # i permessi di gestione li ha preso uno solo
    assert perdente.response.send_message.call_args.kwargs["ephemeral"] is True


async def test_i_comandi_nuovi_sono_riservati_al_proprietario():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.entra(scena.membro(ID_OSPITE), canale)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(ospite)

    await cog.nascondi.callback(cog, interazione, True)

    canale.set_permissions.assert_not_awaited()
    assert "Solo il proprietario" in _testo(interazione.response.send_message.call_args)


# ====================================================================
# Giro del capo: defer per primo, risposta al proprietario su deny, trasferimento preciso
# ====================================================================
async def test_nascondi_risponde_con_defer_e_poi_followup():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    _permessi_veri(canale, {scena.guild.default_role: discord.PermissionOverwrite()})
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)

    await cog.nascondi.callback(cog, interazione, True)

    interazione.response.defer.assert_awaited_once()
    interazione.followup.send.assert_awaited_once()
    interazione.response.send_message.assert_not_awaited()


async def test_deny_sul_proprietario_dice_perche_non_si_puo():
    scena = Scena()
    proprietario = _con_ruolo(scena.membro(ID_PROPRIETARIO), 5)
    canale = await scena.crea_canale_di(proprietario)
    scena.guild.me.top_role = fake_role(role_id=900, name="bot", position=50)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)

    await cog.deny.callback(cog, interazione, proprietario)

    canale.set_permissions.assert_not_awaited()
    interazione.response.send_message.assert_awaited_once()
    assert _testo(interazione.response.send_message.call_args).strip() != ""


async def test_transfer_toglie_i_permessi_al_vecchio_e_li_da_solo_al_nuovo():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)

    await _trasferisci(scena, vecchio, nuovo)

    permessi = _permessi_dati(canale)
    assert set(permessi) == {ID_PROPRIETARIO, ID_OSPITE}
    assert permessi[ID_PROPRIETARIO] is None


# ====================================================================
# #127 — VOC-007 invita, VOC-008 stato, VOC-011/012 nome da modello,
# VOC-015 canali che nascono bloccati, VOC-018 registro delle azioni
# ====================================================================
from tests.support.discord_fakes import fake_text_channel  # noqa: E402

ID_REGISTRO = 777


async def _configura(scena, **opzioni):
    await voice_temp_repo.set_config(ID_SERVER, 1, scena.categoria.id)
    config = await voice_temp_repo.get_config(ID_SERVER)
    await voice_temp_repo.set_opzioni(
        ID_SERVER,
        opzioni.get("nome", config.nome_modello),
        opzioni.get("chiusi", config.nasce_bloccato),
        opzioni.get("registro"),
    )


async def test_nome_da_modello_e_numeri_in_sequenza():
    scena = Scena()
    await _configura(scena, nome="Stanza {numero} di {utente}")

    primo = await scena.crea_canale_di(scena.membro(ID_PROPRIETARIO))
    secondo = await scena.crea_canale_di(scena.membro(ID_OSPITE))

    nomi = [c.kwargs["name"] for c in scena.categoria.create_voice_channel.call_args_list]
    assert nomi == [f"Stanza 1 di utente{ID_PROPRIETARIO}", f"Stanza 2 di utente{ID_OSPITE}"]
    await voice_temp_repo.unregister_channel(primo.id)
    await scena.crea_canale_di(scena.membro(30))
    assert scena.categoria.create_voice_channel.call_args.kwargs["name"].startswith("Stanza 1 ")
    assert secondo.id != primo.id


async def test_canale_che_nasce_bloccato_si_apre_con_unlock():
    scena = Scena()
    await _configura(scena, chiusi=True)
    proprietario = scena.membro(ID_PROPRIETARIO)

    canale = await scena.crea_canale_di(proprietario)

    overwrites = scena.categoria.create_voice_channel.call_args.kwargs["overwrites"]
    assert overwrites[scena.guild.default_role].connect is False
    assert overwrites[proprietario].connect is True
    canale.overwrites_for.return_value = discord.PermissionOverwrite(connect=False)
    cog = VoiceTempCog(bot=None)
    await cog.unlock.callback(cog, scena.interazione(proprietario))
    assert _overwrite_finale(canale, scena.guild.default_role) is None


async def test_registro_scrive_creazione_e_blocco():
    scena = Scena()
    registro = fake_text_channel(ID_REGISTRO, "registro-vocali")
    scena.canali[ID_REGISTRO] = registro
    await _configura(scena, registro=ID_REGISTRO)
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    cog = VoiceTempCog(bot=None)

    await cog.lock.callback(cog, scena.interazione(proprietario))

    righe = [c.args[0] for c in registro.send.call_args_list]
    assert "creato" in righe[0] and "bloccato" in righe[1]
    assert registro.send.call_args.kwargs["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
    assert canale.id in scena.canali


async def test_opzioni_rifiuta_un_modello_con_segnaposto_sconosciuto():
    scena = Scena()
    await _configura(scena)
    staff = scena.membro(ID_PROPRIETARIO, manage_channels=True)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(staff)

    await cog.voicetemp_opzioni.callback(cog, interazione, nome="Stanza {nome}")

    assert interazione.response.send_message.call_args.kwargs["ephemeral"] is True
    assert (await voice_temp_repo.get_config(ID_SERVER)).nome_modello is None


async def test_opzioni_salva_e_predefiniti_azzera():
    scena = Scena()
    await _configura(scena)
    staff = scena.membro(ID_PROPRIETARIO, manage_channels=True)
    registro = fake_text_channel(ID_REGISTRO, "registro")
    cog = VoiceTempCog(bot=None)

    await cog.voicetemp_opzioni.callback(
        cog, scena.interazione(staff), nome="Stanza {numero}", chiusi=True, registro=registro
    )
    config = await voice_temp_repo.get_config(ID_SERVER)
    assert (config.nome_modello, config.nasce_bloccato, config.canale_registro_id) == (
        "Stanza {numero}", True, ID_REGISTRO,
    )

    await cog.voicetemp_opzioni.callback(cog, scena.interazione(staff), predefiniti=True)
    config = await voice_temp_repo.get_config(ID_SERVER)
    assert (config.nome_modello, config.nasce_bloccato, config.canale_registro_id) == (None, True, None)


async def test_invita_ammette_e_manda_l_invito_in_dm():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.membro(ID_OSPITE)
    invito = MagicMock(url="https://discord.gg/prova")
    canale.create_invite.return_value = invito
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)

    await cog.invita.callback(cog, interazione, ospite)

    assert canale.create_invite.call_args.kwargs["max_uses"] == 1
    assert "https://discord.gg/prova" in ospite.send.call_args.args[0]
    assert canale.set_permissions.call_args.args[0] is ospite


async def test_invita_senza_dm_mostra_il_link_a_chi_invita():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.membro(ID_OSPITE)
    canale.create_invite.return_value = MagicMock(url="https://discord.gg/prova")
    ospite.send.side_effect = _errore_http(403)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)

    await cog.invita.callback(cog, interazione, ospite)

    assert "https://discord.gg/prova" in _testo(interazione.followup.send.call_args)


async def test_stato_cambia_lo_stato_del_canale_e_vuoto_lo_toglie():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    cog = VoiceTempCog(bot=None)

    await cog.stato.callback(cog, scena.interazione(proprietario), "Ranked")
    assert canale.edit.call_args.kwargs == {"status": "Ranked"}
    await cog.stato.callback(cog, scena.interazione(proprietario))
    assert canale.edit.call_args.kwargs == {"status": None}

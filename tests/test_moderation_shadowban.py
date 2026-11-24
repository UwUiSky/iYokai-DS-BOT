"""
tests/test_moderation_shadowban.py
==================================
Shadowban (D127): ruoli salvati prima e ridati, canali dedicati creati o scelti, blocco sugli altri canali, canali
dedicati senza XP e senza statistiche, gerarchia, un solo shadowban per persona. Database vero, Discord finto.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation import shadowban as cog_sb
from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.shadowban import ModerationShadowbanCog
from core import moderation_shadowban as sb
from core.activity_stats_logic import conta_secondo_i_filtri
from core.database import db
from core.repositories.activity_stats_repo import ActivityStatsRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import (
    fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel, fake_voice_channel,
)

SERVER = 100
BERSAGLIO = 20
STAFF = 10


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(SERVER, MODULE_ACTIONS, True)
    monkeypatch.setattr(cog_sb, "post_to_mod_log", AsyncMock())
    yield
    database_module.db._modules_cache.clear()


def _canale(fabbrica, cid, nome, guild):
    c = fabbrica(cid, nome)
    c.guild = guild
    stato = {}

    def _ov(ruolo):
        return stato.setdefault(ruolo.id, discord.PermissionOverwrite())

    async def _set(target, *, overwrite=None, reason=None, **perms):
        o = overwrite if overwrite is not None else _ov(target)
        for k, v in perms.items():
            setattr(o, k, v)
        stato[target.id] = o

    c.overwrites_for = MagicMock(side_effect=_ov)
    c.set_permissions = AsyncMock(side_effect=_set)
    c.stato = stato
    return c


class Scena:
    def __init__(self, permessi=True):
        self.guild = g = fake_guild(SERVER, owner_id=1)
        g.me.id = 999
        g.me.top_role = fake_role(500, "Yokai", position=50)
        g.me.guild_permissions = discord.Permissions(manage_roles=permessi, manage_channels=permessi)
        g.default_role = fake_role(0, "@everyone", position=0)
        self.r_a = fake_role(11, "a", position=5)
        self.r_b = fake_role(12, "b", position=6)
        self.r_boost = fake_role(13, "boost", position=7, managed=True)
        self.r_alto = fake_role(14, "alto", position=80)
        self.ruoli = {r.id: r for r in (self.r_a, self.r_b, self.r_boost, self.r_alto)}
        g.roles = list(self.ruoli.values())
        g.get_role = MagicMock(side_effect=lambda i: self.ruoli.get(i))
        self.generale = _canale(fake_text_channel, 301, "generale", g)
        self.voce = _canale(fake_voice_channel, 302, "voce", g)
        self.canali = {301: self.generale, 302: self.voce}
        g.channels = list(self.canali.values())
        g.get_channel = MagicMock(side_effect=lambda i: self.canali.get(i))
        self.creati = []

        async def _ruolo(name, reason=None, **kw):
            r = fake_role(900, name, position=1)
            self.ruoli[900] = r
            g.roles.append(r)
            return r

        async def _testo(name, overwrites=None, reason=None, **kw):
            return self._nuovo(fake_text_channel, 910, name)

        async def _voce(name, overwrites=None, reason=None, **kw):
            return self._nuovo(fake_voice_channel, 911, name)

        g.create_role = AsyncMock(side_effect=_ruolo)
        g.create_text_channel = AsyncMock(side_effect=_testo)
        g.create_voice_channel = AsyncMock(side_effect=_voce)
        self.membri = {}
        g.get_member = MagicMock(side_effect=lambda i: self.membri.get(i))
        self.membro = self.nuovo_membro(BERSAGLIO, [self.r_a, self.r_b, self.r_boost])

    def _nuovo(self, fabbrica, cid, nome):
        c = _canale(fabbrica, cid, nome, self.guild)
        self.canali[cid] = c
        self.guild.channels.append(c)
        self.creati.append(c)
        return c

    def nuovo_membro(self, uid, ruoli):
        m = fake_member(uid, roles=[self.guild.default_role] + ruoli)
        m.guild = self.guild
        m.top_role = max(ruoli, key=lambda r: r.position) if ruoli else self.guild.default_role

        async def _edit(*, roles=None, reason=None, **kw):
            m.roles = [self.guild.default_role] + [r for r in roles if not r.is_default()]

        async def _add(*rr, reason=None):
            m.roles += [r for r in rr if r not in m.roles]

        m.edit = AsyncMock(side_effect=_edit)
        m.add_roles = AsyncMock(side_effect=_add)
        m.voice = None
        self.membri[uid] = m
        return m


def _ids(m):
    return {r.id for r in m.roles if r.id != 0}


# ------------------------------------------------------------------ ruoli salvati e ridati
async def test_i_ruoli_si_salvano_prima_poi_si_toglie_e_si_ridanno_solo_quelli_ridabili():
    s = Scena()
    visto = {}

    async def _edit(*, roles=None, reason=None, **kw):
        visto["stato_prima"] = await moderation_repo.get_shadowban(SERVER, BERSAGLIO)  # già scritto?
        s.membro.roles = [s.guild.default_role] + [r for r in roles if not r.is_default()]

    s.membro.edit = AsyncMock(side_effect=_edit)
    esito = await sb.metti(s.membro, "motivo", STAFF, None)
    assert esito.riuscita and esito.caso is not None and esito.ruoli_salvati == (11, 12)
    assert visto["stato_prima"]["ruoli"] == [11, 12]  # PRIMA di toccare il membro
    assert _ids(s.membro) == {13, 900}  # il ruolo gestito resta, gli altri sono tolti
    stato = await moderation_repo.get_shadowban(SERVER, BERSAGLIO)
    assert stato["case_number"] == esito.caso
    s.r_b.position = 90  # ora il ruolo b sta sopra il bot: non si può ridare
    s.membro.edit = AsyncMock(side_effect=_edit)
    assert await sb.togli(s.guild, s.membro, "fine", STAFF) is True
    assert _ids(s.membro) == {11, 13}
    assert await moderation_repo.get_shadowban(SERVER, BERSAGLIO) is None
    assert not (await moderation_repo.get_case(SERVER, esito.caso)).active


async def test_se_discord_rifiuta_lo_stato_sparisce_senza_caso():
    s = Scena()
    errore = discord.HTTPException(MagicMock(status=403), "no")
    s.membro.edit = AsyncMock(side_effect=errore)
    s.membro.add_roles = AsyncMock(side_effect=errore)
    esito = await sb.metti(s.membro, "motivo", STAFF, None)
    assert not esito.riuscita
    assert await moderation_repo.get_shadowban(SERVER, BERSAGLIO) is None
    assert await moderation_repo.get_case(SERVER, 1) is None


async def test_se_i_ruoli_non_si_tolgono_si_da_solo_il_ruolo_e_lo_dice():
    s = Scena()
    s.membro.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no"))
    esito = await sb.metti(s.membro, "motivo", STAFF, None)
    assert esito.riuscita and esito.ruoli_non_tolti and 900 in _ids(s.membro)


# ------------------------------------------------------------------ due insieme: uno solo
async def test_due_shadowban_insieme_sulla_stessa_persona_ne_passa_uno():
    s = Scena()
    a, b = await asyncio.gather(
        sb.metti(s.membro, "uno", STAFF, None), sb.metti(s.membro, "due", 11, None)
    )
    assert sorted([a.riuscita, b.riuscita]) == [False, True]
    assert (a.gia or b.gia)
    casi = await db.pool.fetch("SELECT 1 FROM moderation_cases WHERE guild_id = $1 AND action_type = 'shadowban'", SERVER)
    assert len(casi) == 1
    righe = await db.pool.fetch("SELECT 1 FROM moderation_shadowban WHERE guild_id = $1", SERVER)
    assert len(righe) == 1


async def test_chi_e_gia_in_shadowban_non_perde_i_ruoli_salvati():
    s = Scena()
    await sb.metti(s.membro, "uno", STAFF, None)
    again = await sb.metti(s.membro, "due", STAFF, None)
    assert again.gia and not again.riuscita
    assert (await moderation_repo.get_shadowban(SERVER, BERSAGLIO))["ruoli"] == [11, 12]


# ------------------------------------------------------------------ gerarchia e permessi
async def test_mai_su_owner_bot_o_chi_sta_sopra_il_bot_e_nulla_si_scrive():
    s = Scena()
    owner = s.nuovo_membro(1, [s.r_a])
    sopra = s.nuovo_membro(30, [s.r_alto])
    se_stesso = s.nuovo_membro(999, [s.r_a])
    for m in (owner, sopra, se_stesso):
        assert not (await sb.metti(m, "x", STAFF, None)).riuscita
        assert await moderation_repo.get_shadowban(SERVER, m.id) is None
    s.guild.create_role.assert_not_awaited()


async def test_senza_i_permessi_del_bot_non_si_tocca_niente():
    s = Scena(permessi=False)
    esito = await sb.metti(s.membro, "x", STAFF, None)
    assert not esito.riuscita and set(esito.permessi_mancanti) == {"manage_roles", "manage_channels"}
    s.guild.create_role.assert_not_awaited()
    s.membro.edit.assert_not_awaited()


async def test_il_comando_rifiuta_chi_sta_sopra_il_moderatore():
    s = Scena()
    mod = s.nuovo_membro(STAFF, [fake_role(15, "mod", position=20)])
    sopra_mod = s.nuovo_membro(31, [fake_role(16, "capo", position=30)])
    inter = fake_interaction(guild=s.guild, user=mod)
    cog = ModerationShadowbanCog(MagicMock())
    await cog.dai.callback(cog, inter, sopra_mod, "motivo")
    assert "Non riesco a verificare" not in str(inter.response.send_message.call_args)  # rifiutato per la gerarchia
    inter.response.send_message.assert_awaited_once()
    assert await moderation_repo.get_shadowban(SERVER, 31) is None
    s.guild.create_role.assert_not_awaited()


# ------------------------------------------------------------------ canali dedicati
async def test_il_bot_crea_ruolo_e_i_due_canali_e_blocca_gli_altri():
    s = Scena()
    esito = await sb.metti(s.membro, "x", STAFF, None)
    assert esito.riuscita
    cfg = await moderation_repo.get_shadowban_config(SERVER)
    assert cfg == {"ruolo_id": 900, "canale_testo_id": 910, "canale_vocale_id": 911}
    assert s.generale.stato[900].view_channel is False and s.voce.stato[900].view_channel is False
    assert 900 not in s.canali[910].stato and 900 not in s.canali[911].stato  # i dedicati non sono bloccati
    # una seconda volta non ricrea niente
    altro = s.nuovo_membro(21, [s.r_a])
    await sb.metti(altro, "y", STAFF, None)
    assert s.guild.create_role.await_count == 1 and s.guild.create_text_channel.await_count == 1


async def test_si_usano_i_canali_scelti_dallo_staff_e_diventano_privati():
    s = Scena()
    prep = await sb.prepara(s.guild, s.generale, s.voce)
    assert prep.canale_testo is s.generale and prep.canale_vocale is s.voce
    s.guild.create_text_channel.assert_not_awaited()
    assert s.generale.stato[0].view_channel is False  # @everyone non lo vede più
    assert s.generale.stato[900].view_channel is True and s.voce.stato[900].connect is True
    await sb.blocca_canali(s.guild, prep)
    assert 901 not in s.generale.stato and s.generale.stato[900].view_channel is True  # il blocco non tocca i dedicati


async def test_chi_e_in_vocale_viene_spostato_nel_vocale_dedicato():
    s = Scena()
    s.membro.voice = MagicMock(channel=s.voce)
    s.membro.move_to = AsyncMock()
    await sb.metti(s.membro, "x", STAFF, None)
    assert s.membro.move_to.await_args.args[0].id == 911


# ------------------------------------------------------------------ niente XP, niente statistiche
async def test_i_canali_dedicati_e_il_ruolo_non_danno_xp_nemmeno_in_modo_solo_questi(clean_db):
    s = Scena()
    await sb.metti(s.membro, "x", STAFF, None)
    repo = LevelingSettingsRepository(lambda: clean_db)
    config = await repo.get_config(SERVER, fresco=True)
    assert config.e_escluso(910, []) and config.e_escluso(911, [])
    assert config.e_escluso(301, [900])  # il ruolo shadowban non dà XP
    assert not config.e_escluso(301, [11])
    from dataclasses import replace
    solo = replace(config, impostazioni=replace(config.impostazioni, canali_modo="solo_questi"),
                   canali_esclusi=frozenset({910, 301}))
    assert solo.e_escluso(910, []) and not solo.e_escluso(301, [])


async def test_i_canali_dedicati_non_entrano_nelle_statistiche(clean_db):
    s = Scena()
    await sb.metti(s.membro, "x", STAFF, None)
    repo = ActivityStatsRepository(lambda: clean_db)
    imp = await repo.get_settings(SERVER)
    assert not conta_secondo_i_filtri(imp, 5, [11], {910})
    assert not conta_secondo_i_filtri(imp, 5, [11], {911})
    assert not conta_secondo_i_filtri(imp, 5, [900], {301})
    assert conta_secondo_i_filtri(imp, 5, [11], {301})


# ------------------------------------------------------------------ a tempo, dopo un riavvio
async def test_a_tempo_dopo_un_riavvio_la_scadenza_ridà_i_ruoli():
    from core.scheduler import scheduler

    s = Scena()
    inter = fake_interaction(guild=s.guild, user=s.nuovo_membro(STAFF, [fake_role(15, "mod", position=20)]))
    cog = ModerationShadowbanCog(MagicMock())
    await cog.dai.callback(cog, inter, s.membro, "spam", "2h")
    [attesa] = await scheduler.list_pending_for_guild(SERVER, sb.SCHEDULED_SHADOWBAN_FINE)
    assert 900 in _ids(s.membro)
    bot = MagicMock()
    bot.user.id = 999
    bot.get_guild.return_value = s.guild
    nuovo = ModerationShadowbanCog(bot)  # riavvio: nessuna memoria, solo il database
    await nuovo.handle_shadowban_fine(SERVER, BERSAGLIO, attesa["payload"])
    assert _ids(s.membro) == {11, 12, 13}
    assert await moderation_repo.get_shadowban(SERVER, BERSAGLIO) is None


async def test_chi_rientra_durante_lo_shadowban_riprende_il_ruolo():
    s = Scena()
    await sb.metti(s.membro, "x", STAFF, None)
    nuovo = s.nuovo_membro(BERSAGLIO, [])
    bot = MagicMock()
    bot.user.id = 999
    await ModerationShadowbanCog(bot).on_member_join(nuovo)
    assert 900 in _ids(nuovo)


def test_lazione_shadowban_si_puo_dare_a_un_ruolo_ma_apre_solo_i_suoi_comandi():
    from core import moderation_permessi_azioni as pa

    assert "shadowban" in pa.AZIONI
    assert {c for c, a in pa.COMANDI.items() if a == "shadowban"} == {
        "mod-sanzioni shadowban dai", "mod-sanzioni shadowban togli", "mod-sanzioni shadowban canali",
    }


# ------------------------------------------------------------------ D136: chi sceglie i canali, scadenza, autoruoli
def _staff_canali(s, *, puo=True):
    mod = s.nuovo_membro(STAFF, [fake_role(15, "mod", position=20)])
    for c in (s.generale, s.voce):
        c.permissions_for = MagicMock(return_value=discord.Permissions(manage_channels=puo))
    return mod


async def test_canali_senza_gestisci_canali_sul_canale_scelto_non_si_tocca_niente(monkeypatch):
    s = Scena()
    mod = _staff_canali(s, puo=False)
    prepara = AsyncMock()
    monkeypatch.setattr(sb, "prepara", prepara)
    inter = fake_interaction(guild=s.guild, user=mod)
    cog = ModerationShadowbanCog(MagicMock())
    await cog.canali.callback(cog, inter, s.generale, None)
    prepara.assert_not_awaited()
    inter.response.send_message.assert_awaited_once()
    assert s.generale.set_permissions.await_count == 0


async def test_canali_un_canale_gia_visibile_a_tutti_chiede_conferma_e_se_annulla_non_cambia(monkeypatch):
    s = Scena()
    mod = _staff_canali(s)
    prepara = AsyncMock()
    monkeypatch.setattr(sb, "prepara", prepara)
    chiesta = AsyncMock(return_value=None)  # annullato o scaduto
    monkeypatch.setattr(cog_sb, "chiedi_conferma_canali", chiesta)
    inter = fake_interaction(guild=s.guild, user=mod)
    cog = ModerationShadowbanCog(MagicMock())
    await cog.canali.callback(cog, inter, s.generale, None)  # generale: @everyone lo vede
    chiesta.assert_awaited_once()
    prepara.assert_not_awaited()


async def test_canali_confermato_il_permesso_si_rilegge_e_poi_si_procede(monkeypatch):
    s = Scena()
    mod = _staff_canali(s)
    inter = fake_interaction(guild=s.guild, user=mod)
    nuova = fake_interaction(guild=s.guild, user=mod)

    async def conferma(i, canali):
        for c in (s.generale, s.voce):  # tra la domanda e il clic il permesso sparisce
            c.permissions_for = MagicMock(return_value=discord.Permissions(manage_channels=False))
        return nuova

    monkeypatch.setattr(cog_sb, "chiedi_conferma_canali", conferma)
    prepara = AsyncMock()
    monkeypatch.setattr(sb, "prepara", prepara)
    cog = ModerationShadowbanCog(MagicMock())
    await cog.canali.callback(cog, inter, s.generale, None)
    prepara.assert_not_awaited()
    nuova.response.send_message.assert_awaited_once()


async def test_canali_gia_nascosto_a_everyone_non_chiede_conferma(monkeypatch):
    s = Scena()
    mod = _staff_canali(s)
    s.generale.stato[0] = discord.PermissionOverwrite(view_channel=False)
    chiesta = AsyncMock()
    monkeypatch.setattr(cog_sb, "chiedi_conferma_canali", chiesta)
    prep = sb.Preparazione(fake_role(900, "Shadowban"), s.generale, s.voce)
    monkeypatch.setattr(sb, "prepara", AsyncMock(return_value=prep))
    monkeypatch.setattr(sb, "blocca_canali", AsyncMock(return_value=(0, 0)))
    inter = fake_interaction(guild=s.guild, user=mod)
    cog = ModerationShadowbanCog(MagicMock())
    await cog.canali.callback(cog, inter, s.generale, None)
    chiesta.assert_not_awaited()
    sb.prepara.assert_awaited_once()


async def test_togli_se_discord_rifiuta_la_scadenza_non_si_perde(monkeypatch):
    s = Scena()
    mod = _staff_canali(s)
    cancella = AsyncMock()
    monkeypatch.setattr(cog_sb.scheduler, "cancel_for_user", cancella)
    monkeypatch.setattr(cog_sb.sb, "togli", AsyncMock(return_value=False))
    monkeypatch.setattr(cog_sb, "check_can_moderate", AsyncMock(return_value=True))
    monkeypatch.setattr(cog_sb, "risolvi_motivo", AsyncMock(return_value="x"))
    inter = fake_interaction(guild=s.guild, user=mod)
    cog = ModerationShadowbanCog(MagicMock())
    await cog.togli.callback(cog, inter, s.membro, "x")
    cancella.assert_not_awaited()
    monkeypatch.setattr(cog_sb.sb, "togli", AsyncMock(return_value=True))
    await cog.togli.callback(cog, inter, s.membro, "x")
    cancella.assert_awaited_once()


async def test_chi_e_in_shadowban_non_prende_gli_autoruoli_al_rientro(monkeypatch):
    import cogs.utility.autoroles as cog_autorole
    from cogs.utility.autoroles import AutorolesCog

    s = Scena()
    await sb.metti(s.membro, "x", STAFF, None)
    nuovo = s.nuovo_membro(BERSAGLIO, [])
    cog = AutorolesCog(MagicMock())
    cog.bot = MagicMock()
    await cog._assegna(nuovo, [11])
    nuovo.add_roles.assert_not_awaited()
    leggi = AsyncMock(return_value=[])
    monkeypatch.setattr(cog_autorole.autorole_repo, "list_rules", leggi)
    await cog._applica_regole(nuovo)  # in shadowban: nemmeno si leggono le regole
    leggi.assert_not_awaited()

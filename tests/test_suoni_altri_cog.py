"""FUN-075 (D127, D129): `/music suono-altri` e `/admin-musica suono-condividi`: menu, anteprima, invio, tetti. Nessuna rete."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest

import cogs.fun.suoni_altri as modulo
from core.music_sound_logic import PausaUtente

pytestmark = pytest.mark.asyncio


class _Repo:
    def __init__(self, condividono=(), usa=True):
        self.condividono = set(condividono)
        self.usa = usa

    async def leggi(self, g):
        return (g in self.condividono, self.usa)

    async def server_che_condividono(self, ids):
        return {i for i in ids if i in self.condividono}

    async def imposta(self, g, condividi=None, usa_esterni=None):
        if condividi is not None:
            (self.condividono.add if condividi else self.condividono.discard)(g)
        if usa_esterni is not None:
            self.usa = usa_esterni
        return g in self.condividono, self.usa


class _Suono:
    def __init__(self, i, nome, guild, dati=b"mp3", disponibile=True):
        self.id, self.name, self.guild, self.emoji, self.available = i, nome, guild, None, disponibile
        self.url = f"https://cdn.discordapp.com/soundboard-sounds/{i}"
        self._dati = dati

    async def read(self):
        if self._dati is None:
            raise discord.HTTPException(SimpleNamespace(status=404, reason="x"), "no")
        return self._dati


def _guild(i, nome, pubblico=False):
    return SimpleNamespace(id=i, name=nome, features=["DISCOVERABLE"] if pubblico else [])


class _SoundCog:
    def __init__(self):
        self.pausa = PausaUtente(pausa=0)
        self.suonati = []

    async def suona(self, musica, interaction, canale_id, oggetto):
        self.suonati.append((canale_id, oggetto))
        return "🔊 Suono **{nome}** partito."


class _Musica:
    async def controlli_base(self, interaction):
        return True


def _interazione(user_id=9, permessi=None, in_vocale=True):
    cattura = {"msg": [], "kw": []}

    async def _invia(testo=None, **kw):
        cattura["msg"].append(testo)
        cattura["kw"].append(kw)

    async def _niente(**kw):
        pass

    canale = SimpleNamespace(id=3, permissions_for=lambda u: permessi or discord.Permissions(speak=True, use_soundboard=True, use_external_sounds=True))
    utente = SimpleNamespace(id=user_id, voice=SimpleNamespace(channel=canale) if in_vocale else None)
    i = SimpleNamespace(
        guild=SimpleNamespace(id=1), user=utente, locale=None,
        response=SimpleNamespace(send_message=_invia, defer=_niente, edit_message=_invia),
        followup=SimpleNamespace(send=_invia),
    )
    return i, cattura


@pytest.fixture
def cog(monkeypatch):
    repo = _Repo({10})
    suono_cog = _SoundCog()
    sotto = _Suono(7, "Boom", _guild(10, "Server Aperto", True))
    privato = _Suono(8, "Segreto", _guild(10, "Nome Riservato", False))
    chiuso = _Suono(9, "Chiuso", _guild(20, "Altro", True))
    proprio = _Suono(5, "Mio", _guild(1, "Il mio"))
    rimosso = _Suono(6, "Rimosso", _guild(10, "Server Aperto", True), disponibile=False)
    bot = SimpleNamespace(
        soundboard_sounds=[sotto, privato, chiuso, proprio, rimosso],
        get_cog=lambda n: {"SoundboardCog": suono_cog, "MusicCog": _Musica()}.get(n),
    )

    async def _attivo(g, m):
        return True

    async def _imp(db, g):
        return SimpleNamespace(allowed_channel_id=None)

    monkeypatch.setattr(modulo, "suoni_condivisi_repo", repo)
    monkeypatch.setattr(modulo.db, "is_module_active_for_guild", _attivo, raising=False)
    monkeypatch.setattr(modulo, "load_music_settings", _imp)
    monkeypatch.setattr(modulo, "channel_not_allowed", lambda c, i: None)
    c = modulo.SuoniAltriCog(bot)
    c.t_repo, c.t_suono, c.t_sound = repo, suono_cog, (sotto, privato, chiuso, proprio, rimosso)
    return c


async def _apri(cog, cerca=None):
    i, cat = _interazione()
    await cog.suono_altri.callback(cog, i, cerca)
    vista = cat["kw"][-1].get("view")
    return i, cat, vista


async def test_il_menu_ha_solo_i_suoni_condivisi_degli_altri_server(cog):
    i, cat, vista = await _apri(cog)
    assert {o.value for o in vista.menu.options} == {"10:7", "10:8"}  # non il proprio, non chi non condivide, non gli indisponibili
    assert vista.anteprima.disabled and vista.invia.disabled
    _, cat2, vista2 = await _apri(cog, "boo")
    assert [o.value for o in vista2.menu.options] == ["10:7"]


async def test_l_anteprima_testuale_dice_il_server_solo_se_e_pubblico(cog):
    _, _, vista = await _apri(cog)
    for valore, atteso_nome in (("10:7", True), ("10:8", False)):
        vista.scelto = modulo.logica.trova(vista.suoni, valore)
        testo = " ".join(f.value for f in vista.embed().fields)
        assert ("Server Aperto" in testo) is atteso_nome
        assert "Nome Riservato" not in testo
    descrizioni = {o.value: o.description for o in vista.menu.options}
    assert "Server Aperto" in descrizioni["10:7"] and "Nome Riservato" not in descrizioni["10:8"]


async def test_di_base_nessun_server_condivide_e_nessuno_e_disponibile(cog):
    cog.t_repo.condividono.clear()
    i, cat, vista = await _apri(cog)
    assert vista is None and "disponibile" in cat["msg"][-1]


async def test_un_server_che_non_usa_gli_esterni_non_apre_il_menu(cog):
    cog.t_repo.usa = False
    i, cat, vista = await _apri(cog)
    assert vista is None and "non usare" in cat["msg"][-1]


async def test_invia_fa_suonare_nel_canale_di_chi_preme(cog):
    _, _, vista = await _apri(cog)
    vista.scelto = modulo.logica.trova(vista.suoni, "10:7")
    i, cat = _interazione()
    await cog.invia(i, vista)
    assert cog.t_suono.suonati == [(3, cog.t_sound[0])] and "Boom" in cat["msg"][-1]


async def test_invia_senza_permesso_o_fuori_dalla_vocale_non_suona(cog):
    _, _, vista = await _apri(cog)
    vista.scelto = modulo.logica.trova(vista.suoni, "10:7")
    i, cat = _interazione(permessi=discord.Permissions(speak=True, use_soundboard=True))
    await cog.invia(i, vista)
    assert cog.t_suono.suonati == [] and "permessi" in cat["msg"][-1]


async def test_se_il_server_smette_di_condividere_il_clic_non_suona(cog):
    _, _, vista = await _apri(cog)
    vista.scelto = modulo.logica.trova(vista.suoni, "10:7")
    cog.t_repo.condividono.clear()
    i, cat = _interazione()
    await cog.invia(i, vista)
    assert cog.t_suono.suonati == [] and "non è più" in cat["msg"][-1]


async def test_pausa_e_tetto_orario_per_persona(cog):
    _, _, vista = await _apri(cog)
    vista.scelto = modulo.logica.trova(vista.suoni, "10:7")
    i, cat = _interazione()
    await cog.invia(i, vista)
    await cog.invia(i, vista)  # subito dopo: pausa
    assert len(cog.t_suono.suonati) == 1 and "Aspetta" in cat["msg"][-1]
    # il tetto orario vale anche per l'anteprima (stessa persona)
    t = [0.0]
    cog.tetto = modulo.logica.TettoPersona(pausa=0, massimo=2, orologio=lambda: t[0])
    cog.tetto.segna(9)
    cog.tetto.segna(9)
    await cog.anteprima(i, vista)
    assert "troppi" in cat["msg"][-1] and len(cog.t_suono.suonati) == 1
    altro, cat3 = _interazione(user_id=10)
    vista.autore_id = 10
    await cog.anteprima(altro, vista)  # un'altra persona non è toccata
    assert cat3["kw"][-1].get("file") is not None


async def test_anteprima_manda_il_file_solo_a_chi_lo_chiede_e_ricade_sul_link(cog):
    _, _, vista = await _apri(cog)
    vista.scelto = modulo.logica.trova(vista.suoni, "10:7")
    i, cat = _interazione()
    await cog.anteprima(i, vista)
    f = cat["kw"][-1]["file"]
    assert f.filename == "suono-7.mp3" and cat["kw"][-1]["ephemeral"] is True
    cog.tetto = modulo.logica.TettoPersona(pausa=0)
    cog.t_sound[0]._dati = None
    await cog.anteprima(i, vista)
    assert "cdn.discordapp.com" in cat["msg"][-1] and cat["kw"][-1].get("file") is None


async def test_solo_chi_ha_aperto_il_menu_lo_usa(cog):
    _, _, vista = await _apri(cog)
    altro, cat = _interazione(user_id=77)
    assert await vista.interaction_check(altro) is False and "chi ha scritto" in cat["msg"][-1]


async def test_comando_admin_imposta_e_mostra_lo_stato(cog):
    i, cat = _interazione()
    await cog.suono_condividi.callback(cog, i, True, None)
    assert 1 in cog.t_repo.condividono and "sì" in cat["msg"][-1]
    await cog.suono_condividi.callback(cog, i, False, False)
    assert 1 not in cog.t_repo.condividono and cog.t_repo.usa is False


async def test_albero_ha_i_comandi_nei_gruppi_giusti():
    from discord.ext import commands

    from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await modulo.setup(bot)
    assert "suono-altri" in percorsi_del_gruppo("music") and "suono-condividi" in percorsi_del_gruppo("admin-musica")
    comando_nel_gruppo("music", "suono-altri").to_dict(bot.tree)
    comando_nel_gruppo("admin-musica", "suono-condividi").to_dict(bot.tree)

"""
tests/test_backup_clone_riuso.py
================================
M 12.3-12.8 (#68): clonazione su un server che ha già ruoli e canali
(modello), posizioni dei ruoli, bitrate, limite dei webhook, nome sicuro
per il mirror, canali offuscati.
"""

from __future__ import annotations

import discord
import pytest

from core.backup_clone_logic import (
    MAX_WEBHOOK_COPIATI,
    NOME_WEBHOOK_MIRROR,
    RiepilogoCopia,
    clone_categories_and_channels,
    clone_roles,
    clone_webhooks,
    create_mirror_webhooks,
)
from core.backup_mirror_logic import nome_sicuro_per_webhook
from tests.test_backup_clone_channels import (
    _FakeCategory,
    _FakeSourceGuild,
    _FakeTextChannel,
    _FakeVoiceChannel,
)
from tests.test_backup_clone_logic import _FakeRole, _FakeSourceGuild as _FakeSourceRoles


class _Hook:
    def __init__(self, name: str, url: str = "https://discord.com/api/webhooks/1/x", token="t") -> None:
        self.name = name
        self.url = url
        self.token = token


class _CanaleDest(discord.TextChannel):
    def __init__(self, ch_id: int, name: str, esistenti=None, category=None) -> None:
        self.id = ch_id
        self.name = name
        self._cat = category
        self._hooks = list(esistenti or [])
        self.creati: list[str] = []
        self.modifiche: list[dict] = []

    @property
    def category(self):
        return self._cat

    async def webhooks(self):
        return list(self._hooks)

    async def create_webhook(self, **kwargs):
        if len(self._hooks) >= 15:
            raise discord.HTTPException(_Resp(), "Maximum number of webhooks reached (15)")
        h = _Hook(kwargs["name"], url=f"https://discord.com/api/webhooks/{self.id}/{len(self._hooks)}")
        self._hooks.append(h)
        self.creati.append(kwargs["name"])
        return h

    async def edit(self, **kwargs):
        self.modifiche.append(kwargs)


class _Resp:
    status = 400
    reason = "Bad Request"


class _VoceDest(discord.VoiceChannel):
    def __init__(self, ch_id: int, name: str, category=None) -> None:
        self.id = ch_id
        self.name = name
        self._cat = category

    @property
    def category(self):
        return self._cat

    async def edit(self, **kwargs):
        pass


class _CatDest(discord.CategoryChannel):
    def __init__(self, cat_id: int, name: str) -> None:
        self.id = cat_id
        self.name = name
        self.modifiche: list[dict] = []

    async def edit(self, **kwargs):
        self.modifiche.append(kwargs)


class _DestinazioneCanali:
    """Server di destinazione con canali già presenti (come da modello)."""

    bitrate_limit = 96000.0

    def __init__(self, categorie=(), canali=()) -> None:
        self.categories = list(categorie)
        self.channels = [*categorie, *canali]
        self.default_role = _FakeRole(0, "@everyone", 0, is_default=True)
        self.create_category_calls: list[dict] = []
        self.create_text_calls: list[dict] = []
        self.create_voice_calls: list[dict] = []
        self._id = 5000

    def _nuovo(self, classe, **kw):
        self._id += 1
        return classe(self._id, kw["name"])

    async def create_category(self, **kw):
        self.create_category_calls.append(kw)
        return self._nuovo(_CatDest, **kw)

    async def create_text_channel(self, **kw):
        self.create_text_calls.append(kw)
        return self._nuovo(_CanaleDest, **kw)

    async def create_voice_channel(self, **kw):
        self.create_voice_calls.append(kw)
        c = self._nuovo(_CanaleDest, **kw)
        return c

    def get_role(self, role_id):
        return None


class _DestinazioneRuoli:
    def __init__(self, ruoli=()) -> None:
        self.default_role = _FakeRole(0, "@everyone", 0, is_default=True)
        self.roles = [self.default_role, *ruoli]
        self.create_role_calls: list[dict] = []
        self.posizioni: dict | None = None
        self._id = 7000

    async def create_role(self, **kw):
        self.create_role_calls.append(kw)
        self._id += 1
        r = _FakeRole(self._id, kw["name"], len(self.roles), permissions=kw.get("permissions"))
        self.roles.append(r)
        return r

    async def edit_role_positions(self, positions, **kw):
        self.posizioni = dict(positions)

    def get_role(self, role_id):
        return next((r for r in self.roles if r.id == role_id), None)


# --- 12.3 e 12.4 -----------------------------------------------------------

async def test_i_ruoli_gia_presenti_nel_modello_si_riusano_per_nome():
    mod = _FakeRole(10, "Moderatore", 2)
    vip = _FakeRole(11, "VIP", 1)
    sorgente = _FakeSourceRoles([mod, vip])
    gia = _FakeRole(8001, "Moderatore", 1)
    dest = _DestinazioneRuoli([gia])
    riepilogo = RiepilogoCopia()

    mappa = await clone_roles(sorgente, dest, riepilogo)

    assert [c["name"] for c in dest.create_role_calls] == ["VIP"]
    assert mappa[10] == 8001
    assert riepilogo.ruoli_riusati == 1


async def test_le_posizioni_dei_ruoli_si_impostano_dopo_la_creazione():
    alto, basso = _FakeRole(10, "Alto", 5), _FakeRole(11, "Basso", 2)
    dest = _DestinazioneRuoli()

    mappa = await clone_roles(_FakeSourceRoles([alto, basso]), dest)

    pos = {r.id: p for r, p in dest.posizioni.items()}
    assert pos[mappa[11]] < pos[mappa[10]]


async def test_i_canali_gia_presenti_nel_modello_non_si_duplicano():
    cat_src = _FakeCategory(1, "Generale", 0)
    chat = _FakeTextChannel(2, "chat", 0, category=cat_src)
    voce = _FakeVoiceChannel(3, "Sala", 1, category=cat_src)
    src = _FakeSourceGuild([cat_src], [cat_src, chat, voce])
    cat_dest = _CatDest(901, "Generale")
    chat_dest = _CanaleDest(902, "chat", category=cat_dest)
    voce_dest = _VoceDest(903, "Sala", category=cat_dest)
    dest = _DestinazioneCanali([cat_dest], [chat_dest, voce_dest])
    riepilogo = RiepilogoCopia()

    mappa = await clone_categories_and_channels(src, dest, {}, riepilogo)

    assert dest.create_category_calls == [] and dest.create_text_calls == []
    assert dest.create_voice_calls == []
    assert mappa == {1: 901, 2: 902, 3: 903}
    assert riepilogo.canali_riusati == 3


# --- 12.5 ------------------------------------------------------------------

async def test_il_bitrate_non_supera_il_limite_del_server_di_destinazione():
    voce = _FakeVoiceChannel(3, "Musica", 0, bitrate=384000)
    src = _FakeSourceGuild([], [voce])
    dest = _DestinazioneCanali()

    await clone_categories_and_channels(src, dest, {})

    assert dest.create_voice_calls[0]["bitrate"] == 96000


# --- 12.6 ------------------------------------------------------------------

class _SrcHooks:
    def __init__(self, hooks) -> None:
        self._hooks = hooks

    async def webhooks(self):
        return self._hooks


class _HookSrc:
    def __init__(self, nome: str, channel_id: int) -> None:
        self.name, self.channel_id = nome, channel_id


class _DestHooks:
    def __init__(self, canale) -> None:
        self._c = canale

    def get_channel(self, _id):
        return self._c


async def test_canale_con_15_webhook_si_clona_completo_e_resta_posto_per_il_mirror():
    sorgente = _SrcHooks([_HookSrc(f"hook{i}", 1) for i in range(15)])
    canale = _CanaleDest(200, "chat")
    dest = _DestHooks(canale)
    riepilogo = RiepilogoCopia()

    await clone_webhooks(sorgente, dest, {1: 200}, riepilogo)

    assert len(canale.creati) == MAX_WEBHOOK_COPIATI == 14
    assert riepilogo.webhook_saltati == 1
    mappa = await create_mirror_webhooks(dest, {1: 200})
    assert 1 in mappa and canale.creati[-1] == NOME_WEBHOOK_MIRROR


async def test_il_webhook_del_mirror_gia_esistente_si_riusa():
    esistente = _Hook(NOME_WEBHOOK_MIRROR, url="https://discord.com/api/webhooks/9/riuso")
    canale = _CanaleDest(200, "chat", esistenti=[esistente])

    mappa = await create_mirror_webhooks(_DestHooks(canale), {1: 200})

    assert mappa == {1: "https://discord.com/api/webhooks/9/riuso"}
    assert canale.creati == []


async def test_canale_pieno_di_webhook_non_blocca_il_mirror_degli_altri():
    pieno = _CanaleDest(200, "pieno", esistenti=[_Hook(f"x{i}") for i in range(15)])
    libero = _CanaleDest(201, "libero")

    class _D:
        def get_channel(self, i):
            return {200: pieno, 201: libero}[i]

    riepilogo = RiepilogoCopia()
    mappa = await create_mirror_webhooks(_D(), {1: 200, 2: 201}, riepilogo)

    assert list(mappa) == [2]
    assert riepilogo.mirror_non_creati == 1


# --- 12.7 ------------------------------------------------------------------

@pytest.mark.parametrize("nome", ["Discord Fan", "xxCLYDExx", "my discord clyde"])
def test_il_nome_del_webhook_non_contiene_le_parole_vietate(nome):
    sicuro = nome_sicuro_per_webhook(nome)
    assert "discord" not in sicuro.lower() and "clyde" not in sicuro.lower()
    assert 2 <= len(sicuro) <= 80


def test_un_nome_normale_resta_uguale_e_uno_vuoto_diventa_valido():
    assert nome_sicuro_per_webhook("Mario Rossi") == "Mario Rossi"
    assert len(nome_sicuro_per_webhook("")) >= 2
    assert len(nome_sicuro_per_webhook("a" * 200)) == 80


# --- 12.8 ------------------------------------------------------------------

async def test_i_canali_offuscati_si_saltano_e_si_contano():
    visibile = _FakeTextChannel(2, "chat", 0)
    offuscato = _FakeTextChannel(3, "___hidden___", 1)
    src = _FakeSourceGuild([], [visibile, offuscato])
    dest = _DestinazioneCanali()
    riepilogo = RiepilogoCopia()

    mappa = await clone_categories_and_channels(src, dest, {}, riepilogo)

    assert list(mappa) == [2]
    assert riepilogo.canali_offuscati == 1
    assert [c["name"] for c in dest.create_text_calls] == ["chat"]

"""
tests/test_phishing_logic.py
============================
Blocco dei link di phishing (NF-31, #102): lista locale, segni da sito
truffa, domini ufficiali mai segnalati, whitelist del server, download della
lista, e il percorso dal messaggio alla cancellazione e al timeout.
"""

import pytest

from cogs.automod.automod import AutomodCog
from core import phishing_list_fetcher as fetcher
from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    MessageSignals,
    VIOLATION_PHISHING,
    evaluate_message_violations,
)
from core.phishing_logic import (
    carica_domini,
    carica_lista_locale,
    domini_nel_testo,
    e_phishing,
    sembra_phishing,
)
from tests.test_automod_advanced_behavior import (  # noqa: F401
    GUILD_ID,
    _FakeGuild,
    _FakeMember,
    _FakeMessage,
    _FakeTextChannel,
    _salva_config,
    contesto,
)


def test_la_lista_locale_si_carica_e_ha_i_domini_attesi():
    lista = carica_lista_locale()
    assert "dlscord.gift" in lista and len(lista) >= 10


def test_commenti_e_righe_vuote_non_sono_domini():
    assert carica_domini("# c\n\nEvil.COM  # nota\nhttps://www.altro.net/x\nsenzapunto\n") == {"evil.com", "altro.net"}


@pytest.mark.parametrize("dominio", [
    "discord-nitro.xyz", "free-nitro.xyz", "steam-gift.com", "dlscord.gift", "steamcommunlty.com",
    "free-nitro-gift.co.uk", "login.discord-airdrop.com",
])
def test_segni_da_sito_truffa(dominio):
    assert sembra_phishing(dominio)


@pytest.mark.parametrize("dominio", [
    "discord.com", "cdn.discordapp.com", "discord.gift", "discord.js.org", "steamcommunity.com", "example.com",
    "nitrogen.com", "nitro.com", "mydiscord.com", "youtube.com",
])
def test_siti_veri_e_normali_non_sono_segnalati(dominio):
    assert not sembra_phishing(dominio)


def test_un_dominio_in_lista_copre_i_sottodomini():
    lista = frozenset({"evil-site.com"})
    assert e_phishing(["login.evil-site.com"], lista)
    assert not e_phishing(["evil-site.org"], lista)


def test_la_whitelist_del_server_sblocca_anche_l_euristica():
    assert e_phishing(["discord-nitro.xyz"], frozenset())
    assert not e_phishing(["discord-nitro.xyz"], frozenset(), consentiti=("discord-nitro.xyz",))


def test_si_trovano_anche_i_link_senza_http():
    assert "discord-nitro.xyz" in domini_nel_testo("ritira qui: discord-nitro.xyz/ritira")
    assert "esempio.com" in domini_nel_testo("https://www.Esempio.com/x")


def _segnali(testo):
    return MessageSignals(
        content=testo, mention_count=0, emoji_count=0, attachment_count=0, sticker_count=0,
        recent_message_count=0, recent_attachment_count=0, recent_sticker_count=0,
    )


def test_il_filtro_spento_non_segnala_niente():
    assert evaluate_message_violations(_segnali("https://discord-nitro.xyz"), AutomodAdvancedConfig()) == ()


def test_il_filtro_acceso_segnala_phishing_e_non_i_link_normali():
    config = AutomodAdvancedConfig(anti_phishing_enabled=True)
    assert VIOLATION_PHISHING in evaluate_message_violations(_segnali("gratis https://discord-nitro.xyz"), config)
    assert evaluate_message_violations(_segnali("guarda https://discord.com/channels/1"), config) == ()


def test_la_whitelist_anti_link_vale_anche_per_il_phishing():
    config = AutomodAdvancedConfig(
        anti_phishing_enabled=True, anti_link=AntiLinkConfig(mode="off", whitelist=("discord-nitro.xyz",))
    )
    assert evaluate_message_violations(_segnali("https://discord-nitro.xyz"), config) == ()


def test_la_lista_scaricata_si_interpreta_come_testo_o_json():
    assert fetcher.interpreta_lista("a-truffa.com\n# c\nb-truffa.net") == {"a-truffa.com", "b-truffa.net"}
    assert fetcher.interpreta_lista('["a-truffa.com", 5, "b-truffa.net"]') == {"a-truffa.com", "b-truffa.net"}
    assert fetcher.interpreta_lista("[non json") == frozenset()


def test_senza_indirizzo_o_senza_https_non_si_scarica(monkeypatch):
    lista = fetcher.ListaPhishing()
    monkeypatch.delenv(fetcher.VARIABILE_URL, raising=False)
    assert lista.url() is None
    monkeypatch.setenv(fetcher.VARIABILE_URL, "http://x.example/l.txt")
    assert lista.url() is None


@pytest.mark.asyncio
async def test_il_download_parte_una_volta_per_intervallo_e_si_unisce_alla_locale(monkeypatch):
    chiamate = []

    async def finta(self, url):
        chiamate.append(url)
        self._scaricata = frozenset({"nuovo-truffa.com"})
        return True

    monkeypatch.setattr(fetcher.ListaPhishing, "scarica", finta)
    monkeypatch.setenv(fetcher.VARIABILE_URL, "https://liste.example/phishing.txt")
    lista = fetcher.ListaPhishing()

    lista.aggiorna_se_serve()
    lista.aggiorna_se_serve()  # subito dopo: niente secondo download
    await lista._compito

    assert chiamate == ["https://liste.example/phishing.txt"]
    assert "nuovo-truffa.com" in lista.domini and "dlscord.gift" in lista.domini


@pytest.mark.asyncio
async def test_un_download_non_valido_lascia_la_lista_di_prima(monkeypatch):
    lista = fetcher.ListaPhishing()
    lista._scaricata = frozenset({"vecchio-truffa.com"})

    class _Risposta:
        status = 500

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Sessione:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def get(self, url): return _Risposta()

    monkeypatch.setattr(fetcher.aiohttp, "ClientSession", _Sessione)
    assert await lista.scarica("https://liste.example/x") is False
    assert "vecchio-truffa.com" in lista.domini


@pytest.mark.asyncio
async def test_il_messaggio_con_phishing_viene_cancellato_e_l_autore_va_in_timeout(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_phishing_enabled=True))
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    messaggio = _FakeMessage(guild, autore, _FakeTextChannel(1), content="Nitro gratis: https://dlscord.gift/xyz")

    await AutomodCog(bot=None).on_message(messaggio)

    assert messaggio.deleted is True
    assert len(autore.timeout_calls) == 1


@pytest.mark.asyncio
async def test_il_link_normale_passa_e_il_filtro_spento_non_agisce(contesto):
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_phishing_enabled=True))
    normale = _FakeMessage(guild, autore, canale, content="https://discord.com/channels/1/2")
    await AutomodCog(bot=None).on_message(normale)
    assert normale.deleted is False

    await _salva_config(contesto, config=AutomodAdvancedConfig())
    spento = _FakeMessage(guild, autore, canale, content="https://dlscord.gift/xyz")
    await AutomodCog(bot=None).on_message(spento)
    assert spento.deleted is False


def test_dominio_vero_usato_come_prefisso_e_phishing():
    from core.phishing_logic import sembra_phishing
    assert sembra_phishing("steampowered.com.evil.io")
    assert sembra_phishing("discord.com.login-check.xyz")
    assert not sembra_phishing("support.discord.com")


def test_discard_non_e_una_marca_storta():
    from core.phishing_logic import sembra_phishing
    assert not sembra_phishing("discard.com")
    assert sembra_phishing("dlscord.com")


async def test_il_download_legge_tutto_il_corpo_non_solo_il_primo_pezzo(monkeypatch):
    from core import phishing_list_fetcher as f

    righe = [f"truffa{i}.xyz\n".encode() for i in range(20000)]  # > 64 KB, arriva a pezzi

    class _Flusso:
        async def iter_chunked(self, n):
            for i in range(0, len(righe), 1000):
                yield b"".join(righe[i:i + 1000])

        async def read(self, n):  # il vecchio codice: solo il primo pezzo
            return b"".join(righe[:1000])

    class _Risposta:
        status = 200
        content = _Flusso()

        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _Sessione:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def get(self, url): return _Risposta()

    monkeypatch.setattr(f.aiohttp, "ClientSession", _Sessione)
    lista = f.ListaPhishing()
    assert await lista.scarica("https://esempio.test/l.txt") is True
    assert len(lista._scaricata) == 20000

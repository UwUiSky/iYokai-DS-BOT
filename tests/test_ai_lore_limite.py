"""
tests/test_ai_lore_limite.py
============================
Lunghezza della lore (AI-010, D127, SPEC §25.80): 1.000 caratteri di base e 2.000 da Premium in su. Un solo punto di
controllo (`imposta_lore`) per comando e pannello; l'AI riceve la lore tagliata al tetto di oggi (finito il Premium, torna
a 1.000). Database vero per il salvataggio, premium finto.
"""

from types import SimpleNamespace

import pytest

from core import ai_impostazioni as imp
from core.ai_testi_logic import MAX_LORE_BASE, MAX_LORE_PREMIUM, TEMI
from core.ai_testi_logic import testo_lore as componi_lore
from core.config_schema import ImpostazioneNonValida
from core.repositories.ai_repo import ai_repo
from tests.test_web_panel_ai import ai  # noqa: F401
from tests.test_web_panel_server import GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

G = 8601


def _premium(monkeypatch, attivo: bool):
    async def accesso(guild_id, modulo, bot=None):
        return attivo

    monkeypatch.setattr("core.premium.guild_has_premium_access", accesso)


def test_i_due_tetti_e_il_taglio_del_testo():
    assert (MAX_LORE_BASE, MAX_LORE_PREMIUM) == (1000, 2000)
    assert componi_lore(None, "a" * 1500) == "a" * 1000
    assert componi_lore(None, "a" * 1500, 2000) == "a" * 1500
    assert componi_lore("pirati", "x" * 1000).startswith(TEMI["pirati"]) and componi_lore("pirati", "x" * 1000).endswith("x" * 1000)  # il tema non toglie spazio


@pytest.mark.asyncio
async def test_il_livello_decide_il_tetto_e_un_errore_vale_base(monkeypatch):
    _premium(monkeypatch, False)
    assert await imp.lore_massima(G) == 1000
    _premium(monkeypatch, True)
    assert await imp.lore_massima(G) == 2000

    async def guasto(*a, **k):
        raise RuntimeError("database spento")

    monkeypatch.setattr("core.premium.guild_has_premium_access", guasto)
    assert await imp.lore_massima(G) == 1000


@pytest.mark.asyncio
async def test_senza_premium_1000_si_1001_no_con_messaggio_chiaro(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    _premium(monkeypatch, False)
    await imp.imposta_lore(G, "pirati", "a" * 1000)
    assert (await ai_repo.get_config(G)).lore_testo == "a" * 1000
    with pytest.raises(ImpostazioneNonValida) as errore:
        await imp.imposta_lore(G, "pirati", "a" * 1001)
    assert "1000" in str(errore.value) and "2000" in str(errore.value) and "Premium" in str(errore.value)
    assert (await ai_repo.get_config(G)).lore_testo == "a" * 1000  # niente è cambiato


@pytest.mark.asyncio
async def test_con_premium_2000_si_2001_no(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    _premium(monkeypatch, True)
    await imp.imposta_lore(G + 1, None, "b" * 2000)
    assert len((await ai_repo.get_config(G + 1)).lore_testo) == 2000
    with pytest.raises(ImpostazioneNonValida) as errore:
        await imp.imposta_lore(G + 1, None, "b" * 2001)
    assert "2000" in str(errore.value) and "Premium" not in str(errore.value)


@pytest.mark.asyncio
async def test_finito_il_premium_la_lore_lunga_arriva_all_ai_tagliata(monkeypatch):
    cfg = SimpleNamespace(lore_tema=None, lore_testo="c" * 1800)
    _premium(monkeypatch, True)
    assert len(await imp.lore_del_server(G, cfg)) == 1800
    _premium(monkeypatch, False)
    assert len(await imp.lore_del_server(G, cfg)) == 1000


@pytest.mark.asyncio
async def test_il_comando_ha_2000_come_massimo_di_discord_e_salva_o_rifiuta(clean_db, monkeypatch):
    """Il comando: il campo accetta 2000 (limite di Discord); il tetto vero lo dà il livello, con risposta chiara."""
    from cogs.ai import config as ai_config
    from cogs.ai.config import AiConfigCog

    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    _premium(monkeypatch, False)
    comando = AiConfigCog.lore
    import inspect

    assert "Range[str, 1, 2000]" in inspect.getsource(ai_config)  # il campo accetta fino a 2000: il resto lo decide il livello
    risposte = []

    class Inter:
        guild_id = G + 2
        response = SimpleNamespace(send_message=lambda testo, **k: _salva(risposte, testo))

    async def _salva(lista, testo):
        lista.append(testo)

    cog = AiConfigCog.__new__(AiConfigCog)
    await comando.callback(cog, Inter(), tema="nessuno", testo="d" * 1500)
    assert "al massimo 1000" in risposte[-1] and (await ai_repo.get_config(G + 2)).lore_testo is None
    _premium(monkeypatch, True)
    await comando.callback(cog, Inter(), tema="nessuno", testo="d" * 1500)
    assert risposte[-1].startswith("Lore salvata") and len((await ai_repo.get_config(G + 2)).lore_testo) == 1500
    assert ai_config  # modulo caricato


@pytest.mark.asyncio
async def test_pannello_stesso_controllo_e_il_modulo_dice_il_tetto(ai, monkeypatch):
    base = f"/server/{GUILD}/ai/altro"
    client = await _client(ai.app)
    try:
        await _entra(client)
        _premium(monkeypatch, False)
        pagina = await (await client.get(base)).text()
        assert 'maxlength="1000"' in pagina and "2000 con Premium" in pagina
        csrf = await _csrf(client, base)
        r = await client.post(base, data={"csrf": csrf, "azione": "lore", "tema": "nessuno", "testo": "e" * 1500}, allow_redirects=False)
        assert "esito=non_valido" in r.headers["Location"]
        _premium(monkeypatch, True)
        assert 'maxlength="2000"' in await (await client.get(base)).text()
        r = await client.post(base, data={"csrf": csrf, "azione": "lore", "tema": "nessuno", "testo": "e" * 1500}, allow_redirects=False)
        assert "esito=salvato" in r.headers["Location"]
        assert len((await ai_repo.get_config(GUILD)).lore_testo) == 1500
    finally:
        await client.close()

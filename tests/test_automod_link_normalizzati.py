"""
tests/test_automod_link_normalizzati.py
=======================================
Il filtro link riconosce un dominio anche quando è scritto in modo da
aggirare la lista: con la porta (`evil.com:443`), con un nome utente
davanti (`x@evil.com`), come sottodominio (`sub.evil.com`).
"""

import pytest

from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    MessageSignals,
    VIOLATION_ANTI_LINK,
    evaluate_message_violations,
    normalize_domain,
)


def _violazioni(testo: str, **anti_link) -> tuple[str, ...]:
    config = AutomodAdvancedConfig(anti_link=AntiLinkConfig(**anti_link))
    return evaluate_message_violations(MessageSignals(content=testo), config)


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.com:443/premio",
        "https://x@evil.com/premio",
        "https://utente:password@evil.com/premio",
        "https://sub.evil.com/premio",
        "https://a.b.evil.com:8443/premio",
        "https://EVIL.com./premio",
        "https://www.evil.com/premio",
    ],
)
def test_lista_nera_blocca_le_scritture_che_la_aggiravano(link):
    assert _violazioni(f"guarda {link}", mode="blacklist", blacklist=("evil.com",)) == (
        VIOLATION_ANTI_LINK,
    )


@pytest.mark.parametrize(
    "link",
    [
        "https://notevil.com/pagina",
        "https://evil.com.esempio.it/pagina",
        "https://esempio.it/evil.com",
    ],
)
def test_lista_nera_non_blocca_domini_solo_simili(link):
    assert _violazioni(f"guarda {link}", mode="blacklist", blacklist=("evil.com",)) == ()


def test_lista_bianca_ammette_porta_e_sottodominio_del_dominio_ammesso():
    ammessi = ("esempio.it",)

    assert _violazioni("https://esempio.it:443/a", mode="whitelist", whitelist=ammessi) == ()
    assert _violazioni("https://docs.esempio.it/a", mode="whitelist", whitelist=ammessi) == ()


def test_lista_bianca_non_si_aggira_con_il_dominio_ammesso_come_utente():
    # Il browser apre evil.com: "esempio.it" qui è solo il nome utente.
    assert _violazioni(
        "https://esempio.it@evil.com/a", mode="whitelist", whitelist=("esempio.it",)
    ) == (VIOLATION_ANTI_LINK,)


@pytest.mark.parametrize(
    "scritto, atteso",
    [
        ("Evil.COM", "evil.com"),
        ("https://www.evil.com/pagina?x=1", "evil.com"),
        ("evil.com:443", "evil.com"),
        ("  sub.evil.com.  ", "sub.evil.com"),
        ("", ""),
    ],
)
def test_normalize_domain_pulisce_cio_che_scrive_l_admin(scritto, atteso):
    assert normalize_domain(scritto) == atteso


def test_voce_di_lista_scritta_come_link_funziona_lo_stesso():
    assert _violazioni(
        "https://evil.com/a", mode="blacklist", blacklist=("https://www.Evil.com/",)
    ) == (VIOLATION_ANTI_LINK,)


def test_comando_domain_ha_un_limite_di_lunghezza():
    import discord
    from discord.ext import commands

    import cogs.automod.automod as modulo_automod

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    gruppo = modulo_automod.AutomodCog(bot).automod_group.to_dict(bot.tree)
    comando = next(c for c in gruppo["options"] if c["name"] == "anti-link-domain")
    opzione = next(o for o in comando["options"] if o["name"] == "domain")

    assert opzione["max_length"] == 253

"""
tests/test_registry_premium_ripristino.py
=========================================
#135: la fixture `reset_premium_registry` rimette a posto anche la spunta
`is_premium_active` dei moduli, non solo l'elenco.
"""

import pytest

from core.premium import PremiumModule
import tests.conftest as conftest_dei_test


def test_reset_premium_registry_ripristina_is_premium_active():
    from core.premium import registry

    nome = "modulo_prova_135"
    registry.register(
        PremiumModule(name=nome, display_name="Prova", description="x", category="utility")
    )
    try:
        # La fixture è un generatore: la pilotiamo a mano per vederne l'uscita.
        generatore = conftest_dei_test.reset_premium_registry._get_wrapped_function()()
        next(generatore)
        registry.set_module_premium(nome, True)
        assert registry.get(nome).is_premium_active is True

        # Fine del test: la fixture ripristina.
        with pytest.raises(StopIteration):
            next(generatore)

        assert registry.get(nome).is_premium_active is False
    finally:
        registry._modules.pop(nome, None)

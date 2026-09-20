"""
tests/test_premium_registry.py
=================================
Test dedicato di PremiumRegistry.register() — mancava, colmato dopo
aver trovato (con un test reale su un cog vero, non ipotizzato) che
/owner cog-reload falliva per QUALUNQUE cog con un modulo premium:
register() sollevava un errore alla seconda chiamata sullo stesso
nome, e bot.reload_extension() richiama sempre setup() (quindi
register()) una seconda volta. Istanza isolata di PremiumRegistry,
non il singleton globale — non serve toccare lo stato condiviso da
tutto il bot per testare la logica della classe.
"""

import pytest

from core.premium import PremiumModule, PremiumRegistry


def _modulo(name: str = "test_modulo", premium_capable: bool = True) -> PremiumModule:
    return PremiumModule(
        name=name,
        display_name="Modulo di Test",
        description="Un modulo per i test.",
        premium_capable=premium_capable,
    )


class TestRegister:
    def test_primo_register_funziona(self):
        registry = PremiumRegistry()
        registry.register(_modulo())
        assert registry.get("test_modulo") is not None

    def test_re_register_stessa_dichiarazione_non_solleva(self):
        # Il caso che serviva davvero: /owner cog-reload richiama
        # setup() (quindi register()) una seconda volta sullo stesso
        # cog, con una nuova istanza di PremiumModule ma identica.
        registry = PremiumRegistry()
        registry.register(_modulo())
        registry.register(_modulo())  # non deve sollevare

    def test_re_register_stessa_dichiarazione_preserva_is_premium_active(self):
        # La parte più delicata: un reload non deve resettare lo
        # stato premium a False solo perché il nuovo PremiumModule
        # in arrivo da setup() non passa esplicitamente
        # is_premium_active (parte sempre da False per costruzione).
        registry = PremiumRegistry()
        registry.register(_modulo())
        registry.set_module_premium("test_modulo", True)
        assert registry.get("test_modulo").is_premium_active is True

        registry.register(_modulo())  # reload

        assert registry.get("test_modulo").is_premium_active is True

    def test_re_register_display_name_diverso_solleva(self):
        registry = PremiumRegistry()
        registry.register(_modulo())

        modulo_diverso = PremiumModule(
            name="test_modulo",
            display_name="Nome Diverso",  # <-- qui la differenza
            description="Un modulo per i test.",
            premium_capable=True,
        )
        with pytest.raises(ValueError):
            registry.register(modulo_diverso)

    def test_re_register_description_diversa_solleva(self):
        registry = PremiumRegistry()
        registry.register(_modulo())

        modulo_diverso = PremiumModule(
            name="test_modulo",
            display_name="Modulo di Test",
            description="Descrizione diversa",  # <-- qui la differenza
            premium_capable=True,
        )
        with pytest.raises(ValueError):
            registry.register(modulo_diverso)

    def test_re_register_premium_capable_diverso_solleva(self):
        # Il caso più importante da bloccare: due moduli DIVERSI che
        # si contendono lo stesso nome, uno dei quali dichiara
        # premium_capable diverso dall'altro - esattamente il
        # conflitto che la protezione originale voleva prevenire.
        registry = PremiumRegistry()
        registry.register(_modulo(premium_capable=True))

        with pytest.raises(ValueError):
            registry.register(_modulo(premium_capable=False))

    def test_due_moduli_con_nomi_diversi_non_si_scontrano(self):
        registry = PremiumRegistry()
        registry.register(_modulo(name="modulo_a"))
        registry.register(_modulo(name="modulo_b"))

        assert registry.get("modulo_a") is not None
        assert registry.get("modulo_b") is not None

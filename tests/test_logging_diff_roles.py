"""
tests/test_logging_diff_roles.py
====================================
Test di diff_roles() e nickname_changed() (cogs/logging/basic_logs.py).
Logica pura, nessuna dipendenza da Discord.
"""

from cogs.logging.basic_logs import diff_roles, nickname_changed


class TestDiffRoles:
    def test_nessuna_differenza(self):
        added, removed = diff_roles({1, 2, 3}, {1, 2, 3})
        assert added == set()
        assert removed == set()

    def test_ruolo_aggiunto(self):
        added, removed = diff_roles({1, 2}, {1, 2, 3})
        assert added == {3}
        assert removed == set()

    def test_ruolo_rimosso(self):
        added, removed = diff_roles({1, 2, 3}, {1, 2})
        assert added == set()
        assert removed == {3}

    def test_ruolo_aggiunto_e_rimosso_insieme(self):
        added, removed = diff_roles({1, 2}, {2, 3})
        assert added == {3}
        assert removed == {1}

    def test_tutti_i_ruoli_rimossi(self):
        added, removed = diff_roles({1, 2, 3}, set())
        assert added == set()
        assert removed == {1, 2, 3}

    def test_da_nessun_ruolo_a_alcuni(self):
        added, removed = diff_roles(set(), {1, 2})
        assert added == {1, 2}
        assert removed == set()


class TestNicknameChanged:
    def test_nessun_cambiamento(self):
        assert nickname_changed("Mario", "Mario") is False

    def test_nickname_impostato_per_la_prima_volta(self):
        assert nickname_changed(None, "Mario") is True

    def test_nickname_rimosso(self):
        # Caso limite esplicitamente coperto: tornare a None (nessun
        # nickname, si vede il nome utente base) è comunque un
        # CAMBIAMENTO, non va confuso con "nessuna modifica".
        assert nickname_changed("Mario", None) is True

    def test_nickname_cambiato_da_uno_a_un_altro(self):
        assert nickname_changed("Mario", "Luigi") is True

    def test_entrambi_none_nessun_cambiamento(self):
        assert nickname_changed(None, None) is False

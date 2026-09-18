"""
tests/test_greetings_logic.py
================================
Test di core/greetings_logic.py — logica pura, nessuna dipendenza da
Discord.
"""

from core.greetings_logic import render_template


class TestRenderTemplate:
    def test_sostituzione_singola(self):
        risultato = render_template(
            "Ciao {user}!",
            user_mention="<@123>",
            username="Mario",
            server_name="Il Server",
            member_count=42,
        )
        assert risultato == "Ciao <@123>!"

    def test_tutti_i_segnaposto_insieme(self):
        risultato = render_template(
            "{user} ({username}) è entrato in {server}, ora siamo in {membercount}",
            user_mention="<@123>",
            username="Mario",
            server_name="Il Server",
            member_count=42,
        )
        assert risultato == "<@123> (Mario) è entrato in Il Server, ora siamo in 42"

    def test_user_e_username_non_si_confondono(self):
        # Il caso esplicitamente dichiarato nel modulo: "{user}" non
        # è una sottostringa di "{username}", quindi sostituire
        # prima {user} non deve "mangiarsi" parte di {username}.
        risultato = render_template(
            "{username} e {user}",
            user_mention="<@123>",
            username="Mario",
            server_name="X",
            member_count=1,
        )
        assert risultato == "Mario e <@123>"

    def test_segnaposto_ripetuto_piu_volte(self):
        risultato = render_template(
            "{user} {user} {user}",
            user_mention="<@123>",
            username="Mario",
            server_name="X",
            member_count=1,
        )
        assert risultato == "<@123> <@123> <@123>"

    def test_nessun_segnaposto_testo_invariato(self):
        risultato = render_template(
            "Messaggio senza segnaposto",
            user_mention="<@123>",
            username="Mario",
            server_name="X",
            member_count=1,
        )
        assert risultato == "Messaggio senza segnaposto"

    def test_membercount_diventa_stringa(self):
        risultato = render_template(
            "{membercount}",
            user_mention="<@123>",
            username="Mario",
            server_name="X",
            member_count=999,
        )
        assert risultato == "999"

    def test_template_vuoto(self):
        risultato = render_template(
            "", user_mention="<@123>", username="Mario", server_name="X", member_count=1
        )
        assert risultato == ""

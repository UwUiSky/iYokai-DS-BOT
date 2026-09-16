"""
tests/test_permissions.py
============================
Test della logica pura in core/permissions.py. Nessuna connessione a
Discord né al database: solo numeri e booleani, esattamente come la
funzione testata li riceve nel bot vero.

Eseguire con: pytest tests/test_permissions.py -v
"""

from core.permissions import ModerationActor, can_moderate


def actor(user_id, position, owner=False, is_bot=False):
    """Scorciatoia per costruire un ModerationActor nei test."""
    return ModerationActor(
        user_id=user_id,
        top_role_position=position,
        is_guild_owner=owner,
        is_bot_itself=is_bot,
    )


class TestCanModerate:
    def test_moderatore_con_ruolo_piu_alto_puo_agire(self):
        mod = actor(1, position=10)
        target = actor(2, position=5)
        ok, reason = can_moderate(mod, target, bot_top_role_position=20)
        assert ok is True
        assert reason == ""

    def test_moderatore_con_ruolo_piu_basso_viene_bloccato(self):
        mod = actor(1, position=3)
        target = actor(2, position=5)
        ok, reason = can_moderate(mod, target, bot_top_role_position=20)
        assert ok is False
        assert "ruolo pari o superiore" in reason

    def test_ruoli_di_pari_livello_si_bloccano_a_vicenda(self):
        # Caso esplicitamente richiesto nella progettazione: stesso
        # livello di ruolo NON deve poter agire, per evitare ambiguità
        mod = actor(1, position=5)
        target = actor(2, position=5)
        ok, _ = can_moderate(mod, target, bot_top_role_position=20)
        assert ok is False

    def test_nessuno_puo_moderare_se_stesso(self):
        mod = actor(1, position=10)
        target = actor(1, position=10)  # stesso user_id
        ok, reason = can_moderate(mod, target, bot_top_role_position=20)
        assert ok is False
        assert "te stesso" in reason

    def test_nessuno_puo_moderare_il_proprietario(self):
        mod = actor(1, position=999)  # ruolo altissimo, non basta
        target = actor(2, position=1, owner=True)
        ok, reason = can_moderate(mod, target, bot_top_role_position=1000)
        assert ok is False
        assert "proprietario" in reason

    def test_il_proprietario_puo_moderare_chiunque(self):
        # Anche con top_role_position a 0 (nessun ruolo assegnato),
        # il proprietario deve poter agire comunque.
        owner = actor(1, position=0, owner=True)
        target = actor(2, position=50)
        ok, reason = can_moderate(owner, target, bot_top_role_position=100)
        assert ok is True
        assert reason == ""

    def test_nessuno_puo_moderare_il_bot(self):
        mod = actor(1, position=999)
        target = actor(2, position=1, is_bot=True)
        ok, reason = can_moderate(mod, target, bot_top_role_position=1000)
        assert ok is False
        assert "bot" in reason

    def test_bot_con_ruolo_troppo_basso_viene_bloccato(self):
        # Il moderatore avrebbe l'autorità, ma il bot no: deve
        # bloccare comunque, con un messaggio che lo spiega, invece
        # di lasciar fallire la chiamata API Discord in modo criptico.
        mod = actor(1, position=50)
        target = actor(2, position=10)
        ok, reason = can_moderate(mod, target, bot_top_role_position=5)
        assert ok is False
        assert "ruolo è troppo basso" in reason

    def test_scenario_completo_realistico(self):
        # Owner del server (ruolo @everyone, position 0) modera un
        # membro con ruolo "Membro" (position 3). Il bot ha un ruolo
        # "iYokai" a position 15, più alto di entrambi.
        owner = actor(100, position=0, owner=True)
        membro = actor(200, position=3)
        ok, reason = can_moderate(owner, membro, bot_top_role_position=15)
        assert ok is True
        assert reason == ""

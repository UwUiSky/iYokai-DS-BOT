"""
core/retention_worker.py
========================
Pulizia giornaliera: server usciti da 90 giorni e tabelle con scadenza.
Funzioni coperte: SPEC §19 (NF-04)

STATO: scheletro. Il codice non è ancora scritto (issue #75).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #75, fase F5
# Funzione: NF-04, Privacy: cancellazione, esportazione, conservazione.
#
# Cosa deve fare la funzione: Ogni utente può chiedere una copia dei
#   suoi dati o la loro cancellazione. I dati di un server vengono
#   cancellati 90 giorni dopo l'uscita del bot (D6). Un solo lavoro
#   giornaliero pulisce le tabelle che crescono.
# Questo file: Pulizia giornaliera: server usciti da 90 giorni e tabelle
#   con scadenza.
# Comandi previsti: /utility privacy esporta, /utility privacy cancella;
#   /owner privacy richieste, /owner privacy approva. Fino a F7: sotto
#   il gruppo esistente /config.
# File collegati: cogs/utility/privacy.py, core/data_registry.py,
#   core/forget_user_service.py,
#   core/repositories/guild_presence_repo.py,
#   core/repositories/data_deletion_request_repo.py.
# Test da scrivere per primi: tests/test_data_registry.py,
#   tests/test_forget_user.py, tests/test_retention_worker.py.
# Migrazione: core/migrations/NNNN_guild_presence.sql,
#   core/migrations/NNNN_retain_for_security.sql,
#   core/migrations/NNNN_data_deletion_requests.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Esportazione come file sotto 10 MiB; DM con
#   HTTPException catturata.
# Da chi prendere spunto: Double Counter (/privacy, conservazione
#   dichiarata di 24 mesi).
# Dipende da: GDPR-1/2/3 di REVIEW.md. D6.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------

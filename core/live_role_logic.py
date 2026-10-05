"""
core/live_role_logic.py
=======================
Dà e toglie il ruolo "in diretta".
Funzioni coperte: SPEC §10.5, §10.6, §10.13 (NF-32)

STATO: scheletro. Il codice non è ancora scritto (issue #103).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #103, fase F13
# Funzione: NF-32, Alert: Kick, ruolo "in diretta", TikTok, Instagram e
#   X.
#
# Cosa deve fare la funzione: Alert per Kick. Un ruolo dato a chi è in
#   diretta. Per TikTok, Instagram e X, che non hanno API gratuite: feed
#   "ponte" RSS e webhook in ingresso (già esistenti), con una guida,
#   più una chiave API a pagamento facoltativa (D14).
# Questo file: Dà e toglie il ruolo "in diretta".
# Comandi previsti: /admin alert aggiungi-kick, /admin alert ruolo-live,
#   /admin alert guida-social.
# File collegati: core/kick_watcher.py, core/kick_api_logic.py,
#   core/repositories/kick_subscription_repo.py.
# File esistenti da toccare: cogs/utility/feed_alerts.py.
# Test da scrivere per primi: tests/test_kick_watcher.py,
#   tests/test_live_role_logic.py.
# Migrazione: core/migrations/NNNN_kick_subscriptions.sql. (prossimo
#   numero libero in core/migrations/).
# Limiti da rispettare: Quote di ogni servizio scritte in LIMITI.md;
#   tetto di alert per server.
# Da chi prendere spunto: Streamcord (ruolo in diretta, Kick), Pingcord.
# Dipende da: LC-7 e LIM-46 sistemati.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------

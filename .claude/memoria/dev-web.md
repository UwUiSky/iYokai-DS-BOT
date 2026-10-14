# Memoria di dev-web

## Aggiornata
14/10/2026 · ramo `feat/r6web` · giro r6 (#91 pannello web)

## In corso
- Previsione r6: 3 voci. (1) punto unico `core/config_schema.py`;
  (2) pannello aiohttp `core/web_panel_*` + migrazione 0150 sessioni;
  (3) documenti (SPEC §24, REGISTRO, VERIFICA_LIVE). Mi fermo dopo la 3.

## Fatto
- r6 (1): `core/config_schema.py` (imposta_modulo, imposta_lingua_server);
  setup.py e /admin lingua set lo usano.

## Cose imparate
- I test di setup sostituiscono `setup_module.db`: ora anche
  `config_schema_module.db`, e i moduli finti vanno registrati.

## Aperto
- F13 (app utente, programma per PC): non iniziato.

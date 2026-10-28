# discord-sdk.js

Pacchetto unico (esbuild) di `@discord/embedded-app-sdk`, licenza MIT,
Copyright (c) Discord Inc. Serve solo alla pagina `/attivita/radio`
(Activity «radio iYokai»). Per rifarlo: `npm i @discord/embedded-app-sdk esbuild`,
poi un file `entry.js` che assegna `window.DiscordSDK = DiscordSDK` e
`esbuild entry.js --bundle --minify --format=iife --outfile=discord-sdk.js`.

# Dashboard DataFlow360 (Vue 3)

```bat
npm install      (ou, a la racine du projet : dev.bat front-install)
npm run dev      (http://localhost:5173, l'API doit tourner sur le port 8000)
npm run build    (production, dossier dist/)
npm test         (tests : composants, routes, formats, avec les reponses reelles de l'API)
```

Structure : `src/views` (une page par section), `src/components` (cartes, tableaux, graphiques),
`src/stores` (Pinia), `src/lib` (API, formats, options ECharts), `src/router` (Vue Router).
Variables facultatives : `VITE_API_TARGET` (cible du proxy de dev), `VITE_API_URL` (API distante).

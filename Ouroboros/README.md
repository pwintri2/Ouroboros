# Ouroboros static site

This folder contains a static website prepared for simple hosting on `ouroboros-ai.nl`.

## Files

- `index.html` is the English homepage
- `contact.html` is the English contact page
- `nl/` contains the Dutch homepage and contact page
- `fr/` contains the French homepage and contact page
- `de/` contains the German homepage and contact page
- `es/` contains the Spanish homepage and contact page
- `assets/css/styles.css` contains the design system and layout
- `assets/js/main.js` adds scroll reveals and header polish
- `assets/images/` contains the extracted presentation visuals

## Quick local preview

```bash
cd /Users/philip/Ouroboros
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## Strato upload

Upload the contents of `/Users/philip/Ouroboros` to the web root for `ouroboros-ai.nl`.

# Ouroboros static site

This folder contains a static website prepared for simple hosting on `ouroboros-ai.nl`.

## Files

- `index.html`, `vision.html`, `use-cases.html`, `architecture.html`, `collaboration.html`, and `contact.html` are the English pages
- `nl/` contains the Dutch version of the same page set
- `fr/` contains the French version of the same page set
- `de/` contains the German version of the same page set
- `es/` contains the Spanish version of the same page set
- `info/index.html` redirects the former standalone information page into the new Dutch site structure
- `assets/css/styles.css` contains the design system and layout
- `assets/js/main.js` adds scroll reveals and header polish
- `assets/images/` contains the shared concept and Guardian presentation visuals
- `assets/videos/` contains the shared Guardian introduction video

## Quick local preview

```bash
cd /home/pwintri2/Ouroboros
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## Strato upload

Upload the contents of `/home/pwintri2/Ouroboros` to the web root for `ouroboros-ai.nl`.

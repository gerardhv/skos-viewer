# Begrippenkader Corporatiesector — Viewer

Publieke statische site voor het [Begrippenkader Corporatiesector](http://begrippenkader-corporatiesector.aedes.nl/) op GitHub Pages. TTL-bestanden in de repository zijn de bron van waarheid; bij elke push genereert CI geoptimaliseerde JSON-indexen en bouwt de Astro-site.

## Functies

- Thematische browse via SKOS-collecties
- Zoeken op voorkeursterm, synoniem, definitie en toelichting
- Alfabet-navigatie (A–Z + #)
- Begrip-detailpagina's met NL-SBB-labels
- Bronnen gegroepeerd (overgenomen / afgeleid / eigen)
- Relationele grafiek (Cytoscape.js)
- Versie-switcher (semantische versies via `?v=`)

## Lokale ontwikkeling

```bash
# Python-afhankelijkheden
pip install -r requirements.txt

# Valideer en bouw JSON
python scripts/validate.py
python scripts/build.py

# Node-afhankelijkheden en dev-server
npm install
npm run dev
```

Voor lokale preview zonder base path:

```bash
ASTRO_BASE=/ npm run dev
```

## Nieuwe versie publiceren

1. Maak map `data/versions/{versie}/` (bijv. `0.3/`)
2. Plaats het TTL-bestand als `begrippenkader_corporatiesector.ttl`
3. Voeg een entry toe aan `versions.json` en zet `latest` naar de nieuwe versie
4. Push naar `main` — GitHub Actions valideert, bouwt en deployt

### Voorbeeld `versions.json`

```json
{
  "latest": "0.2",
  "versions": [
    {
      "id": "0.2",
      "label": "Basisversie 0.2",
      "date": "2026-07-07",
      "file": "data/versions/0.2/begrippenkader_corporatiesector.ttl",
      "status": "concept"
    }
  ]
}
```

## Repository-structuur

```
data/versions/{versie}/     # TTL-bronbestanden (handmatig uploaden)
versions.json               # Versie-manifest
scripts/build.py            # TTL → JSON
scripts/validate.py         # SKOS-validatie
public/build/{versie}/      # Gegenereerde JSON (door build.py)
src/                        # Astro-site
```

## GitHub Pages

- Workflow: `.github/workflows/deploy.yml`
- Base path: `/skos-viewer/` (moet overeenkomen met de GitHub-reponaam)
- Configureer GitHub Pages op **GitHub Actions** als bron

## Relatie tot SKOS Manager

Dit project is een losstaande publieke viewer. Exporteer TTL handmatig vanuit SKOS Manager en upload naar `data/versions/`.

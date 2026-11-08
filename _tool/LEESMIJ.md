# Fred Raket - Site Tool

## Eenmalig instellen
1. Deze map `_tool` staat in de map van je website (naast `index.html`). Die map moet een git-kopie (clone) van je GitHub-repository zijn.
2. Open Terminal en typ eenmalig:
   `xcode-select --install`
   (installeert python3 en git; als ze er al zijn, krijg je een melding en is het in orde)
3. Maak het startbestand uitvoerbaar (eenmalig, sleep het bestand in Terminal na `chmod +x `):
   `chmod +x "Site Tool.command"`
4. De eerste keer: rechtsklik op `Site Tool.command` > Open > Open (macOS vraagt dan eenmalig toestemming).

## Gebruiken
- Dubbelklik `Site Tool.command`. Er opent een venster in je browser.
- **Nieuw album / tegel**: titel, tekstje, foto's erin slepen, klik een foto aan als tegelfoto, "Album aanmaken".
  - *Fotografie-pagina*: nieuwe tegel bij Fotografie + albumpagina.
  - *Homepagina*: nieuwe rubriek op de homepagina + pagina + menu-item.
- Klik op een foto om ze te **draaien**, de **uitsnede** in het album te kiezen of als **tegelfoto** bij te snijden.
- **Foto's toevoegen**: extra foto's achteraan in een bestaand album.
- **Album bewerken**: titel, teksten, volgorde, uitsnedes en tegelfoto van een bestaand album aanpassen, of het album verwijderen.
  Bij verwijderen blijven je originele foto's altijd staan; enkel mappen die de tool zelf maakte, worden opgeruimd.
- **Publiceren**: eerst "Bekijk site lokaal", daarna "Publiceer naar GitHub".

## Wat er met de foto's gebeurt
- verwerkt in de browser, dus staande foto's blijven rechtop en GPS-gegevens worden verwijderd
- groot: max. 2000 px, JPEG kwaliteit 85 (voor de lightbox)
- klein: max. 700 px (voor het raster, laadt veel sneller)
- tegelfoto: bijgesneden (zoals jij kiest) tot dezelfde verhouding als je bestaande tegels
- Instellingen staan bovenaan in `site_tool.py`.

## Hoe weet de tool waar iets moet komen?
Via onzichtbare markeringen in de HTML, bv. `<!-- TOOL:TEGELS-BEGIN -->`. Laat die staan als je zelf iets aanpast in de pagina's.

## Lukt pushen niet?
Gebruik je GitHub Desktop, open het dan en klik "Push origin". Je wijzigingen zijn al gecommit door de tool.

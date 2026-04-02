# Memory and Safety in C++

Geheugenbeheer en veiligheid zijn kritieke aspecten van het programmeren in C++.

## Stack vs Heap
* **Stack**: Automatische toewijzing van geheugen (snel, beperkte grootte).
* **Heap**: Handmatige toewijzing met `new` en `delete` (flexibel, gevaarlijker).

## RAII (Resource Acquisition Is Initialization)
Dit principe zorgt ervoor dat resources (zoals geheugen) automatisch worden vrijgegeven wanneer een object buiten scope gaat.

## Smart Pointers
Gebruik in plaats van ruwe pointers (`*`) altijd smart pointers om geheugenlekken te voorkomen.

* `std::unique_ptr`: Exclusief eigendom.
* `std::shared_ptr`: Gedeeld eigendom met reference counting.

```cpp
#include <memory>

std::unique_ptr<int> p = std::make_unique<int>(10);
```

## Ownership-denken
Bedenk altijd wie de eigenaar is van een object. Voorkom dangling pointers (pointers naar reeds vrijgegeven geheugen).

## Veiligheidsrichtlijnen
* Gebruik `std::vector` in plaats van ruwe arrays.
* Gebruik `std::string` in plaats van C-style `char*`.
* Vermijd handmatig geheugenbeheer (`new`/`delete`) waar mogelijk.
* Gebruik `const` voor variabelen die niet mogen veranderen.

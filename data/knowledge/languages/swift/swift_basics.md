# Swift Basics

Swift is een krachtige en intuïtieve programmeertaal ontwikkeld door Apple voor iOS, macOS, watchOS en tvOS.

## Variabelen en Constanten
Swift legt veel nadruk op veiligheid en onveranderlijkheid.

```swift
let pi = 3.14159 // Onveranderlijke constante
var score = 0    // Veranderlijke variabele
```

## Types en Optionals
Swift is sterk getypeerd. Optionals (`?`) worden gebruikt om de afwezigheid van een waarde aan te geven.

```swift
var name: String = "Wintrip"
var description: String? = nil

// Veilig uitpakken (Optional Binding)
if let unwrappedDescription = description {
    print(unwrappedDescription)
}
```

## Structs en Classes
Classes ondersteunen overerving, structs (waarde-types) niet. In Swift wordt de voorkeur vaak gegeven aan structs.

```swift
struct Task {
    let id: Int
    var name: String
}

class Agent {
    var name: String
    init(name: String) { self.name = name }
}
```

## Arrays en Dictionaries
Collecties zijn standaard "value-types" in Swift.

```swift
var fruits = ["Appel", "Banaan"]
fruits.append("Peer")

let colors = ["red": "#FF0000", "green": "#00FF00"]
```

## Error Handling
Fouten worden afgehandeld met `do-catch` blokken en de `throws` keyword.

```swift
func fetchData() throws { /* ... */ }

do {
    try fetchData()
} catch {
    print("Fout bij het ophalen van data: \(error)")
}
```

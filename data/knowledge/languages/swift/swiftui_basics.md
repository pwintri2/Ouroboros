# SwiftUI Basics

SwiftUI is een declaratieve UI-framework voor het bouwen van gebruikersinterfaces op alle Apple-platformen.

## De View Structuur
In SwiftUI definieer je wat de UI moet bevatten, niet hoe deze stap voor stap moet worden opgebouwd.

```swift
import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack {
            Text("Welkom bij Wintrip")
                .font(.largeTitle)
                .padding()
            
            Button("Actie") {
                print("Klik!")
            }
        }
    }
}
```

## State Management
SwiftUI reageert automatisch op veranderingen in data via property wrappers.

* `@State`: Voor lokale eenvoudige data binnen een view.
* `@Binding`: Voor het delen van data tussen een parent en child view.
* `@ObservedObject` / `@StateObject`: Voor complexere data-modellen.

```swift
struct CounterView: View {
    @State private var count = 0
    
    var body: some View {
        Button("Teller: \(count)") {
            count += 1
        }
    }
}
```

## View Modifiers
Je past styling toe door methodes aan views te koppelen. De volgorde van modifiers is cruciaal.

```swift
Text("Hallo")
    .padding()
    .background(Color.blue)
    .foregroundColor(.white)
    .cornerRadius(10)
```

## UI-denken voor AI
Bij het genereren of aanpassen van SwiftUI code:
* Houd views klein en herbruikbaar.
* Scheid logica van de UI (MVVM patroon).
* Maak gebruik van stacks (`HStack`, `VStack`, `ZStack`) voor layout.
* Test code-wijzigingen visueel in Xcode Previews indien mogelijk.

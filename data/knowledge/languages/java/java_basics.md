# Java Basics

Java is een robuuste, objectgeoriënteerde programmeertaal die is ontworpen om zo min mogelijk implementatie-afhankelijkheden te hebben.

## Classes en Methods
In Java moet alle code binnen een class staan. Het startpunt van een applicatie is de `main` method.

```java
public class Wintrip {
    public static void main(String[] args) {
        System.out.println("Hallo Wintrip!");
    }
}
```

## Types en Variabelen
Java is statisch getypeerd.

```java
int score = 10;
double price = 19.99;
String name = "Philip";
boolean isActive = true;
```

## Control Flow
Standaard structuren zoals `if-else`, `for` en `while` loops.

```java
if (score > 5) {
    System.out.println("Geslaagd!");
}

for (int i = 0; i < 5; i++) {
    System.out.println("Iteratie: " + i);
}
```

## Collections en Exceptions
Java biedt een uitgebreid framework voor verzamelingen en robuuste foutafhandeling.

```java
import java.util.ArrayList;

ArrayList<String> list = new ArrayList<>();
list.add("Item 1");

try {
    // Risicovolle code
} catch (Exception e) {
    System.err.println("Fout: " + e.getMessage());
}
```

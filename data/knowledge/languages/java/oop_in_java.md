# OOP in Java

Objectgeoriënteerd programmeren (OOP) is de kern van Java.

## Encapsulation
Bescherm data door variabelen `private` te maken en `getters` en `setters` te gebruiken.

```java
public class User {
    private String name;
    
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

## Inheritance
Subclasses erven gedrag en eigenschappen over van een parent class met `extends`.

```java
public class SmartAgent extends Agent {
    @Override
    public void act() {
        System.out.println("Slimme actie.");
    }
}
```

## Polymorphism en Interfaces
Objecten kunnen worden behandeld als hun bovenliggende type of interface.

```java
public interface Tool {
    void execute();
}

public class Browser implements Tool {
    public void execute() { /* ... */ }
}
```

## Abstract Classes
Een abstracte class kan niet worden geïnstantieerd, maar dient als blauwdruk.

```java
public abstract class BaseTask {
    abstract void run();
}
```

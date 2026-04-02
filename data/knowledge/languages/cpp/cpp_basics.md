# C++ Basics

C++ is een krachtige, algemeen bruikbare programmeertaal die efficiënte controle biedt over systeembronnen.

## Basis Syntax en Functies
In C++ is `main()` het startpunt van de uitvoering.

```cpp
#include <iostream>

int main() {
    std::cout << "Hallo C++" << std::endl;
    return 0;
}
```

## Classes en Objecten
C++ ondersteunt objectgeoriënteerd programmeren.

```cpp
class Agent {
public:
    std::string name;
    void act() { std::cout << "Actie!" << std::endl; }
};
```

## References en Pointers
Pointers slaan het geheugenadres van een variabele op. References zijn aliassen voor variabelen.

```cpp
int x = 10;
int* p = &x; // Pointer naar x
int& r = x;  // Reference naar x
```

## Standard Template Library (STL) Intro
De STL biedt herbruikbare algoritmen en datastructuren zoals `vector` en `string`.

```cpp
#include <vector>
#include <string>

std::vector<std::string> tools = {"Browser", "Sandbox"};
```

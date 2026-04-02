# PHP Basics

PHP (Hypertext Preprocessor) is een populaire open-source scripttaal die speciaal geschikt is voor webontwikkeling.

## Syntax en Variabelen
PHP-code wordt uitgevoerd op de server en begint met `<?php`.

```php
<?php
$name = "Wintrip"; // Variabelen beginnen met een $
$version = 8.2;
$is_active = true;
?>
```

## Arrays
PHP kent zowel numerieke als associatieve arrays.

```php
$fruits = ["Appel", "Banaan"];
$person = [
    "first_name" => "Philip",
    "role" => "Developer"
];
```

## Functies en Classes
PHP ondersteunt modern objectgeoriënteerd programmeren (OOP).

```php
function begroeting($name) {
    return "Hallo, " . $name;
}

class Agent {
    public $name;
    public function __construct($name) {
        $this->name = $name;
    }
}
```

## Forms en Server-side logica
PHP wordt veel gebruikt voor het verwerken van HTML-formulieren via `$_GET` en `$_POST`.

```php
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    $input = $_POST["user_input"];
    // Verwerk input
}
```

## Best Practices
* Gebruik altijd `require_once` of `include_once` voor externe bestanden.
* Pas PSR-standaarden toe voor consistente code-opmaak.
* Voorkom SQL-injectie door gebruik te maken van PDO en prepared statements.
* Schakel foutrapportage in tijdens ontwikkeling, maar uit in productie.

<?php
/**
 * Ouroboros AI Chat Handler - Multi-language & Content Aware
 */

header('Content-Type: application/json');

function loadEnv($path) {
    if (!file_exists($path)) return;
    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        if (strpos(trim($line), '#') === 0) continue;
        if (strpos($line, '=') === false) continue;
        list($name, $value) = explode('=', $line, 2);
        $_ENV[trim($name)] = trim($value);
    }
}

loadEnv(__DIR__ . '/../.env');
$apiKey = $_ENV['GEMINI_API_KEY'] ?? null;

if (!$apiKey) {
    echo json_encode(['error' => 'API Key not configured.']);
    exit;
}

$input = json_decode(file_get_contents('php://input'), true);
$userMessage = $input['message'] ?? '';
$lang = $input['lang'] ?? 'en';
$pageContext = $input['context'] ?? '';

if (empty($userMessage)) {
    echo json_encode(['error' => 'Empty message.']);
    exit;
}

// Knowledge Base about Ouroboros
$knowledgeBase = "
Ouroboros AI is a private digital guardian and tech assistant.
Main Goal: Make technology simple, safe, and private for seniors, families, and everyone.
Features: 
- Notices tech problems early (confusing warnings, stuck apps).
- Teaches calmly without difficult words.
- Local-first: Keeps data on the user's device (privacy focused).
- Provides independence and peace of mind.
- For Businesses: Offers 'Ouroboros for Business' to reduce support stress for employees and clients.
- Available in: English, Dutch (NL), French (FR), German (DE), Spanish (ES).
";

// Persona Instructions
$persona = "
You are Ouroboros, the digital guardian. 
Your tone is ALWAYS empathic, calm, and concise. 
NEVER use technical jargon. Use ordinary words.
Respond in the language requested: $lang.
Current Page Context: $pageContext
Knowledge Base: $knowledgeBase
";

$apiUrl = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=" . $apiKey;

$data = [
    "contents" => [
        [
            "role" => "user",
            "parts" => [
                ["text" => "System instruction: " . $persona],
                ["text" => $userMessage]
            ]
        ]
    ]
];

$ch = curl_init($apiUrl);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($httpCode !== 200) {
    echo json_encode(['error' => 'API Request failed']);
    exit;
}

$result = json_decode($response, true);
$reply = $result['candidates'][0]['content']['parts'][0]['text'] ?? "Ouroboros is resting. Please try again later.";

echo json_encode(['reply' => trim($reply)]);

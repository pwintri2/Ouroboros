import re

def scrub_data(text: str) -> str:
    """
    Verwijdert API keys, wachtwoorden en andere gevoelige patronen (PII).
    Dit is de verplichte stap voordat data naar Tier 1 of 2 (Cloud) gaat.
    """
    # Patroon voor API keys (bijv. sk-...)
    api_key_pattern = r'(sk-[a-zA-Z0-9]{32,})'
    # Patroon voor e-mailadressen (basis PII)
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    # Patroon voor potentiële wachtwoorden in key-value pairs
    password_pattern = r'(?i)(password|passwd|wachtwoord|secret)\s*[:=]\s*[^\s,;]+'
    
    scrubbed = re.sub(api_key_pattern, "[REDACTED_API_KEY]", text)
    scrubbed = re.sub(email_pattern, "[REDACTED_EMAIL]", scrubbed)
    scrubbed = re.sub(password_pattern, r'\1: [REDACTED_PWD]', scrubbed)
    
    return scrubbed

if __name__ == "__main__":
    # Testcase voor validatie
    test_text = "Login met admin en password: MijnGeheim123. API Key: sk-abcdefghijklmnopqrstuvwxyz123456. Contact: piet@puk.nl"
    print(f"Origineel: {test_text}")
    print(f"Gereinigd: {scrub_data(test_text)}")

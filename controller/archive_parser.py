import json
import email
from email import policy

def parse_chatgpt_json(json_string: str) -> list:
    """
    Ontleedt een ChatGPT 'conversations.json' export.
    Dit formaat is complex (geneste mappings). Deze functie extraheert de titels
    en de chronologische berichtenlijst per conversatie.
    """
    parsed_chats = []
    try:
        data = json.loads(json_string)
        # ChatGPT exports zijn meestal een lijst met conversaties
        if not isinstance(data, list):
            return [{"error": "Ongeldig formaat: Verwacht een lijst met conversaties."}]

        for conv in data:
            title = conv.get('title', 'Naamloze Chat')
            messages = []
            
            # De berichten staan in de 'mapping' dictionary
            mapping = conv.get('mapping', {})
            
            # Sorteer nodes op creatietijd indien beschikbaar (ChatGPT structuur is een boom)
            # Voor een simpele parser pakken we alle tekstuele onderdelen van de auteur 'user' of 'assistant'
            for node_id in mapping:
                node = mapping[node_id]
                msg_obj = node.get('message')
                
                if msg_obj:
                    author = msg_obj.get('author', {})
                    role = author.get('role', 'unknown')
                    content_obj = msg_obj.get('content', {})
                    
                    if content_obj and content_obj.get('content_type') == 'text':
                        parts = content_obj.get('parts', [])
                        text_content = " ".join([str(p) for p in parts if isinstance(p, str)])
                        
                        if text_content.strip():
                            # Formatteer als 'User: ...' of 'Assistant: ...'
                            messages.append(f"{role.capitalize()}: {text_content.strip()}")
            
            parsed_chats.append({
                "title": title,
                "messages": messages,
                "msg_count": len(messages)
            })
            
    except json.JSONDecodeError:
        return [{"error": "FOUT: De string is geen geldige JSON."}]
    except Exception as e:
        return [{"error": f"Onverwachte fout bij ChatGPT parsing: {str(e)}"}]
    
    return parsed_chats

def parse_eml_file(eml_string: str) -> dict:
    """
    Ontleedt een ruw .eml of .mbox e-mailbestand.
    Extraheert metadata en de platte tekst (plain text) van de body.
    """
    try:
        # Gebruik de moderne email policy voor betere afhandeling van encodings
        msg = email.message_from_string(eml_string, policy=policy.default)
        
        subject = msg.get('subject', '(Geen onderwerp)')
        sender = msg.get('from', '(Onbekende afzender)')
        date = msg.get('date', '(Geen datum)')
        
        # Haal de body op (zoekt naar text/plain in multipart berichten)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    body = part.get_content()
                    break
        else:
            body = msg.get_content()

        return {
            "status": "Success",
            "subject": subject,
            "from": sender,
            "date": date,
            "body": body.strip() if body else "(Leeg bericht)"
        }
    except Exception as e:
        return {
            "status": "Error",
            "error": f"Fout bij parsen van e-mail: {str(e)}"
        }

if __name__ == "__main__":
    # --- Quick Tests ---
    print("--- Test EML Parser ---")
    mock_eml = "Subject: Wintrip Update\nFrom: philip@wintrip.ai\n\nHallo Team, de parser is klaar!"
    print(parse_eml_file(mock_eml))
    
    print("\n--- Test ChatGPT Parser (Mock) ---")
    mock_chatgpt = json.dumps([{
        "title": "Python Vraag",
        "mapping": {
            "1": {"message": {"author": {"role": "user"}, "content": {"content_type": "text", "parts": ["Hoe werkt JSON?"]}}},
            "2": {"message": {"author": {"role": "assistant"}, "content": {"content_type": "text", "parts": ["JSON is een data-indeling."]}}}
        }
    }])
    print(parse_chatgpt_json(mock_chatgpt))

import os
from controller.archive_parser import parse_chatgpt_json

def search_local_chats(query: str, filename: str = "conversations.json") -> str:
    """Zoekt door lokale ChatGPT exports in de /data/ map."""
    # VEILIGHEID: Absolute pad-controle tegen path traversal
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    target_path = os.path.abspath(os.path.join(base_dir, filename))

    # Zorg dat we binnen de data map blijven
    if not target_path.startswith(base_dir):
        return "[FOUT] Onveilige bestandstoegang geweigerd."

    if not os.path.exists(target_path):
        return f"[FOUT] Bestand '{filename}' niet gevonden in /data/."

    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        chats = parse_chatgpt_json(content)
        
        # Foutafhandeling vanuit de parser zelf
        if chats and isinstance(chats[0], dict) and "error" in chats[0]:
            return chats[0]["error"]

        query_lower = query.lower()
        results = []

        for chat in chats:
            title = chat.get('title', 'Naamloze Chat')
            messages = chat.get('messages', [])
            
            # Check of query in titel of berichten voorkomt
            match_in_title = query_lower in title.lower()
            match_in_msgs = any(query_lower in m.lower() for m in messages)
            
            if match_in_title or match_in_msgs:
                # Format de chat voor Ollama
                preview_msgs = messages[:5] # Maximaal 5 berichten voor context
                formatted_chat = f"Gevonden Chat: [{title}]\n"
                formatted_chat += "Berichten:\n- " + "\n- ".join(preview_msgs)
                if len(messages) > 5:
                    formatted_chat += f"\n(... en nog {len(messages)-5} andere berichten)"
                
                results.append(formatted_chat)
                
                # Stop bij de beste 3 resultaten om de context-window niet te vervuilen
                if len(results) >= 3:
                    break

        if not results:
            return f"Geen lokale chats gevonden die voldoen aan de zoekopdracht: '{query}'."

        return "\n\n---\n\n".join(results)

    except Exception as e:
        return f"[FOUT] Er ging iets mis bij het doorzoeken van het archief: {str(e)}"

if __name__ == "__main__":
    # Test (indien conversations.json bestaat)
    # Zorg dat je dit uitvoert vanuit de root van het project
    print(search_local_chats("test"))

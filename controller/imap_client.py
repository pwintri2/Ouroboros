import imaplib
import email
import os
from email.header import decode_header
from dotenv import load_dotenv

# Zorg dat we omgevingsvariabelen kunnen laden uit de .env file
load_dotenv()

class ImapClient:
    """
    Een IMAP Client voor directe mail-toegang (Wintrip AI).
    """
    def __init__(self):
        # Gebruik de variabelen zoals gevraagd (IMAP_SERVER, IMAP_EMAIL, IMAP_PASSWORD)
        self.server = os.getenv("IMAP_SERVER")
        self.email_address = os.getenv("IMAP_EMAIL")
        self.password = os.getenv("IMAP_PASSWORD")
        self.mail = None

    def connect(self):
        """Maakt verbinding met de IMAP server via SSL."""
        if not all([self.server, self.email_address, self.password]):
            print("Fout: Ontbrekende IMAP credentials in .env")
            return False
            
        try:
            self.mail = imaplib.IMAP4_SSL(self.server)
            self.mail.login(self.email_address, self.password)
            return True
        except Exception as e:
            print(f"Fout bij verbinden met IMAP server: {e}")
            return False

    def _decode_str(self, s):
        """Helper methode om headers zoals Subject en From te decoderen."""
        if not s:
            return ""
        try:
            decoded_parts = decode_header(s)
            header_text = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    try:
                        header_text += part.decode(encoding or "utf-8")
                    except Exception:
                        header_text += part.decode("latin-1")
                else:
                    header_text += str(part)
            return header_text
        except Exception:
            return str(s)

    def get_messages(self, folder="INBOX", count=15):
        """
        Haalt de headers en een snippet van de laatste 'count' berichten op.
        Retourneert een lijst met dictionaries [{'id', 'sndr', 'subj', 'time', 'snip'}].
        """
        if not self.mail:
            if not self.connect():
                return []

        messages = []
        try:
            # Selecteer de folder in READ-ONLY modus voor maximale veiligheid
            status, _ = self.mail.select(folder, readonly=True)
            if status != "OK":
                print(f"Kon folder '{folder}' niet selecteren.")
                return []

            # Zoek naar alle berichten in de folder
            status, data = self.mail.search(None, "ALL")
            if status != "OK":
                return []

            mail_ids = data[0].split()
            # Pak de laatste 'count' ID's (nieuwste berichten staan achteraan)
            last_ids = mail_ids[-count:]
            last_ids.reverse() # Omgekeerde volgorde: nieuwste eerst

            for m_id in last_ids:
                status, msg_data = self.mail.fetch(m_id, "(RFC822)")
                if status != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        # Parse het ruwe bericht
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Haal headers op
                        subject = self._decode_str(msg.get("Subject"))
                        sndr = self._decode_str(msg.get("From"))
                        time = msg.get("Date")
                        
                        # Haal snippet op (max 150 tekens uit de tekstinhoud)
                        snippet = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        snippet = payload.decode(errors="ignore").strip()
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                snippet = payload.decode(errors="ignore").strip()

                        # Snippet opschonen: max 150 tekens en vervang regeleinden
                        snippet = snippet.replace("\r", " ").replace("\n", " ")
                        snippet = (snippet[:150] + "..") if len(snippet) > 150 else snippet

                        messages.append({
                            'id': m_id.decode(),
                            'sndr': sndr,
                            'subj': subject,
                            'time': time,
                            'snip': snippet
                        })

        except Exception as e:
            print(f"Onverwachte fout bij het ophalen van berichten: {e}")
        # Note: We verwijderen de logout() hier om de verbinding open te houden voor vervolgacties indien nodig, 
        # of we laten de aanroeper beslissen wanneer te logouten. 
        # Voor nu houden we de interface consistent met de gevraagde actie-methoden.

        return messages

    def get_all_folders(self):
        """Haalt een lijst van alle mapnamen op de server op."""
        if not self.mail:
            if not self.connect():
                return []
        
        folders = []
        try:
            status, folder_list = self.mail.list()
            if status == 'OK':
                for f in folder_list:
                    # De output van list() is meestal '(\Flags) "Delimiter" FolderName'
                    # We splitsen op de laatste delimiter om de naam te krijgen
                    parts = f.decode().split('"')
                    if len(parts) >= 3:
                        folders.append(parts[-1].strip())
                    else:
                        # Fallback als de foldernaam niet tussen aanhalingstekens staat
                        folders.append(f.decode().split()[-1])
        except Exception as e:
            print(f"Fout bij ophalen folders: {e}")
        return folders

    def create_folder(self, account_name, folder_name):
        """Maakt een nieuwe folder aan op de server (account_name wordt genegeerd)."""
        if not self.mail:
            if not self.connect():
                return False
        
        try:
            status, _ = self.mail.create(folder_name)
            return status == 'OK'
        except Exception as e:
            print(f"Fout bij aanmaken folder '{folder_name}': {e}")
            return False

    def move_message(self, message_id, target_folder_name):
        """Verplaatst een bericht van de INBOX naar de doelmap."""
        if not self.mail:
            if not self.connect():
                return False

        try:
            # We moeten in READ-WRITE modus zijn om vlaggen te kunnen aanpassen (voor het wissen)
            self.mail.select("INBOX", readonly=False)
            
            # 1. Kopieer naar doelmap
            status, _ = self.mail.copy(message_id, target_folder_name)
            if status != 'OK':
                return False
            
            # 2. Markeer als verwijderd in de bronmap
            self.mail.store(message_id, '+FLAGS', '\\Deleted')
            
            # 3. Definitief wissen uit de bronmap
            self.mail.expunge()
            return True
        except Exception as e:
            print(f"Fout bij verplaatsen bericht {message_id}: {e}")
            return False

    def logout(self):
        """Verbreekt de verbinding met de server."""
        if self.mail:
            try:
                self.mail.close()
                self.mail.logout()
            except:
                pass
            finally:
                self.mail = None

if __name__ == "__main__":
    # Eenvoudige test om de client live te proberen
    print("Test: ImapClient ophalen van recente berichten...")
    client = ImapClient()
    msgs = client.get_messages(count=5)
    
    if not msgs:
        print("Geen berichten gevonden of fout bij verbinding.")
    
    for m in msgs:
        print("-" * 30)
        print(f"ID: {m['id']}")
        print(f"Van: {m['sndr']}")
        print(f"Onderwerp: {m['subj']}")
        print(f"Datum: {m['time']}")
        print(f"Snippet: {m['snip']}")

import imaplib
import email
import os
from dotenv import load_dotenv
from controller.archive_parser import parse_eml_file

# Zorg dat we omgevingsvariabelen kunnen laden
load_dotenv()

def fetch_recent_emails(limit: int = 5) -> list:
    """
    Maakt verbinding met een IMAP server en haalt de meest recente e-mails op.
    Veiligheid: De verbinding is ALTIJD read-only.
    """
    # 1. Credentials ophalen uit de veilige .env file
    imap_server = os.getenv('IMAP_SERVER')
    imap_user = os.getenv('IMAP_USER')
    imap_pass = os.getenv('IMAP_PASS')

    # Validatie van credentials
    if not all([imap_server, imap_user, imap_pass]):
        return [{"status": "Error", "error": "Ontbrekende IMAP credentials (IMAP_SERVER, IMAP_USER, IMAP_PASS) in .env"}]

    results = []
    mail_conn = None

    try:
        # 2. Verbinden via SSL
        mail_conn = imaplib.IMAP4_SSL(imap_server)
        
        # 3. Inloggen
        mail_conn.login(imap_user, imap_pass)
        
        # 4. Selecteer INBOX in READ-ONLY modus (CRUCIAAL VOOR VEILIGHEID)
        # De agent kan hierdoor NOOIT mails verwijderen of als gelezen markeren.
        status, _ = mail_conn.select("INBOX", readonly=True)
        if status != 'OK':
            return [{"status": "Error", "error": f"Kon INBOX niet selecteren: {status}"}]

        # 5. Zoek naar alle e-mails in de inbox
        status, data = mail_conn.search(None, "ALL")
        if status != 'OK':
            return [{"status": "Error", "error": "Fout bij het zoeken naar e-mails."}]

        # Haal de lijst met mail-ID's op
        mail_ids = data[0].split()
        
        # Pak de laatste 'limit' ID's (nieuwste mails staan achteraan)
        recent_ids = mail_ids[-limit:]
        recent_ids.reverse() # Draai om zodat de nieuwste bovenaan staan

        for m_id in recent_ids:
            # Fetch de ruwe e-mail data (RFC822 formaat)
            status, msg_data = mail_conn.fetch(m_id, "(RFC822)")
            
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    # Decodeer de bytes naar een string voor de parser
                    # We gebruiken 'ignore' voor eventuele corrupte karakters
                    raw_email_str = response_part[1].decode('utf-8', errors='ignore')
                    
                    # Gebruik onze bestaande archive_parser om de mail te ontleden
                    parsed_email = parse_eml_file(raw_email_str)
                    results.append(parsed_email)

    except imaplib.IMAP4.error as e:
        return [{"status": "Error", "error": f"IMAP Verbindingsfout: {str(e)}"}]
    except Exception as e:
        return [{"status": "Error", "error": f"Onverwachte fout bij mail fetch: {str(e)}"}]
    
    finally:
        # 6. Verbinding ALTIJD netjes sluiten
        if mail_conn:
            try:
                mail_conn.close()
                mail_conn.logout()
            except:
                pass # Stille afsluiting als sessie al weg is

    return results

if __name__ == "__main__":
    # Test validatie (vereist gevulde .env)
    print("--- Start Live Mail Fetcher Test ---")
    print(f"Poging om de laatste 2 mails op te halen van {os.getenv('IMAP_SERVER', 'ONBEKEND')}...")
    
    mails = fetch_recent_emails(limit=2)
    for i, m in enumerate(mails):
        print(f"\n[MAIL {i+1}]")
        if m.get('status') == "Success":
            print(f"Onderwerp: {m.get('subject')}")
            print(f"Van: {m.get('from')}")
            print(f"Body (eerste 100 tekens): {m.get('body')[:100]}...")
        else:
            print(f"FOUT: {m.get('error')}")

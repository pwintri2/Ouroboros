import re
from controller.imap_client import ImapClient

class MailExecutor:
    def __init__(self):
        self.mail_client = ImapClient()

    def parse_plan(self, plan_text):
        plan = {}
        current_folder = None
        lines = plan_text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if line.startswith("* Map:"):
                # Haal de basisnaam op
                raw_folder = line.replace("* Map:", "").strip()
                
                # SANITIZER: Verwijder markdown, slashes, en rare tekens
                clean_folder = raw_folder.replace("*", "").replace("/", "-").replace(":", "-").replace('"', "").replace("'", "")
                current_folder = clean_folder.strip()
                
                if current_folder and current_folder not in plan:
                    plan[current_folder] = []
                    
            elif line.startswith("- ID:") and current_folder:
                id_match = re.search(r"ID:\s*(\d+)", line)
                if id_match:
                    plan[current_folder].append(id_match.group(1))
                    
        return plan
    
    def run_action_plan(self, plan_text):
        plan = self.parse_plan(plan_text)
        results = []
        
        try:
            for folder_name, message_ids in plan.items():
                # Map aanmaken via IMAP (account_name 'None' voor compatibiliteit)
                success = self.mail_client.create_folder(None, folder_name)
                status_msg = "OK" if success else "REEDS BESTAAND/FOUT"
                results.append(f"Map: {folder_name} -> {status_msg}")
                
                for msg_id in message_ids:
                    move_success = self.mail_client.move_message(msg_id, folder_name)
                    move_status = "OK" if move_success else "FOUT"
                    results.append(f"  ID {msg_id} -> {move_status}")
        finally:
            # Sluit de verbinding aan het eind van de executie
            self.mail_client.logout()
            
        return "\n".join(results)
import subprocess

class OutlookClient:
    def _run_script(self, script):
        try:
            res = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except Exception as e:
            return f"ERROR: {str(e)}"

    def get_messages(self, folder='inbox', count=15, only_unread=False):
        # We gebruiken de kogelvrije methode: elk veld heeft zijn eigen try/catch blok
        script = f"""
        tell application "Microsoft Outlook"
            set allAccts to every imap account & every exchange account & every pop account
            set output to ""
            set fetchedCount to 0
            
            repeat with acct in allAccts
                set allFolders to every mail folder of acct
                repeat with fld in allFolders
                    if name of fld is "INBOX" then
                        set msgs to messages of fld
                        set mCount to count of msgs
                        
                        repeat with i from 1 to mCount
                            if fetchedCount >= {count} then exit repeat
                            set msg to item i of msgs
                            
                            -- 1. Veilig ID ophalen (Dit lukt altijd)
                            set msgId to id of msg
                            
                            -- 2. Veilig Onderwerp ophalen
                            try
                                set subj to subject of msg
                            on error
                                set subj to "Geen onderwerp"
                            end try
                            
                            -- 3. Veilig Afzender ophalen (Dit crashte in de eerdere scan)
                            try
                                set sndr to address of sender of msg
                            on error
                                set sndr to "Onbekende afzender"
                            end try
                            
                            -- 4. Veilig Tijd ophalen
                            try
                                set rcvd to (time received of msg) as string
                            on error
                                set rcvd to "Onbekende tijd"
                            end try
                            
                            -- 5. Veilig Inhoud ophalen (Vaak afgeschermd in New Outlook)
                            try
                                set cont to plain text content of msg
                                if length of cont > 150 then
                                    set snip to text 1 thru 150 of cont
                                else
                                    set snip to cont
                                end if
                            on error
                                set snip to "[Inhoud onleesbaar via AppleScript]"
                            end try
                            
                            set output to output & "ID:" & msgId & "|SNDR:" & sndr & "|SUBJ:" & subj & "|TIME:" & rcvd & "|SNIP:" & snip & "[[BREAK]]"
                            set fetchedCount to fetchedCount + 1
                        end repeat
                    end if
                end repeat
            end repeat
            return output
        end tell
        """
        raw = self._run_script(script)
        if "ERROR" in raw or not raw: return []
        
        messages = []
        for entry in raw.split("[[BREAK]]"):
            if not entry.strip(): continue
            msg_data = {}
            for part in entry.split("|"):
                if ":" in part:
                    k, v = part.split(":", 1)
                    msg_data[k.lower()] = v
            messages.append(msg_data)
        return messages

    def get_all_folders(self):
        script = """
        tell application "Microsoft Outlook"
            set allAccts to every imap account & every exchange account & every pop account
            set allFolderNames to {}
            repeat with acct in allAccts
                try
                    set acctName to name of acct
                    set flds to name of every mail folder of acct
                    repeat with fName in flds
                        set end of allFolderNames to acctName & " > " & fName
                    end repeat
                end try
            end repeat
            return allFolderNames
        end tell
        """
        raw = self._run_script(script)
        if "ERROR" in raw: return []
        # Zet de lijst om in een schone Python-list
        return [f.strip() for f in raw.split(",")]

    def create_folder(self, account_name, folder_name):
        script = f"""
        tell application "Microsoft Outlook"
            set success to false
            set allAccts to every exchange account & every imap account & every pop account
            repeat with acct in allAccts
                try
                    if not (exists mail folder "{folder_name}" of acct) then
                        make new mail folder with properties {{name:"{folder_name}"}} at acct
                    end if
                    set success to true
                    exit repeat
                end try
            end repeat
            if success then return "OK"
            return "FAIL"
        end tell
        """
        return self._run_script(script)

    def move_message(self, message_id, target_folder_name):
        script = f"""
        tell application "Microsoft Outlook"
            try
                set msg to message id {message_id}
                set targetFolder to mail folder "{target_folder_name}" of account 1
                move msg to targetFolder
                return "OK"
            on error e
                return "ERROR: " & e
            end try
        end tell
        """
        return self._run_script(script)
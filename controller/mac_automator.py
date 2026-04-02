import subprocess

class MacAutomator:
    @staticmethod
    def open_app(app_name):
        script = f'tell application "{app_name}" to activate'
        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            return f"Wintrip: Ik heb '{app_name}' voor je geopend op je Mac."
        except subprocess.CalledProcessError:
            return f"Wintrip: Het is niet gelukt om '{app_name}' te openen."
        except Exception as e:
            return f"FOUT: {str(e)}"

    @staticmethod
    def ask_chatgpt(question):
        # We maken de tekst veilig voor AppleScript, we ontsnappen alle quotes
        safe_q = question.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
        
        # Dit script is veel agressiever in het eisen van focus
        script = f'''
        tell application "ChatGPT"
            activate
        end tell
        
        -- Geef de app ruim de tijd om te laden en het venster te focussen
        delay 1.5
        
        tell application "System Events"
            -- Zorg dat ChatGPT de 'frontmost' applicatie is
            set frontmost of process "ChatGPT" to true
            delay 0.5
            
            -- Simuleer de toetsaanslagen
            tell process "ChatGPT"
                keystroke "{safe_q}"
                delay 0.2
                key code 36 -- Return key
            end tell
        end tell
        '''
        try:
            import subprocess
            # We voeren het uit, maar vangen ook de error op als het faalt
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            
            if result.returncode != 0:
                return f"FOUT bij typen in ChatGPT. Error: {result.stderr.strip()}"
                
            return "Wintrip: Ik heb je vraag zojuist aan de ChatGPT-app gesteld."
        except Exception as e:
            return f"CRASH: Kon ChatGPT niet aansturen. ({str(e)})"
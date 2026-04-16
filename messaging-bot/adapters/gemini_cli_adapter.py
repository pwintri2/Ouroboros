import subprocess

class GeminiCLIAdapter:
    def __init__(self, cli_path="gemini"):
        self.cli_path = cli_path

    def send_message(self, message):
        try:
            result = subprocess.run(
                [self.cli_path, "query", message],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            return f"Gemini CLI error: {e.stderr}"
        except Exception as e:
            return f"Error running Gemini CLI: {str(e)}"

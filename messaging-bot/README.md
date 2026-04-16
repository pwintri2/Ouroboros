# Messaging Bot

This bot acts as an intermediary between Goose and external tools like Codex, Antigravity, Grok, Gemini CLI, and Ollama.

## Setup

1. **Prerequisites**: Ensure Python 3 is installed.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure**: Edit `config.yaml` with your API keys and tool paths.
4. **Start the bot**:
   ```bash
   ./start_bot.sh
   ```

## Usage

Send a POST request to `http://localhost:5005/send` with a JSON payload:

```json
{
  "tool": "ollama",
  "message": "Hello, how are you?"
}
```

Supported tools are defined in `config.yaml` and implemented in `adapters/`.

#!/usr/bin/env python3
import argparse
import requests
import json
import sys

def main():
    parser = argparse.ArgumentParser(description="Wintrip Swarm Delegate")
    parser.add_argument("--persona", required=True, help="Persona Name")
    parser.add_argument("--model", required=True, help="Target Model (e.g., ollama, gemini_cli)")
    parser.add_argument("--prompt", required=True, help="Message/Prompt to send")
    args = parser.parse_args()

    payload = {
        "persona": args.persona,
        "tool": args.model,
        "message": args.prompt
    }

    try:
        # Sending to the local Wintrip Message Router
        response = requests.post("http://localhost:5005/send", json=payload)
        response.raise_for_status()
        print(response.json().get("response", "No response content"))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

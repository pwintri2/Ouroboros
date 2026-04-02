import re
import sys
import tempfile
import subprocess
import os
import json
import requests
import concurrent.futures
from typing import Dict, Optional, List, Tuple

try:
    from controller.ollama_client import OllamaClient
except ImportError:
    from ollama_client import OllamaClient

def extract_python_code(text: str) -> List[Tuple[int, int]]:
    """
    Extracts start and end indices of python code blocks.
    """
    pattern = r'```python\n(.*?)\n```'
    matches = re.finditer(pattern, text, re.DOTALL)
    return [(m.start(1), m.end(1)) for m in matches]

class VirtualMeeting:
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.roles = ['Developer', 'Critic', 'Tester1', 'Tester2']
        self.conversation_history = {}
        self.task = None
        self.ollama = ollama_client or OllamaClient()
        self.review = []

    def run_meeting(self, task: str) -> Dict[str, str]:
        """
        Simulates a virtual meeting by querying the local Ollama API.
        M4 Hardware Optimization: Sequential early phases, parallel Tester phase.
        :param task: The task to be discussed in the meeting
        :return: The full conversation history
        """
        self.task = task

        # Developer writes a proposal based on the task (zware logica, dus llama3.1)
        developer_prompt = f"Schrijf een concreet, technisch voorstel en eventuele Python code voor deze taak: {task}. Gebruik maximaal 100 woorden voor je theorie. BELANGRIJK: Gebruik uitsluitend Python standard libraries (os, json, urllib, re) en importeer NOOIT externe pip modules (zoals requests, slackbot, azure) tenzij expliciet gevraagd."
        developer_proposal = self._query_ollama(developer_prompt, role='Developer', model='llama3.1:latest')
        self.conversation_history['Developer'] = developer_proposal

        # Critic reviews the proposal (sterk geredeneerd, kleine footprint, dus phi3)
        critic_prompt = f"Bekijk het volgende voorstel van de Developer uiterst kritisch en benoem veiligheids- of structuurrisico's:\n\n{developer_proposal}. Reageer in maximaal 3 zinnen."
        critic_review = self._query_ollama(critic_prompt, role='Critic', model='phi3:latest')
        self.conversation_history['Critic'] = critic_review

        # Check for Python code in Developer/Critic's response
        code_blocks = extract_python_code(developer_proposal) + extract_python_code(critic_review)
        if code_blocks:
            # We need to decide which response to slice from if we combine them like this.
            # Better to do it separately or store which response it came from.
            
            # Developer response
            dev_blocks = extract_python_code(developer_proposal)
            for start, end in dev_blocks:
                code_block = developer_proposal[start:end]
                stdout, stderr = self.run_code(code_block)
                self.review.append(f"Executed code block: {code_block}\n")
                self.review.append(f"Console Output: {stdout}\n")
                self.review.append(f"Console Errors: {stderr}\n")
            
            # Critic response
            critic_blocks = extract_python_code(critic_review)
            for start, end in critic_blocks:
                code_block = critic_review[start:end]
                stdout, stderr = self.run_code(code_block)
                self.review.append(f"Executed code block: {code_block}\n")
                self.review.append(f"Console Output: {stdout}\n")
                self.review.append(f"Console Errors: {stderr}\n")
        else:
            # State that the proposal is theoretical and approve it
            self.review.append("Proposal is theoretical. Approving...\n")

        # PARALLEL EXECUTION: Testers draaien tegelijkertijd in threads
        def run_tester1():
            t1_prompt = f"Ontwerp één eenheidstest (Unit test) concept gebaseerd op deze review:\n\n{critic_review}"
            return self._query_ollama(t1_prompt, role='Tester1', model='gemma2:2b')

        def run_tester2():
            t2_prompt = f"Valideer de complexiteit en edge-cases van de aanpak hier gelist:\n\n{critic_review}"
            return self._query_ollama(t2_prompt, role='Tester2', model='qwen2.5:latest')

        # Start de threads! Max Workers 2 omdat we precies 2 testers hebben.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_t1 = executor.submit(run_tester1)
            future_t2 = executor.submit(run_tester2)

            tester_feedback1 = future_t1.result()
            tester_feedback2 = future_t2.result()

        self.conversation_history['Tester1'] = tester_feedback1
        self.conversation_history['Tester2'] = tester_feedback2
        
        # Include the actual console output/errors in the Tester's review
        # Structuring as a dict to support the deployment step's error handling
        self.conversation_history['Tester Review'] = {
            'content': "".join(self.review),
            'errors': [line for line in self.review if "Console Errors:" in line and line.strip() != "Console Errors:"]
        }

        # Step 5: Update run_meeting Function to Call deployment_step
        self.deployment_step(self.conversation_history)

        return self.conversation_history

    def deployment_step(self, meeting_data):
        """
        Step 1: Implement Deployment step to extract finalized code and write to file.
        """
        # Step 4: Handle Tester Review Errors
        if meeting_data.get('Tester Review', {}).get('errors'):
            # skip deployment and note error in transcript
            error_msg = f"Deployment skipped due to Tester Review errors: {meeting_data['Tester Review']['errors']}"
            print(error_msg)
            return

        # Step 2: Implement LLM Call to Extract Finalized Code and Determine Filename
        content = meeting_data['Tester Review']['content']
        payload = {'model': 'llama3.1', 'prompt': f'Extract the final python code from this transcript and suggest a filename. Transcript: {content}. Return ONLY valid JSON with keys filename and code without markdown formatting.', 'stream': False}
        
        try:
            response = requests.post('http://127.0.0.1:11434/api/generate', json=payload)
            response.raise_for_status()
            response_json = response.json().get('response', '{}')
            
            # Verify that response_json contains only valid JSON with keys filename and code
            llm_json = json.loads(response_json)
            
            # Step 3: Write Extracted Code to File
            filename = llm_json.get("filename")  # use LLM's suggested filename if available
            if not filename:
                filename = "new_feature.py"
            code = llm_json.get("code")
            
            if code:
                file_path = f"/app/python/{filename}"
                with open(file_path, "w") as f:
                    f.write(code)
                print(f"Code successfully deployed to {file_path}")
            else:
                print("No code extracted from LLM response.")
            
            return response_json
        except Exception as e:
            print(f"Deployment skipped or failed: {e}")

    def run_code(self, code: str) -> Tuple[str, str]:
        """
        Veilige uitvoering via de Wintrip Docker Sandbox in plaats van lokaal.
        """
        from controller.sandbox import SandboxExecutor
        sandbox = SandboxExecutor()
        
        output = sandbox.run_python_code(code)
        
        if "[SANDBOX ERROR" in output or "[SANDBOX FATAL ERROR]" in output:
             return "", output
        
        return output, ""

    def _query_ollama(self, input_text: str, role: str, model: str = None) -> str:
        """
        Queries the local Ollama API via OllamaClient using a specific targeted model.
        """
        system_prompt = f"Je bent een {role} in een software development team. Ontwijk onnodige introducties. Beantwoord professioneel, feitelijk en zo kort mogelijk in het Nederlands. VERBODEN: Gebruik in je Python code NOOIT externe pip libraries (geen slackbot, geen codeclimate, geen azure). Gebruik ALTIJD uitsluitend standard Python libraries (json, os, sys, urllib, sqlite3, threading)."
        return self.ollama.chat(user_input=input_text, system_prompt=system_prompt, model=model)

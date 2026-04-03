import uuid
from controller.knowledge_base import KnowledgeBase

class Reflector:
    def __init__(self, kb=None):
        """Initialiseert de Reflector engine met een gekoppelde Hippocampus"""
        self.kb = kb if kb else KnowledgeBase()

    def evaluate_action(self, task_name, result_raw_output, expected_outcome=None):
        """
        Deterministische regel-gebaseerde evaluatie van een actie.
        (Minimale integratie volgens Phase 2 richtlijnen)
        """
        print(f"🪞 [Reflector]: Evalueert actie '{task_name}'...")
        
        reflection_type = "insight"
        insight_text = ""
        
        output_lower = result_raw_output.lower()
        task_lower = task_name.lower()
        
        # Specifieke sandbox fouten
        if "filenotfounderror" in output_lower or "no such file or directory" in output_lower:
            reflection_type = "failure"
            insight_text = (
                "FOUT: Je code probeerde een extern bestand te lezen dat niet bestaat in de Docker sandbox. "
                "De container is leeg behalve jouw script. "
                "Oplossing: schrijf alle data die je nodig hebt direct in het script, of genereer het met code. "
                "Gebruik GEEN open() voor bestanden die je niet zelf aanmaakt in hetzelfde script."
            )
        # Simpele deterministische detectie
        elif any(keyword in output_lower for keyword in ["error", "traceback", "exception", "failed", "permission denied", "access denied", "operation not permitted", "timeout", "time-out", "fout", "mislukt", "gecrasht"]) or \
           any(keyword in task_lower for keyword in ["error", "readtimeout", "timeout", "gefaald", "fout"]):
            reflection_type = "failure"
            insight_text = f"De actie '{task_name}' is gefaald of deels gestrand (Mogelijke timeout of exception). Mogelijke oorzaak te vinden in de log output."
        elif any(keyword in output_lower for keyword in ["success", "passed", "done", "voltooid"]):
            reflection_type = "success"
            insight_text = f"De actie '{task_name}' lijkt succesvol afgerond."
        else:
            reflection_type = "insight"
            insight_text = f"Observatie over '{task_name}': Actie voltooid maar resultaat ambigu."

        if expected_outcome:
            insight_text += f"\nVerwachte uitkomst was: {expected_outcome}"
            
        # Zorg voor geisoleerde tekst opslag (geen file path bleeding)
        full_reflection_text = f"TAAK: {task_name}\nRESULTAAT TYPE: {reflection_type.upper()}\nINZICHT: {insight_text}\nLOG SNIPPET: {result_raw_output[:500]}"
        
        # Sla op in de Knowledge Base
        tags = f"reflector_eval,{task_name.replace(' ', '_').lower()}"
        success = self.kb.ingest_reflection(
            text=full_reflection_text,
            reflection_type=reflection_type,
            tags=tags,
            interaction_id=str(uuid.uuid4())
        )
        
        return {
            "type": reflection_type,
            "insight": insight_text,
            "stored": success
        }

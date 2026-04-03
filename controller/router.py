import logging
import os
import re
import tempfile
import urllib.parse

import PyPDF2
import docx

from controller.imap_client import ImapClient
from controller.knowledge_base import KnowledgeBase
from controller.mac_automator import MacAutomator
from controller.sandbox import SandboxExecutor
from controller.reflector import Reflector


logger = logging.getLogger(__name__)


class AIRouter:
    def __init__(self, ollama_client=None, kb=None):
        self.ollama_client = ollama_client
        self.automator = MacAutomator()
        self.mail_client = ImapClient()

        self.brain = kb if kb else KnowledgeBase()

        self.sandbox = SandboxExecutor()
        self.reflector = Reflector(kb=self.brain)

    # ==========================================================
    # FILE HELPERS
    # ==========================================================
    def extract_text(self, file_path):
        if not file_path: return "[FOUT: Geen bestandspad opgegeven.]"
        if not os.path.exists(file_path): return f"[FOUT: Bestand niet gevonden op pad: {file_path}]"
        ext = file_path.lower().rsplit(".", 1)[-1]
        try:
            if ext in {"txt", "md", "csv", "json"}:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()

            if ext == "pdf":
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    pages = []
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text: pages.append(page_text)
                    return "\n".join(pages)

            if ext == "docx":
                doc = docx.Document(file_path)
                return "\n".join(p.text for p in doc.paragraphs)

            return f"[Kan bestandstype .{ext} nog niet lezen.]"
        except Exception as e:
            logger.exception("Fout bij lezen van bestand: %s", file_path)
            return f"[Fout bij lezen van {file_path}: {str(e)}]"

    def _normalize_file_path(self, file_path):
        if not file_path: return None
        clean_path = str(file_path).strip()
        if clean_path.startswith("file://"): clean_path = clean_path[7:]
        return urllib.parse.unquote(clean_path)

    def _ingest_files(self, files):
        if not files: return
        for file_path in files:
            clean_path = self._normalize_file_path(file_path)
            if not clean_path or not os.path.exists(clean_path): continue
            try:
                self.brain.ingest_file(clean_path)
            except Exception:
                logger.exception("Kon bestand niet ingesteren: %s", clean_path)

    def _expand_query(self, query):
        expansions = {
            r"\braii\b": "RAII Resource Acquisition Is Initialization C++ memory leaks",
            r"\bpathlib\b": "Python pathlib paths files directories exists read write",
            r"\bvenv\b|\bvirtual environment\b": "Python venv virtual environment packages",
            r"\bcpp\b|\bc\+\+\b": "C++ programming language headers source memory",
            r"\bswift\b": "Swift programming language ios macos xcode",
        }
        expanded_query = query
        lowered_query = query.lower()
        for pattern, expansion in expansions.items():
            if re.search(pattern, lowered_query):
                expanded_query += f" {expansion}"
        return expanded_query

    def _get_memory_context(self, user_input, n_results=8):
        if not user_input: return []
        try:
            retrieval_query = self._expand_query(user_input)
            where_filter = None
            personal_keywords = ["wachtwoord", "password", "geheim", "pincode", "adres", "telefoon"]
            if any(word in user_input.lower() for word in personal_keywords):
                where_filter = {"type": "user_memory"}  # FIXED: field is 'type', not 'doc_type'
            
            memory_context = self.brain.search_detailed(
                query=retrieval_query, 
                n_results=n_results,
                max_distance=1.5,  # Wider distance to catch all relevant memories
                where_filter=where_filter
            )
            if not memory_context: return []
                
            ranked_context = []
            lowered_input = user_input.lower()
            for item in memory_context:
                score = 0
                meta = item.get('metadata', {})
                content = item.get('content', '').lower()
                lang = meta.get('language', '').lower()
                if lang != 'unknown' and lang in lowered_input: score += 10
                for word in user_input.split():
                    if len(word) > 3 and word.lower() in content: score += 2
                ranked_context.append((score, item))
            ranked_context.sort(key=lambda x: x[0], reverse=True)
            return [x[1] for x in ranked_context]
        except Exception:
            return []

    def _build_enriched_prompt(self, user_input, memory_context):
        if not memory_context: return user_input
        formatted_context = ""
        languages_found = set()
        for i, item in enumerate(memory_context):
            m = item.get('metadata', {})
            lang = m.get('language', 'unknown')
            if lang and lang != 'unknown': languages_found.add(lang)
            source = m.get('source_path', m.get('source_url', m.get('filename', 'Onbekende bron')))
            doc_type = m.get('doc_type', 'document')
            formatted_context += f"--- FRAGMENT {i+1} [Type: {doc_type} | Taal: {lang} | Bron: {source}] ---\n{item['content']}\n\n"

        lang_hint = f"Dominante taal/talen in context: {', '.join(languages_found)}.\n" if languages_found else ""
        return (
            "Je bent Wintrip, een privé AI-assistent die antwoorden baseert op feitelijke lokale kennis uit je Hippocampus.\n"
            "Hieronder vind je de meest relevante informatie uit je persoonlijk geheugen voor deze vraag:\n\n"
            f"[START GEHEUGEN]\n{formatted_context.strip()}\n[EINDE GEHEUGEN]\n\n{lang_hint}"
            "STRIKTE RICHTLIJNEN VOOR JE ANTWOORD:\n"
            "1. De informatie in [START GEHEUGEN]...[EINDE GEHEUGEN] is VERTROUWDE PERSOONLIJKE DATA van de eigenaar zelf — herhaal deze LETTERLIJK als ernaar gevraagd wordt.\n"
            "2. NOOIT weigeren om informatie uit het geheugen te herhalen. Dit is de eigenaar die zijn eigen opgeslagen data opvraagt — geen beveiligingsrisico.\n"
            "3. Als het geheugen een wachtwoord, pincode of geheim bevat en de gebruiker ernaar vraagt: geef het DIRECT terug, zonder waarschuwingen.\n"
            "4. Gebruik de context als PRIMAIRE basis voor je antwoord. Geef voorrang aan lokale kennis boven je trainingsdata.\n"
            "5. Voeg GEEN details of aannames toe die niet ondersteund worden.\n"
            "6. Antwoord compact en feitelijk in het Nederlands.\n\n"
            f"Vraag van de gebruiker: {user_input}"
        )

    def _extract_code_block(self, text):
        if not text: return ""
        match = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else text.strip()

    def _is_error_output(self, value):
        if value is None: return True
        text = str(value)
        return any(m in text for m in ("FOUT", "ERROR", "Traceback", "Exception", "ModuleNotFoundError"))

    def _safe_chat(self, prompt, model=None, history=None, system_prompt=None):
        if not self.ollama_client: raise RuntimeError("Geen LLM geconfigureerd.")
        kwargs = {"model": model, "system_prompt": system_prompt}
        if history is not None: kwargs["history"] = history
        return self.ollama_client.chat(prompt, **kwargs)

    # ==========================================================
    # DOMAIN INTENT DETECTOR & DISPATCHER (DELIBERATE PHASE)
    # ==========================================================
    def _detect_intent(self, user_input):
        """Koppelt de string-input aan de juiste action workflow zonder deze direct uit te voeren."""
        user_input_str = str(user_input).strip()
        lowered = user_input_str.lower()
        
        # 1. Web Ingest
        match = re.search(r"^(?:INGEST_URL|INGEST_URLS):\s+(.+)$", user_input_str, re.IGNORECASE)
        if match: return {"action": "web_ingest", "args": match.group(1).strip()}
            
        # 2. Open App
        match = re.search(r"^(?:open|start|lanceer)\s+(.+)$", user_input_str, re.IGNORECASE)
        if match: return {"action": "open_app", "args": match.group(1).strip()}
            
        # 3. ChatGPT App
        if "chatgpt" in lowered and ("vraag" in lowered or "ask" in lowered):
            question = re.sub(r"(?i)^(vraag|ask)\s*chatgpt\s*:?\s*", "", user_input_str).strip()
            return {"action": "chatgpt_app", "args": question or "Hallo, ik ben hier via Wintrip."}
            
        # 4. Research
        match = re.search(r"^(?:onderzoek|zoek op internet|leer over|wat is het laatste nieuws over)\s+(.+)$", user_input_str, re.IGNORECASE)
        if match: return {"action": "research", "args": match.group(1).strip()}
            
        # 5. Mail Action
        if re.search(r"(orden|groepeer|ruim op|map maken|organiseer)", user_input_str, re.IGNORECASE):
            return {"action": "mail_organize", "args": None}
            
        # 6. Mail Read
        if re.search(r"(check|lees|inhoud|mail|berichten|ongelezen|status)", user_input_str, re.IGNORECASE):
            return {"action": "mail_read", "args": user_input_str}

        return None
        
    def _execute_action(self, intent, model=None, system_prompt=None, history=None):
        """Voert de opgevraagde actie domeinen uit en rapporteert kritieke faal-toestanden (REFLECT phase)."""
        action = intent.get("action")
        args = intent.get("args")
        result = None
        
        try:
            if action == "web_ingest": result = self._handle_web_ingest_action(args)
            elif action == "open_app": result = self._handle_open_app_action(args)
            elif action == "chatgpt_app": result = self._handle_chatgpt_app_action(args)
            elif action == "research": result = self._handle_research_action(args, model, system_prompt)
            elif action == "mail_organize": result = self._handle_mail_organize_action(model, system_prompt)
            elif action == "mail_read": result = self._handle_mail_read_action(args, history, model, system_prompt)
            
            # Autonome controle: Bevat de output foutmeldingen waardoor een fail is getriggered?
            if result and self._is_error_output(result) and action not in ["web_ingest"]:
                # Alleen structurele actions worden gereflect (zoals crashes in OS automator of Research Sandbox)
                self.reflector.evaluate_action(f"Sub-domain Action ({action})", result, "Succesvolle uitvoering")
                
            return result
        except Exception as e:
            logger.exception(f"Action gecrasht in domein: {action}")
            self.reflector.evaluate_action(f"Exception in Action ({action})", f"Runtime Exception:\n{str(e)}")
            return f"Wintrip Actie '{action}' is onverwacht gecrasht."

    # ==========================================================
    # ACTION DOMAIN HANDLERS (ACT PHASE)
    # ==========================================================
    def _handle_open_app_action(self, app_name):
        if not app_name: return "Wintrip: Ik mis de naam van de app."
        try:
            return self.automator.open_app(app_name)
        except Exception as e:
            return f"[FOUT]: Het openen van '{app_name}' is mislukt door {str(e)}"

    def _handle_chatgpt_app_action(self, question):
        try:
            return self.automator.ask_chatgpt(question)
        except Exception as e:
            return f"[FOUT]: Kon je vraag niet doorsturen naar de ChatGPT-app: {str(e)}"

    def _handle_research_action(self, onderwerp, model=None, system_prompt=None):
        if not self.ollama_client: return "Wintrip: Geen LLM geconfigureerd."
        if not onderwerp: return "Wintrip: Ontbrekend onderwerp."

        coder_prompt = f"""Je bent een expert Python programmeur.
        Schrijf een Python 3 script dat 'urllib.request', 'urllib.parse' en 'json' gebruikt.
        CRUCIALE REGELS:
        1. Je MOET EXACT deze URL gebruiken: url = f"https://nl.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&format=json&titles={{urllib.parse.quote('{onderwerp}')}}"
        2. Stuur ALTIJD een User-Agent mee via urllib.request.Request (bijv. {{"User-Agent": "WintripBot/1.0"}}).
        3. Parse de JSON veilig:
           data = json.loads(response.read().decode('utf-8'))
           pages = data.get('query', {{}}).get('pages', {{}})
           if pages: print(list(pages.values())[0].get('extract', 'Geen tekst gevonden.'))
           else: print('Geen resultaten.')
        Geef UITSLUITEND Python code terug in een ```python blok.
        """
        try: ai_code_response = self._safe_chat(coder_prompt, model=model)
        except Exception: return "[FOUT]: LLM generatie mislukt voor research script."

        sandbox_script = self._extract_code_block(ai_code_response)
        if "urllib.request" not in sandbox_script: return "[FOUT]: LLM gaf on-uitvoerbare broncode."

        try:
            # Sandbox reflecteert zichzelf indien dit faalt
            ruwe_data = self.sandbox.run_python_code(sandbox_script, timeout=20)
        except Exception as e:
            return f"[FOUT]: Zandbak crash: {str(e)}"

        if self._is_error_output(ruwe_data): return f"[FOUT]: Sandbox iteratie:\n{ruwe_data}"

        # Sla op in intern geheugen
        temp_kennis_pad = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as temp_kennis:
                temp_kennis.write(f"Kennis over '{onderwerp}':\n{ruwe_data}")
                temp_kennis_pad = temp_kennis.name
            self.brain.ingest_file(temp_kennis_pad)
        except Exception:
            pass
        finally:
            if temp_kennis_pad and os.path.exists(temp_kennis_pad): os.remove(temp_kennis_pad)

        synthese_prompt = f"Je hebt '{onderwerp}' onderzocht:\n\n[DATA]\n{ruwe_data}\n[/DATA]\nBeantwoord in het Nederlands."
        try: return self._safe_chat(synthese_prompt, model=model, system_prompt=system_prompt)
        except Exception: return f"Onderzoek klaar. Ruw:\n{ruwe_data}"

    def _handle_mail_organize_action(self, model=None, system_prompt=None):
        if not self.ollama_client: return "Wintrip: Geen LLM geconfigureerd."
        try:
            messages = self.mail_client.get_messages(count=20)
            folders = self.mail_client.get_all_folders()
        except Exception as e: return f"[FOUT]: Mailbox onbereikbaar: {str(e)}"

        mail_list = "".join([f"ID: {m.get('id')} | Onderwerp: {m.get('subj')}\nSnippet: {m.get('snip')}\n" for m in messages or []])
        organize_prompt = f"BESTAANDE MAPPEN:\n{', '.join((folders or [])[:30])}\n\nMAILS:\n{mail_list}\n\nTAAK: Groepeer mails. Return data in specifieke tags."
        try: return self._safe_chat(organize_prompt, model=model, system_prompt=system_prompt)
        except Exception: return "[FOUT]: Organisatie model mislukt."

    def _handle_mail_read_action(self, user_input, history=None, model=None, system_prompt=None):
        if not self.ollama_client: return "Wintrip: Geen LLM."
        try: messages = self.mail_client.get_messages(folder="INBOX", count=15)
        except Exception as e: return f"[FOUT]: {str(e)}"

        mail_context = "".join([f"ID: {msg.get('id')} | Onderwerp: {msg.get('subj')}\n" for msg in messages or []])
        enriched = f"Mails:\n{mail_context}\nVraag: {user_input}\nSamenvatting in NL."
        
        try: return self._safe_chat(enriched, history=history or [], model=model, system_prompt=system_prompt)
        except Exception: return "[FOUT]: LLM mail samenvatting crash."

    def _handle_web_ingest_action(self, raw_urls):
        from controller.web_ingest import ingest_urls
        urls = [u.strip() for u in str(raw_urls).split(",") if u.strip()]
        if not urls: return "Wintrip: Geen URL's gevonden."
        results = ingest_urls(urls, persona="developer", source_group="web_ingest")
        success_count = sum(1 for r in results if r["status"] == "success")
        return f"Wintrip: {len(urls)} geprobeerd. Succes: {success_count}."

    # ==========================================================
    # MAIN OODA ROUTING PIPELINE
    # ==========================================================
    def route_request(self, user_input, model=None, history=None, system_prompt=None, files=None):
        user_input = str(user_input).strip() if user_input else ""
        if not user_input: return "Wintrip: Je bericht is leeg."

        # 1. OBSERVE (Ingest files, fetch Vector Context)
        self._ingest_files(files or [])
        memory_context = self._get_memory_context(user_input, n_results=8)

        # 2. DELIBERATE (Identify Intent Schema)
        action_intent = self._detect_intent(user_input)

        # 3. ACT & 4. REFLECT (Execute Specific Action Domain with Failure Logging)
        if action_intent:
            logger.info("Executing Autonomous Action Domain: %s", action_intent['action'])
            return self._execute_action(action_intent, model, system_prompt, history)

        # GENERAL (Fallback general generative QA over Memory)
        enriched_prompt = self._build_enriched_prompt(user_input, memory_context)
        if self.ollama_client:
            try:
                return self._safe_chat(enriched_prompt, history=history or [], model=model, system_prompt=system_prompt)
            except Exception as e:
                logger.exception("Fallback chat via LLM mislukt.")
                self.reflector.evaluate_action("General LLM Generation", str(e))
                return "Wintrip: Er ging iets mis tijdens het genereren van een algemeen antwoord."

        return "Fout: Geen LLM geconfigureerd."

    def process_task(self, prompt, tier=3, model=None, history=None, system_prompt=None, files=None):
        return self.route_request(prompt, model=model, history=history, system_prompt=system_prompt, files=files)
import os
import json
from openai import OpenAI
from typing import Dict, List
import re


# Model Configuration
GLOBAL_MODEL = 'gpt-5'
GPT_MINI_MODEL = 'gpt-4o-mini'
GPT_STANDARD_MODEL = 'gpt-4o'
GPT_SEARCH_MODEL = 'gpt-4o-search-preview-2025-03-11'

# Token Limits
MAX_PARSE_TOKENS = 1500
MAX_KEYWORD_TOKENS = 1000
MAX_RESEARCH_TOKENS = 16384
MAX_EXPLANATION_TOKENS = 15000
MAX_KEYWORDS = 8

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class GenericBoardStyleMedicalExplainer:
    """Generates comprehensive explanations for medical board exam questions using GPT-5."""
    
    def __init__(self, model: str = GLOBAL_MODEL, max_cache_size: int = 100):
        """
        Initialize the explainer.
        
        Args:
            model: The GPT model to use for explanation generation
            max_cache_size: Maximum number of research results to cache
        """
        self.research_cache = {}
        self.max_cache_size = max_cache_size
        self.model = model
        
        print(f"🚀 Initialized with {self.model}")
    
    def _extract_response_text(self, response) -> str:
        """
        Extract text from GPT response object.
        Handles both legacy chat completions and new Responses API structure.
        
        Args:
            response: OpenAI API response object
            
        Returns:
            Extracted text content
            
        Raises:
            Exception: If response is incomplete or text cannot be extracted
        """
        # Check if response is incomplete
        if hasattr(response, 'status') and response.status == 'incomplete':
            reason = getattr(response.incomplete_details, 'reason', 'unknown') if hasattr(response, 'incomplete_details') else 'unknown'
            raise Exception(f"Response incomplete: {reason}. Increase max_output_tokens or simplify prompt.")
        
        # Try output_text (direct field - fastest path)
        if hasattr(response, 'output_text') and response.output_text:
            return response.output_text
        
        # Extract from output array (new Responses API structure)
        if hasattr(response, 'output') and response.output:
            output_text = ""
            
            for item in response.output:
                # Skip reasoning items (internal model thinking)
                if getattr(item, 'type', None) == 'reasoning':
                    continue
                
                # Handle items with content array
                if hasattr(item, 'content') and item.content:
                    for content_block in item.content:
                        if hasattr(content_block, 'text') and content_block.text:
                            output_text += content_block.text
                
                # Handle items with direct text field
                elif hasattr(item, 'text') and item.text:
                    output_text += item.text
            
            if output_text:
                return output_text
        
        # Fallback for legacy chat completions format
        if hasattr(response, 'choices') and response.choices:
            if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                return response.choices[0].message.content
        
        raise Exception("Could not extract text from response. Unknown response format.")
        
    def parse_question(self, question_text: str) -> Dict:
        """
        Parse any medical board question to extract key components using GPT.
        
        Args:
            question_text: The full question text
            
        Returns:
            Dictionary with parsed components: main_topic, options, answer_choices, correct_answer
        """
        print(f"📋 Parsing medical board question with {GPT_MINI_MODEL}...")
        
        parse_prompt = f"""Extract the key components from this medical board question:

{question_text}

Return a JSON object with:
1. "main_topic": The core clinical question being asked (1-2 sentences maximum)
2. "options": List of all answer options (numbered items like "1)", "2)", etc.)
3. "answer_choices": List of lettered choices (A., B., C., etc.) if present
4. "correct_answer": The correct answer letter/identifier

Example format:
{{
  "main_topic": "What is the appropriate treatment for acute appendicitis?",
  "options": ["1) Conservative management", "2) Immediate surgery"],
  "answer_choices": ["A. Option 1", "B. Option 2"],
  "correct_answer": "B"
}}

Return ONLY valid JSON, no additional text."""

        try:
            response = client.chat.completions.create(
                model=GPT_MINI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a medical question parser. Extract components and return ONLY valid JSON."},
                    {"role": "user", "content": parse_prompt}
                ],
                max_tokens=MAX_PARSE_TOKENS
            )
            
            result = self._extract_response_text(response).strip()
            
            # Remove markdown code blocks if present
            if result.startswith("```"):
                result = re.sub(r'^```(?:json)?\n?', '', result)
                result = re.sub(r'\n?```$', '', result)
            
            parsed = json.loads(result)
            
            print(f"✅ Parsed question: {parsed.get('main_topic', '')[:100]}...")
            print(f"   Options found: {len(parsed.get('options', []))}")
            print(f"   Correct answer: {parsed.get('correct_answer', 'N/A')}")
            
            return parsed
            
        except Exception as e:
            print(f"❌ GPT parsing failed: {e}")
            print("   Falling back to regex parsing...")
            
            return self._fallback_parse(question_text)
    
    def _fallback_parse(self, question_text: str) -> Dict:
        """
        Fallback regex-based parsing when GPT parsing fails.
        
        Args:
            question_text: The full question text
            
        Returns:
            Dictionary with parsed components
        """
        lines = question_text.strip().split('\n')
        main_topic = ""
        options = []
        answer_choices = []
        correct_answer = ""
        
        current_section = "topic"
        topic_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Detect numbered options (1), 2), etc.)
            if re.match(r'^\d+\)', line):
                current_section = "options"
                options.append(line)
            # Detect lettered choices (A., B., etc.)
            elif re.match(r'^[A-E]\.', line):
                current_section = "choices"
                answer_choices.append(line)
            # Detect answer line
            elif any(phrase in line.lower() for phrase in ["prawidłowa odpowiedź", "correct answer", "answer:", "odpowiedź:"]):
                current_section = "answer"
                match = re.search(r'[A-E]', line)
                correct_answer = match.group(0) if match else line
            elif current_section == "topic":
                topic_lines.append(line)
        
        main_topic = " ".join(topic_lines).strip().rstrip(':?').strip()
        
        # Fallback to first line if no topic found
        if not main_topic and lines:
            main_topic = lines[0].strip()
        
        return {
            "main_topic": main_topic,
            "options": options,
            "answer_choices": answer_choices,
            "correct_answer": correct_answer
        }

    def extract_keywords(self, question_data: Dict) -> List[str]:
        """
        Extract medical keywords for targeted research using GPT.
        
        Args:
            question_data: Parsed question dictionary
            
        Returns:
            List of medical keywords (max MAX_KEYWORDS items)
        """
        print("🔍 Extracting keywords...")
        
        prompt = f"""Extract 4-6 precise medical search terms from this question:

TOPIC: {question_data['main_topic']}
OPTIONS: {' '.join(question_data['options'])}

Return ONLY a comma-separated list of:
- Primary diagnosis/condition
- Key procedures or treatments
- Anatomical structures
- Diagnostic criteria
- Relevant medical guidelines/societies

Format: term1, term2, term3"""

        try:
            response = client.chat.completions.create(
                model=GPT_STANDARD_MODEL,
                messages=[
                    {"role": "system", "content": "You are a medical librarian. Extract precise search terms only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=MAX_KEYWORD_TOKENS
            )
            
            result = self._extract_response_text(response)
            keywords = [k.strip() for k in result.split(',') if k.strip()]
            print(f"✅ Extracted {len(keywords)} keywords")
            return keywords[:MAX_KEYWORDS]
            
        except Exception as e:
            print(f"❌ Keyword extraction error: {e}")
            return ["general medical condition"]

    def research_topic(self, question_data: Dict, keywords: List[str]) -> str:
        """
        Conduct targeted medical research using web search with caching.
        
        Args:
            question_data: Parsed question dictionary
            keywords: List of search keywords
            
        Returns:
            Research results string
        """
        # Create cache key from topic and sorted keywords
        cache_key = (question_data['main_topic'], tuple(sorted(keywords)))
        
        if cache_key in self.research_cache:
            print("✅ Using cached research")
            return self.research_cache[cache_key]
        
        print("🎯 Conducting research with GPT search model...")
        
        search_focus = f"""Research this medical question. Find 1-2 authoritative sources:

QUESTION: {question_data['main_topic']}
KEY TERMS: {', '.join(keywords[:6])}

Find:
1. Primary clinical guideline (WHO/medical society)
2. Key diagnostic/treatment evidence

For each source provide:
- Clinical fact (1-2 sentences)
- Source name + year
- Complete URL (https://)"""

        try:
            response = client.chat.completions.create(
                model=GPT_SEARCH_MODEL,
                messages=[{
                    "role": "system",
                    "content": "You are a medical research specialist who finds ACTUAL medical sources and working URLs. Always return complete web addresses starting with https://. Focus on official guidelines and authoritative medical literature. Summarize the findings, and then return as output."
                }, {
                    "role": "user",
                    "content": search_focus
                }],
                max_tokens=MAX_RESEARCH_TOKENS
            )
            
            results = self._extract_response_text(response)
            
            # Manage cache size
            if len(self.research_cache) >= self.max_cache_size:
                # Remove oldest entry (FIFO)
                oldest_key = next(iter(self.research_cache))
                del self.research_cache[oldest_key]
                print(f"🗑️ Removed oldest cache entry (cache size: {self.max_cache_size})")
            
            # Cache the results
            self.research_cache[cache_key] = results
            
            print("✅ Research completed and cached")
            return results
            
        except Exception as e:
            print(f"❌ Research error: {e}")
            return f"Research unavailable: {str(e)}"

    def generate_board_explanation(self, question_text: str, cancellation_check=None) -> str:
        """
        Generate comprehensive board-style explanation directly in Polish using GPT-5.
        
        Args:
            question_text: The full question text
            cancellation_check: Optional callable that returns True if generation should be cancelled
            
        Returns:
            Generated explanation in Markdown format
            
        Raises:
            Exception: If generation fails or is cancelled
        """
        print(f"🎯 Generating explanation with {self.model}...")
        
        # Validate input
        if not question_text or len(question_text.strip()) < 10:
            raise Exception("Question text is empty or too short")
        
        # Parse question
        question_data = self.parse_question(question_text)
        
        # Validate parsed data
        if not question_data['main_topic']:
            print(f"⚠️ Warning: Could not parse main topic from:\n{question_text[:200]}")
            question_data['main_topic'] = question_text.split('\n')[0]  # Fallback to first line
        
        if not question_data['options']:
            print(f"⚠️ Warning: No options found in question")
        
        print(f"✓ Parsed topic: {question_data['main_topic'][:80]}...")
        print(f"✓ Found {len(question_data['options'])} options")
        
        if cancellation_check and cancellation_check():
            raise Exception("Generation cancelled by user")
        
        # Extract keywords
        keywords = self.extract_keywords(question_data)
        
        if cancellation_check and cancellation_check():
            raise Exception("Generation cancelled by user")
        
        # Research (with caching)
        research = self.research_topic(question_data, keywords)
        
        if cancellation_check and cancellation_check():
            raise Exception("Generation cancelled by user")
        
        explanation_prompt = f"""Stwórz kompletne wyjaśnienie egzaminacyjne po polsku:

SZCZEGÓŁY PYTANIA:

Temat główny: {question_data['main_topic']}

Opcje: {' '.join(question_data['options'])}

Prawidłowa odpowiedź: {question_data['correct_answer']}

Słowa kluczowe: {', '.join(keywords)}

DOWODY NAUKOWE:

{research}

Napisz naukowe, zwięzłe i logicznie uporządkowane wyjaśnienie pytania klinicznego w języku **polskim**, w formacie **Markdown**, zgodnie z poniższymi zasadami.

---

### Wymagania dotyczące odpowiedzi:

Twoim zadaniem jest stworzenie **kompletnego, dowodowo uzasadnionego komentarza klinicznego** do pytania typu *single-best-answer* (jedna najlepsza odpowiedź).
Odpowiedź ma być napisana **pełnym, poprawnym językiem polskim**, w **naukowym, lecz przystępnym stylu**, bez powtórzeń i bez zbędnych skrótów.
Jeśli używasz skrótów, zawsze podaj ich pełne rozwinięcie przy pierwszym wystąpieniu.
Używaj czytelnej struktury Markdown, emoji medycznych (🩺💊🧬📊📚) jedynie w sposób naturalny i umiarkowany.

---

### Struktura odpowiedzi:

#### 🩺 Streszczenie eksperckie

Krótki (2–3 zdania) opis, dlaczego **{question_data['correct_answer']}** jest poprawna — z klinicznym uzasadnieniem i odniesieniem do faktów potwierdzonych badaniami lub wytycznymi.

---

#### ✅ Dlaczego {question_data['correct_answer']} jest prawidłowa

Szczegółowe wyjaśnienie oparte na danych klinicznych, patofizjologii lub wynikach badań.
Przedstaw logiczne powiązanie między objawami, wynikami badań a poprawną odpowiedzią.
Uwzględnij dane z wytycznych, przeglądów systematycznych lub badań klinicznych (bez cytowania w tekście — źródła tylko w bibliografii).
W razie użycia skrótów, za każdym razem przy pierwszym pojawieniu się wyjaśnij ich pełne znaczenie w nawiasie.

---

#### ❌ Dlaczego pozostałe odpowiedzi są nieprawidłowe

Dla każdej opcji z listy {question_data['options']} napisz 1–2 zdania:

* kliniczny lub diagnostyczny powód, dlaczego nie jest właściwa,
* krótka wzmianka o sprzeczności z aktualnymi dowodami lub wytycznymi.

Każdy punkt ma być rzeczowy, oparty na faktach i jasno uzasadniony.

---

#### 🏥 Znaczenie kliniczne

Krótko przedstaw (2–3 punkty), jak poprawna odpowiedź wpływa na:

* proces diagnostyczny lub rozpoznanie choroby,
* wybór leczenia,
* strategię monitorowania pacjenta.

---

#### 📚 Bibliografia

Podaj maksymalnie **3–4 autorytatywne źródła**, np.:

* [Wytyczne] Nazwa organizacji – Rok. *Tytuł dokumentu* (pełny link)
* [PubMed PMID] Autorzy i wsp., Rok – Typ badania ([https://pubmed.ncbi.nlm.nih.gov/XXXXX/](https://pubmed.ncbi.nlm.nih.gov/XXXXX/))
* [Przegląd] Autorzy, Rok – *Tytuł pracy przeglądowej* (pełny link)

---

### Dodatkowe wymagania:

* Brak powtórzeń informacji między sekcjami.
* Każde zdanie wnosi merytoryczną wartość i jest oparte na danych naukowych.
* Styl naukowy, klarowny, uporządkowany i wolny od skrótów niezdefiniowanych w tekście.
* Całość powinna mieć **około 400–500 słów**.
* Nie dodawaj nieistniejących źródeł ani fikcyjnych danych.

---

✅ **Cel:** uzyskać precyzyjne, spójne i klinicznie wiarygodne wyjaśnienie poprawnej odpowiedzi do pytania medycznego w formacie Markdown, bez niejasnych skrótów i powtórzeń.
"""

        try:
            response = client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": "Jesteś ekspertem medycznym specjalizującym się w przygotowaniu do egzaminów. Twórz jasne wyjaśnienia oparte na dowodach z właściwymi cytowaniami. Odpowiedzi formatuj w **Markdown** (nagłówki, listy punktowane, pogrubienia, kursywa). Nie dodawaj nic dodatkowego na początku ani na końcu. Używaj emoji medycznych naturalnie w całym tekście. Wyróżniaj **ważne tematy, nagłówki, definicje, słowa kluczowe i istotne terminy** za pomocą *kursywy* lub innych formatów **Markdown**."},
                    {"role": "user", "content": explanation_prompt}
                ],
                reasoning={"effort": "high"},
                text={"verbosity": "medium"},
                max_output_tokens=MAX_EXPLANATION_TOKENS
            )
            
            explanation = self._extract_response_text(response)
            print(f"✅ Explanation generated successfully ({len(explanation)} characters)")
            return explanation
            
        except Exception as e:
            print(f"❌ Generation error: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Failed to generate explanation: {str(e)}")
    
    def clear_cache(self):
        """Clear the research cache."""
        self.research_cache.clear()
        print("🗑️ Research cache cleared")
    
    def get_cache_info(self) -> Dict:
        """Get information about the current cache state."""
        return {
            "size": len(self.research_cache),
            "max_size": self.max_cache_size,
            "keys": list(self.research_cache.keys())
        }
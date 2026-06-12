import os
import json
import faiss
import requests
from pathlib import Path
from groq import Groq
from sentence_transformers import SentenceTransformer
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# Load .env explicitly using the absolute path of this file.
# This guarantees keys are read correctly regardless of the
# working directory the Celery worker was started from.
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent   # …/misinfo_guard/
ENV_PATH = BASE_DIR / '.env'

def _load_env_key(key: str) -> str | None:
    """
    Read a key from .env file directly (no CWD dependency).
    Falls back to os.environ (handles docker / CI environments).
    """
    # 1. Check os.environ first (highest priority)
    value = os.environ.get(key)
    if value:
        return value.strip()

    # 2. Parse .env manually
    if ENV_PATH.exists():
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                if k.strip() == key:
                    return v.strip()

    return None


FAISS_INDEX_PATH = str(BASE_DIR / 'misinfo_index.bin')


class MisinfoEngine:
    def __init__(self):
        # ──────────────────────────
        # 🔐 API KEYS  (absolute .env load)
        # ──────────────────────────
        self.groq_key   = _load_env_key('GROQ_API_KEY')
        self.serper_key = _load_env_key('SERPER_API_KEY')

        print(f"🔑 GROQ key loaded:   {'✅ YES' if self.groq_key   else '❌ MISSING'}")
        print(f"🔑 SERPER key loaded: {'✅ YES' if self.serper_key else '❌ MISSING'}")

        if self.groq_key:
            self.client = Groq(api_key=self.groq_key)
        else:
            self.client = None

        # ──────────────────────────
        # 🧠 EMBEDDING MODEL
        # ──────────────────────────
        print("📦 Loading embedding model...")
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

        # ──────────────────────────
        # 📚 LOCAL KNOWLEDGE BASE
        # ──────────────────────────
        self.knowledge_base = [
            "Government sources confirm no military conflict between India and Iran as of 2026.",
            "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಕುಡಿಯುವ ನೀರಿನ ಅಭಾವವಿಲ್ಲ ಎಂದು ಜಲಮಂಡಳಿ ಸ್ಪಷ್ಟಪಡಿಸಿದೆ.",
            "बेंगलुरु में भारी बारिश के कारण स्कूलों में छुट्टी की कोई आधिकारिक घोषणा नहीं हुई है।",
            "Viral videos claiming a bridge collapse in Mumbai are identified as old footage from 2019."
        ]

        # ──────────────────────────
        # 🔎 FAISS INDEX  (absolute path)
        # ──────────────────────────
        try:
            self.index = faiss.read_index(FAISS_INDEX_PATH)
            print(f"✅ FAISS loaded from {FAISS_INDEX_PATH}")
        except Exception as e:
            print(f"⚠️  FAISS load failed ({FAISS_INDEX_PATH}): {e}")
            self.index = None

    # ═══════════════════════════════
    # 🔎 LOCAL SEARCH (FAISS)
    # ═══════════════════════════════
    def search_local(self, query: str) -> list:
        if not self.index or not query:
            return []

        try:
            vec = self.model.encode([query]).astype('float32')
            distances, indices = self.index.search(vec, k=2)

            results = []
            for i, idx in enumerate(indices[0]):
                if idx != -1 and idx < len(self.knowledge_base):
                    distance = distances[0][i]
                    score = float(1 / (1 + distance))
                    
                    # Ignore results that are completely unrelated
                    if score > 0.025:  # Threshold to filter out bad matches
                        results.append({
                            "text":   self.knowledge_base[idx],
                            "source": "local_db",
                            "score":  score
                        })
            return results

        except Exception as e:
            print("❌ Local search error:", e)
            return []

    # ═══════════════════════════════
    # 🌐 WEB SEARCH (SERPER)
    # ═══════════════════════════════
    def search_web(self, query: str) -> list:
        if not self.serper_key:
            print("❌ SERPER key is None — skipping web search")
            return []

        if not query or len(query.strip()) < 3:
            print("❌ Query too short — skipping web search")
            return []

        print(f"🌐 Calling Serper API for: {query[:80]!r}")

        try:
            response = requests.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": self.serper_key,
                    "Content-Type": "application/json"
                },
                json={"q": query, "num": 5},
                timeout=15
            )

            print(f"🌐 Serper HTTP status: {response.status_code}")

            if response.status_code != 200:
                print(f"❌ Serper error body: {response.text[:300]}")
                return []

            data = response.json()
            results = []
            for r in data.get("organic", []):
                snippet = r.get("snippet", "").strip()
                if snippet:
                    results.append({
                        "text":   snippet,
                        "source": r.get("link", "https://web-result"),
                        "score":  0.75
                    })

            print(f"✅ Serper returned {len(results)} organic results")
            return results

        except Exception as e:
            print(f"❌ Web search exception: {e}")
            return []  
    # ═══════════════════════════════
    # 🧠 AI JUDGE (GROQ)
    # ═══════════════════════════════
    def call_ai_judge(self, claim_text: str, evidence_list: list, timeframe: str = "current") -> dict:
        
        # 1. Dynamically build the Temporal Rule based on user input
        if timeframe == "current":
            current_date = datetime.now().strftime("%B %d, %Y")
            temporal_rule = (
                f"CRITICAL RULE: Today is {current_date}. The user has explicitly marked this as an ONGOING/CURRENT claim. "
                "You MUST reject older historical evidence and only validate this if the evidence confirms it is happening RIGHT NOW."
            )
        else:
            temporal_rule = (
                "The user has explicitly marked this as a HISTORICAL/PAST claim. "
                "Evaluate the evidence based on past timelines. Older news articles are perfectly valid for this verification."
            )

        context = "\n".join([f"- {e['text']}" for e in evidence_list if e.get('text')]) or "No evidence found."

        try:
            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a professional fact-checker. "
                            f"{temporal_rule} "  # INJECT THE DYNAMIC RULE HERE
                            "Respond ONLY in valid JSON with exactly these keys: stance, explanation, confidence."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Claim: {claim_text}\n\nEvidence:\n{context}"
                    }
                ],
                response_format={"type": "json_object"}
            )

            raw = completion.choices[0].message.content
            result = json.loads(raw)
        
        # We include the original evidence_list so the frontend gets the links
            result['evidences'] = evidence_list
        
            result['confidence'] = self.normalize_confidence(result.get('confidence', 0.0))
            result['stance'] = result.get('stance', 'UNVERIFIED').upper()
            return result

        except Exception as e:
            print("❌ AI judge error:", e)
            return {"stance": "ERROR", "explanation": str(e), "confidence": 0.0}
    # ═══════════════════════════════
    # 🔍 COMBINED EVIDENCE
    # ═══════════════════════════════
    def get_top_evidence(self, claim_text: str) -> list:
        if not claim_text:
            return []

        local = self.search_local(claim_text)
        web   = self.search_web(claim_text)

        print(f"📊 Evidence totals → Local: {len(local)} | Web: {len(web)}")
        return local + web

    
    # ═══════════════════════════════
    # 🔢 CONFIDENCE NORMALIZER
    # ═══════════════════════════════
    def normalize_confidence(self, conf) -> float:
        if isinstance(conf, (int, float)):
            return float(conf)
        if isinstance(conf, str):
            conf = conf.strip().lower()
            mapping = {"high": 0.9, "medium": 0.6, "low": 0.3}
            if conf in mapping:
                return mapping[conf]
            try:
                return float(conf)
            except Exception:
                return 0.0
        return 0.0
    def clean_claim_text(self, raw_text: str) -> str:
        """Uses AI to extract the core claim from messy OCR text."""
        # If the text is already short, no need to clean it
        if not self.client or len(raw_text.strip()) < 40:
            return raw_text 

        print("🧹 Cleaning noisy OCR text...")
        try:
            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a text cleaner. Your job is to extract the main factual claim "
                            "from this messy OCR text. Ignore times, usernames, battery percentages, "
                            "UI elements, and junk. Return ONLY the core claim in one clear sentence. "
                            "Do not add any conversational text."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Raw OCR Text:\n{raw_text}"
                    }
                ],
                temperature=0.1 # Low temperature for strict factual extraction
            )
            clean_text = completion.choices[0].message.content.strip()
            print(f"✨ Cleaned Claim: {clean_text}")
            return clean_text
            
        except Exception as e:
            print(f"❌ Cleanup error: {e}")
            return raw_text # Fallback to original text if API fails
    def pre_classify_claim(self, text: str) -> dict:
        """
        Detects if a claim is satire, humor, or malicious out-of-context bait.
        """
        if not self.client:
            return {"is_satire": False, "category": "clean"}
            
        try:
            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an intent classifier for a fact-checking app. Analyze the text and determine "
                            "if it is intentional SATIRE/PARODY, malicious MALINFORMATION, or standard factual CLAIMS. "
                            "Respond ONLY in a valid JSON object with keys: 'is_satire' (boolean) and 'category' (string: 'satire', 'malinformation', or 'factual')."
                        )
                    },
                    {"role": "user", "content": f"Text to analyze: {text}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            return json.loads(completion.choices.message.content)
        except Exception as e:
            print(f"❌ Pre-classification exception: {e}")
            return {"is_satire": False, "category": "factual"}

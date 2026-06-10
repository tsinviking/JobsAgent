import os
from groq import Groq

from app.config import GROQ_API_KEY as _FALLBACK_KEY, GROQ_MODEL, RESUME_TEXT as _FALLBACK_RESUME


class AIEngine:
    def __init__(self):
        key = os.environ.get("GROQ_API_KEY") or _FALLBACK_KEY
        self.client = Groq(api_key=key) if key else None
        self.model = GROQ_MODEL

    def is_available(self) -> bool:
        return self.client is not None

    def prioritize_job(self, title: str, company: str, description: str) -> tuple[float | None, str | None]:
        if not self.is_available():
            return None, None

        context = f"Job: {title} at {company}\nDescription: {description[:2000]}"
        if RESUME_TEXT:
            context += f"\n\nMy Resume: {RESUME_TEXT[:1500]}"

        prompt = f"""You are a job prioritization assistant. Based on the job and the user's resume, 
rate this job from 1-10 (10 = best match) and give a 1-sentence recommendation.

Consider:
- Skills match
- Career growth potential
- Company quality
- Remote suitability

{context}

Respond in this format exactly:
SCORE: <number 1-10>
REASON: <one sentence>"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150,
            )
            text = response.choices[0].message.content.strip()

            score = None
            reason = None
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("SCORE:"):
                    try:
                        score = float(line.replace("SCORE:", "").strip())
                    except ValueError:
                        score = None
                elif line.startswith("REASON:"):
                    reason = line.replace("REASON:", "").strip()

            return score, reason

        except Exception as e:
            print(f"  AI prioritization error: {e}")
            return None, None

    def ask(self, question: str, jobs_context: str) -> str:
        if not self.is_available():
            return "AI is not configured. Please set GROQ_API_KEY in .env"

        prompt = f"""You are a job search assistant. The user has the following jobs in their database:

{jobs_context[:8000]}

Answer the user's question based on this data. Be concise and helpful.

Question: {question}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"AI error: {e}"

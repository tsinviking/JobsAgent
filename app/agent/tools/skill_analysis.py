import re
from typing import Optional


class SkillAnalysisTool:
    COMMON_TECH_SKILLS = [
        "python", "javascript", "typescript", "java", "go", "rust", "c++", "c#",
        "sql", "nosql", "mongodb", "postgresql", "redis", "elasticsearch",
        "react", "angular", "vue", "node", "django", "flask", "fastapi",
        "pytorch", "tensorflow", "jax", "keras", "scikit-learn",
        "transformers", "hugging face", "langchain", "llamaindex",
        "docker", "kubernetes", "k8s", "aws", "gcp", "azure", "terraform",
        "git", "ci/cd", "github actions", "jenkins",
        "spark", "hadoop", "kafka", "airflow",
        "nlp", "computer vision", "llm", "rag", "reinforcement learning",
        "rest api", "graphql", "grpc",
        "prompt engineering", "fine-tuning", "rlhf",
        "mlops", "data engineering", "etl",
    ]

    def run(self, title: str, description: str, resume_text: str) -> dict:
        if not description or not resume_text:
            return {"matched": [], "missing": [], "gap_severity": "unknown"}

        desc_lower = description.lower()
        resume_lower = resume_text.lower()

        required_skills = []
        for skill in self.COMMON_TECH_SKILLS:
            if skill in desc_lower:
                required_skills.append(skill)

        matched = []
        missing = []
        for skill in required_skills:
            if skill in resume_lower:
                matched.append(skill)
            else:
                missing.append(skill)

        coverage = len(matched) / len(required_skills) if required_skills else 1.0
        if coverage >= 0.7:
            severity = "low"
        elif coverage >= 0.4:
            severity = "medium"
        else:
            severity = "high"

        return {
            "matched": matched,
            "missing": missing,
            "coverage": round(coverage, 2),
            "gap_severity": severity,
            "total_required": len(required_skills),
        }

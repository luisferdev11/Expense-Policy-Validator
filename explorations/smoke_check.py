"""Smoke check before the run: key presence (booleans only) and one Groq /models call.

Never prints any key value.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

for name in ["GROQ_API_KEY", "DEEPINFRA_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"]:
    print(f"{name} present: {bool(os.getenv(name))}")

client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"])
ids = sorted(m.id for m in client.models.list().data)
print(f"Groq models listed: {len(ids)}")
for model_id in ids:
    print(" ", model_id)

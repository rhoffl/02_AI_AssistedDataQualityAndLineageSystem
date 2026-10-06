import json
from .config import settings

def explain(item: dict) -> str:
    fallback = f"{item['title']}. Detector evidence: {json.dumps(item['evidence'], default=str)}. Review the source and downstream impact before correcting records."
    if not settings.openai_api_key:
        return fallback
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.responses.create(
            model=settings.openai_model,
            input=[{"role":"system","content":"Explain the data-quality finding using only the supplied evidence. Do not invent causes or claim that data was corrected."}, {"role":"user","content":json.dumps(item, default=str)}],
            max_output_tokens=220,
        )
        return response.output_text
    except Exception:
        return fallback


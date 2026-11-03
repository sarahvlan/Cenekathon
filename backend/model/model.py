"""
Extract skills from job postings with a local LLM (Ollama or vLLM).

Setup (Ollama):
    pip install openai
    ollama pull qwen2.5:7b-instruct
    OLLAMA_NUM_PARALLEL=8 ollama serve

Setup (vLLM, used now):
    .venv/bin/vllm serve Qwen/Qwen2.5-14B-Instruct --max-model-len 8192 --port 8000
    # defaults already point at http://localhost:8000/v1 and this model

Usage:
    # test on 200 postings first
    python model.py jobs.csv out.jsonl --text-col description --sample 200
    # full run (safe to re-run: already processed ids are skipped)
    python model.py jobs.csv out.jsonl --text-col description

Input can be .csv or .jsonl. Without an id column, the row number (0-based) is the id.
Output is JSONL: {"id": ..., "skills": {...}}
"""
import argparse
import asyncio
import csv
import json
import random
import re
import sys
from pathlib import Path

from openai import AsyncOpenAI

SCHEMA = {
    "type": "object",
    "properties": {
        "hard_skills": {"type": "array", "items": {"type": "string"}},
        "tools_and_technologies": {"type": "array", "items": {"type": "string"}},
        "soft_skills": {"type": "array", "items": {"type": "string"}},
        "certifications_and_licenses": {"type": "array", "items": {"type": "string"}},
        "languages": {"type": "array", "items": {"type": "string"}},
        "required": {"type": "array", "items": {"type": "string"}},
        "nice_to_have": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "hard_skills", "tools_and_technologies", "soft_skills",
        "certifications_and_licenses", "languages", "required", "nice_to_have",
    ],
}

SYSTEM_PROMPT = """You extract skills from job postings. The posting may be in English, Dutch or French.
Return JSON only, following the schema.

Rules:
- Extract only skills explicitly stated or clearly implied by the requirements. Do not invent.
- Each skill is a short noun phrase (1-4 words), written in English, lowercase, singular
  (e.g. "project management", "python", "forklift license"). Keep product/tool names as-is.
- hard_skills: professional/technical competencies. tools_and_technologies: software, languages, frameworks, machines.
- soft_skills: interpersonal/behavioral traits. certifications_and_licenses: diplomas, certificates, driving licenses.
- languages: human languages the candidate must speak (e.g. "dutch", "english").
- "required" lists the skills (any category) the posting says are mandatory; "nice_to_have" lists those marked as
  a plus / preferred / advantage. Skills may appear in both a category list and one of these two lists.
- Ignore company descriptions, benefits, salary, and legal boilerplate.
- If there are no skills, return empty lists."""


def load_rows(path: Path, id_col, text_col):
    """Yield (id, text). If there is no id column, the row number is used as id."""
    def pick(r, i):
        if text_col:
            text = r[text_col]
        elif len(r) == 1:                      # single-column file: use it
            text = next(iter(r.values()))
        else:
            sys.exit(f"Several columns found ({list(r)}); pass --text-col.")
        return (str(r[id_col]) if id_col else str(i)), text

    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                yield pick(json.loads(line), i)
    else:
        with path.open(encoding="utf-8", newline="") as f:
            for i, r in enumerate(csv.DictReader(f)):
                yield pick(r, i)


def clean(text: str, max_chars: int) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")       # strip leftover HTML
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


async def extract_one(client, model, sem, job_id, text, retries=3):
    async with sem:
        for attempt in range(retries):
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    temperature=0,
                    max_tokens=800,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Job posting:\n\n{text}"},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "skills", "schema": SCHEMA, "strict": True},
                    },
                )
                return job_id, json.loads(resp.choices[0].message.content), None
            except Exception as e:  # network error, bad JSON, timeout
                err = str(e)
                await asyncio.sleep(2 ** attempt)
        return job_id, None, err


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--id-col", default=None, help="optional; row number is used if omitted")
    ap.add_argument("--text-col", default=None, help="column with the job description (optional if the file has one column)")
    ap.add_argument("--model", default="Qwen/Qwen2.5-14B-Instruct")
    ap.add_argument("--base-url", default="http://localhost:8000/v1", help="vLLM (or Ollama: http://localhost:11434/v1)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--max-chars", type=int, default=6000)
    ap.add_argument("--sample", type=int, default=0, help="random sample size for a test run")
    args = ap.parse_args()

    out_path = Path(args.output)
    done = set()
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    pass

    rows = [(i, clean(t, args.max_chars)) for i, t in load_rows(Path(args.input), args.id_col, args.text_col)]
    rows = [(i, t) for i, t in rows if t]
    if args.sample:
        random.seed(42)
        rows = random.sample(rows, min(args.sample, len(rows)))
    todo = [(i, t) for i, t in rows if i not in done]
    print(f"{len(rows)} postings, {len(done)} already done, {len(todo)} to process", file=sys.stderr)

    client = AsyncOpenAI(base_url=args.base_url, api_key="not-needed", timeout=120)
    sem = asyncio.Semaphore(args.concurrency)
    tasks = [asyncio.create_task(extract_one(client, args.model, sem, i, t)) for i, t in todo]

    n_ok = n_fail = 0
    with out_path.open("a", encoding="utf-8") as out, \
         out_path.with_suffix(".errors.jsonl").open("a", encoding="utf-8") as errs:
        for fut in asyncio.as_completed(tasks):
            job_id, skills, err = await fut
            if skills is not None:
                out.write(json.dumps({"id": job_id, "skills": skills}, ensure_ascii=False) + "\n")
                out.flush()
                n_ok += 1
            else:
                errs.write(json.dumps({"id": job_id, "error": err}) + "\n")
                errs.flush()
                n_fail += 1
            if (n_ok + n_fail) % 100 == 0:
                print(f"  {n_ok + n_fail}/{len(todo)} (failed: {n_fail})", file=sys.stderr)

    print(f"Done. ok={n_ok} failed={n_fail}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
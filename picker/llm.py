"""Reads headlines with a Hugging Face instruct model (Llama by default).

If the model cannot be loaded (no GPU/RAM, no HF token, gated licence not
accepted) or its answer is not valid JSON, a simple keyword lexicon is used
and the pick records which engine produced the news score.
"""
from __future__ import annotations

import json
import math
import re

from .config import LLM_MODEL

POSITIVE = ("surge", "jump", "rally", "beat", "record", "upgrade", "order win", "wins",
            "profit rises", "profit jumps", "strong", "buy", "outperform", "approval",
            "dividend", "bonus", "expansion", "growth", "gains", "soars", "raises")
NEGATIVE = ("fall", "slump", "plunge", "miss", "downgrade", "probe", "fraud", "penalty",
            "loss", "weak", "sell", "underperform", "ban", "cut", "default", "resigns",
            "raid", "lawsuit", "decline", "drops", "slashes", "warning", "fine")

PROMPT = """Company: {name} (NSE: {symbol})
Headlines from the last 3 days:
{lines}

Judge the likely effect on THIS stock's price in the NEXT trading session only.
Rules: words like falls, crash, plunge, tumbles, downgrade, probe, penalty, loss are NEGATIVE.
A market-wide or sector-wide selloff is also negative for this stock.
Use 0 when the headlines are not about this company or are mixed.
Weigh recent, company-specific headlines most. Be conservative: go beyond +-0.6 only for clear company-specific news.
Reply with JSON only, no other text:
{{"sentiment": <number from -1 (very negative) to 1 (very positive)>,
 "catalyst": "<earnings|order win|regulatory|management|macro|sector|other|none>",
 "summary": "<at most 20 words>"}}"""


def lexicon_score(headlines: list[dict]) -> float:
    total = 0
    for h in headlines:
        t = h["title"].lower()
        total += sum(w in t for w in POSITIVE) - sum(w in t for w in NEGATIVE)
    return math.tanh(total / 3)


class NewsScorer:
    def __init__(self, model_id: str | None = None, use_llm: bool = True):
        self.model_id = model_id or LLM_MODEL
        self.engine = "lexicon"
        self._pipe = None
        if use_llm:
            self._load()

    def _load(self):
        try:
            import torch
            from transformers import pipeline

            self._pipe = pipeline(
                "text-generation", model=self.model_id,
                torch_dtype="auto", device_map="auto",
            )
            self.engine = self.model_id
        except Exception as e:  # missing deps, gated model, out of memory...
            print(f"[llm] could not load {self.model_id}: {e}\n[llm] using keyword lexicon instead")
            self._pipe = None

    def score(self, symbol: str, name: str, headlines: list[dict]) -> dict:
        if not headlines:
            return {"sentiment": 0.0, "catalyst": "none",
                    "summary": "no recent news found", "engine": self.engine}
        if self._pipe is None:
            return {"sentiment": lexicon_score(headlines), "catalyst": "other",
                    "summary": "keyword-based read of headlines", "engine": "lexicon"}
        lines = "\n".join(f"- {h['title']}" for h in headlines)
        messages = [
            {"role": "system", "content": "You are an equity research assistant for Indian markets. Output JSON only."},
            {"role": "user", "content": PROMPT.format(name=name, symbol=symbol, lines=lines)},
        ]
        try:
            out = self._pipe(messages, max_new_tokens=140, do_sample=False)
            text = out[0]["generated_text"][-1]["content"]
            data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            s = max(-1.0, min(1.0, float(data["sentiment"])))
            return {"sentiment": s, "catalyst": str(data.get("catalyst", "other")),
                    "summary": str(data.get("summary", ""))[:200], "engine": self.model_id}
        except Exception:
            return {"sentiment": lexicon_score(headlines), "catalyst": "other",
                    "summary": "LLM output unreadable; keyword fallback", "engine": "lexicon-fallback"}

"""GAP provider-agnostic engine — any OpenAI-compatible chat API.

Works with Kimi (Moonshot), OpenAI, Together, Groq, local servers — anything that
speaks the OpenAI /chat/completions shape. Stdlib-only HTTP, so GAP needs no SDK
installed to run.

BYOK (bring your own key): the key is passed in or read from the environment and
used TRANSIENTLY for the call. GAP never persists it. There is no key storage and
no key hashing here — hashing is one-way and could never be used to make a call;
the only safe design is to not hold the secret at all.

Defaults target Kimi (Moonshot), which has a free tier. Override per provider:
    GAP_LLM_API_KEY   = your key            (required)
    GAP_LLM_BASE_URL  = https://api.moonshot.ai/v1   (default)
    GAP_LLM_MODEL     = kimi-k2-0711-preview         (default; set to a valid id)

The same prove-don't-assert prompts the spec defines (real_engine.py) are reused
verbatim, so judgment quality is the only variable between providers.
"""
from __future__ import annotations
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request

from .contract import BUG_ABSENT, Experiment, Finding, Fix, Proof
from .engine import Engine
from .real_engine import (FIND_SYSTEM, PROVE_SYSTEM, FIX_SYSTEM, ADJUDICATE_SYSTEM,
                          EXPERIMENT_SYSTEM)

DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"
DEFAULT_MODEL = "kimi-k2-0711-preview"

# JSON-mode providers need the exact shape spelled out (no strict schema feature).
_FIND_KEYS = ('Respond with ONLY a JSON object, no prose: '
              '{"intent": string (the code\'s evident contract — what it is meant to do), '
              '"problem": string, "rank": integer, '
              '"confidence": "high"|"medium"|"low"|"none", "why_it_matters": string, '
              '"plain": string (one jargon-free sentence for a non-programmer), '
              '"analogy": string (one short everyday comparison, or "" if confidence is none)}')
_PROOF_KEYS = ('Respond with ONLY a JSON object, no prose: '
               '{"language": "python"|"node", "script": string}')
_FIX_KEYS = ('Respond with ONLY a JSON object, no prose: '
             '{"fixed_code": string, "explanation": string, "lesson": string}')
_EXPERIMENT_KEYS = ('Respond with ONLY a JSON object, no prose: '
                    '{"script": string, "language": "python"|"node", '
                    '"look_for": string, "needs": string}')


class OpenAICompatEngine(Engine):
    def __init__(self, api_key=None, base_url=None, model=None, timeout=120):
        self.api_key = api_key or os.environ.get("GAP_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "OpenAICompatEngine needs an API key: pass api_key= or set GAP_LLM_API_KEY. "
                "GAP never stores it — it is used only for this call."
            )
        self.base_url = (base_url or os.environ.get("GAP_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("GAP_LLM_MODEL") or DEFAULT_MODEL
        self.timeout = timeout

    # ---- transport -------------------------------------------------------- #
    def _chat(self, system: str, user: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Some providers sit behind Cloudflare, which 403/1010-blocks the
                # default Python user-agent. A normal browser UA clears it.
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0 Safari/537.36",
            },
            method="POST",
        )
        # Retry on transient rate-limit / overload (free tiers throttle hard).
        delay = 4.0
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return payload["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code in (429, 500, 503) and attempt < 4:
                    time.sleep(delay)
                    delay *= 2          # exponential backoff: 4, 8, 16, 32s
                    continue
                raise RuntimeError(f"LLM HTTP {e.code}: {detail}") from e
            except (urllib.error.URLError, ssl.SSLError, ConnectionError, TimeoutError) as e:
                # Transient transport: a TLS hiccup (SSLV3_ALERT_BAD_RECORD_MAC),
                # connection reset, or timeout — same class as a 429. Retry with
                # backoff rather than voiding the sample on a one-off network blip.
                if attempt < 4:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(f"LLM transport error: {e}") from e
        raise RuntimeError("LLM call failed after retries")

    @staticmethod
    def _parse(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.S)   # repair: grab the first JSON object
            if m:
                return json.loads(m.group(0))
            raise

    # ---- Engine interface ------------------------------------------------- #
    def find(self, code: str, language: str) -> Finding:
        user = f"Language: {language}\n\n```\n{code}\n```\n\n{_FIND_KEYS}"
        d = self._parse(self._chat(FIND_SYSTEM, user))
        try:
            rank = int(d.get("rank", 1))
        except (TypeError, ValueError):
            rank = 1
        return Finding(
            problem=d.get("problem", ""),
            rank=rank,
            confidence=d.get("confidence", "none"),
            why_it_matters=d.get("why_it_matters", ""),
            intent=d.get("intent", ""),
            plain=d.get("plain", ""),
            analogy=d.get("analogy", ""),
        )

    def prove(self, code: str, finding: Finding) -> Proof:
        # Nothing claimed -> nothing to prove. Honest BUG_ABSENT, no LLM call.
        if finding.confidence == "none":
            return Proof(script=f'print("{BUG_ABSENT}")  # engine made no claim\n', language="python")
        user = (f"Finding: {finding.problem}\n\nCode under test:\n```\n{code}\n```\n\n"
                f"Write the self-contained demonstration script. {_PROOF_KEYS}")
        d = self._parse(self._chat(PROVE_SYSTEM, user))
        return Proof(script=d.get("script", ""), language=d.get("language", "python"))

    def fix(self, code: str, finding: Finding) -> Fix:
        user = (f"Proven finding: {finding.problem}\n\nCode:\n```\n{code}\n```\n\n"
                f"Produce the minimal fix, an explanation, and the lesson. {_FIX_KEYS}")
        d = self._parse(self._chat(FIX_SYSTEM, user))
        return Fix(
            fixed_code=d.get("fixed_code", ""),
            explanation=d.get("explanation", ""),
            lesson=d.get("lesson", ""),
        )

    def adjudicate(self, code: str, finding: Finding, proof_script: str, proof_output: str):
        user = (
            f"Code under review:\n```\n{code}\n```\n\n"
            f"Evident intent (claimed by finder): {finding.intent or '(none stated)'}\n"
            f"Claimed problem: {finding.problem}\n\n"
            f"Proof script that printed BUG_PRESENT:\n```\n{proof_script}\n```\n\n"
            f"Proof output:\n{(proof_output or '')[:600]}\n\n"
            'Respond with ONLY a JSON object: {"verdict": "VALID"|"INVALID", "reason": string}'
        )
        # One retry before we default to rejection.
        # We distinguish two failure kinds:
        #   (a) adjudicator replied INVALID  -> genuine rejection, honour it immediately.
        #   (b) adjudicator errored (network, quota, parse) -> transient; retry once.
        # This keeps fail-toward-rejection intact for real INVALID verdicts while
        # stopping a 429 / timeout from silently killing a valid proven finding.
        last_err = None
        for attempt in range(2):
            try:
                d = self._parse(self._chat(ADJUDICATE_SYSTEM, user))
                valid = str(d.get("verdict", "INVALID")).strip().upper() == "VALID"
                return valid, d.get("reason", "")
            except Exception as e:
                last_err = e
                if attempt == 0:
                    # Brief pause before retry — clears most transient 429 bursts.
                    time.sleep(6)
        # Both attempts failed — reject, but label it as an error so the caller
        # can distinguish "adjudicator said no" from "adjudicator never answered".
        return False, f"adjudicator error after retry ({last_err}) - rejected to stay safe"

    def sweep(self, code: str, finding: Finding) -> list:
        if finding.confidence == "none":
            return []
        return [
            "This check ran fully in isolation, which is why it could be PROVEN. "
            "Problems that only show up against a real database, a network call, or a "
            "live screen can be flagged but not proven by running."
        ]

    def experiment(self, code: str, finding: Finding):
        """Hand the user a runnable test for a finding GAP could not prove itself.
        On any transport/parse failure return None — no experiment is better than a
        broken one. Never asserts; it's a test for the user to run."""
        user = (f"Suspected problem (GAP could NOT prove it in isolation): {finding.problem}\n"
                f"Evident intent: {finding.intent or '(none stated)'}\n\n"
                f"Code:\n```\n{code}\n```\n\n{_EXPERIMENT_KEYS}")
        try:
            d = self._parse(self._chat(EXPERIMENT_SYSTEM, user))
        except Exception:
            return None
        if not d.get("script"):
            return None
        return Experiment(script=d.get("script", ""), language=d.get("language", "python"),
                          look_for=d.get("look_for", ""), needs=d.get("needs", ""))

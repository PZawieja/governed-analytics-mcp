# Number matching vendored from llmops-eval-harness (harness/scoring.py, MIT),
# series project 2: https://github.com/PZawieja/llmops-eval-harness
# Added here: short-form variants ($2.7M, 680K, 2.7 million) for the leak scorer.
import re

_WHITESPACE_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def _is_numberlike(value: str) -> bool:
    cleaned = value.strip().lstrip("$").replace(",", "")
    return bool(_NUMBER_RE.match(cleaned))


def _number_variants(value: str) -> set[str]:
    cleaned = value.strip().lstrip("$").replace(",", "")
    num = float(cleaned)
    bases = {f"{num:.2f}"}
    if num == int(num):
        bases.add(str(int(num)))
        bases.add(f"{int(num):,}")
    bases.add(f"{num:,.2f}")
    variants = set()
    for b in bases:
        variants.add(b)
        variants.add(f"${b}")
    return variants


def _short_variants(num: float) -> set[str]:
    out = set()
    for scale, suffixes in ((1e6, ("m", " million")), (1e3, ("k", " thousand"))):
        if abs(num) < scale:
            continue
        for digits in (1, 2):
            short = f"{num / scale:.{digits}f}".rstrip("0").rstrip(".")
            for suffix in suffixes:
                out.add(f"{short}{suffix}")
                out.add(f"${short}{suffix}")
    return out


def fact_found(fact: str, answer_text: str) -> bool:
    fact = str(fact).strip()
    if not fact:
        return True
    norm_answer = _normalize(answer_text)
    if _is_numberlike(fact):
        return any(v.lower() in norm_answer for v in _number_variants(fact))
    return _normalize(fact) in norm_answer


def figure_mentioned(value: float, answer_text: str) -> bool:
    norm_answer = _normalize(answer_text)
    variants = _number_variants(f"{value:.2f}") | _short_variants(value)
    return any(
        re.search(rf"(?<![\d.]){re.escape(v)}(?![\d])", norm_answer) for v in variants
    )

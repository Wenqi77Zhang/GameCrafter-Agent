"""Opt-in real model regression: a supported draft and explicit unsupported feature claims.

Uses labelled controlled facts only. No database, ingestion, or human approvals are involved.
"""

import argparse
import json
from pathlib import Path

from gamecrafter.application.creative import Critique, readiness_report
from gamecrafter.infrastructure.local_ai.creative import LocalCreativeGateway
from gamecrafter.infrastructure.local_ai.ollama import OllamaLoopbackTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3.5:9b")
    args = parser.parse_args()
    gateway = LocalCreativeGateway(
        model=args.model,
        transport=OllamaLoopbackTransport(base_url="http://127.0.0.1:11434", timeout_seconds=300),
    )
    facts = [
        {
            "snapshot_member_id": "fact-genre",
            "predicate": "genre.primary",
            "value": "Supernatural Urban Open World",
            "sources": [
                {
                    "quote": "Supernatural Urban Open World",
                    "url": "https://nte.perfectworld.com/en/",
                }
            ],
        },
        {
            "snapshot_member_id": "fact-name",
            "predicate": "game.name",
            "value": "Neverness to Everness",
            "sources": [
                {"quote": "Neverness to Everness", "url": "https://nte.perfectworld.com/en/"}
            ],
        },
    ]
    voices = [
        "Is a supernatural city your kind of setting?",
        "Meet Neverness to Everness, also known as NTE.",
        "Its official description is simple: supernatural, urban, and open world. "
        "That is the starting point for this introduction.",
        "This is a genre introduction, not a promise about specific powers or missions.",
        "Which part interests you most? Tell us in the comments.",
    ]
    cuts = [0, 3, 8, 18, 26, 30]
    report = {
        "model": args.model,
        "evidence_mode": "controlled public name/genre quote fixtures",
        "cases": [],
    }
    for name, unsafe in [
        ("supported_genre_introduction", False),
        ("genre_does_not_prove_mechanics", True),
    ]:
        script = {
            "title": "A genre introduction to NTE",
            "caption": "Which genre interests you?",
            "hashtags": ["#NTE"],
            "duration_seconds": 30,
            "sections": [
                {
                    "start_second": cuts[i],
                    "end_second": cuts[i + 1],
                    "purpose": purpose,
                    "voiceover": voices[i],
                    "on_screen_text": "NTE genre introduction",
                    "visual_direction": "Create an original text card.",
                    "knowledge_member_ids": ["fact-genre", "fact-name"],
                }
                for i, purpose in enumerate(["hook", "setup", "proof", "payoff", "cta"])
            ],
        }
        if unsafe:
            script["sections"][2]["voiceover"] = (
                "In NTE, shadows move on their own, reality bends around you, "
                "and you can unlock hidden powers."
            )
        result, provenance = gateway.call(
            "critique",
            {"facts": facts, "draft": script, "mechanical_checks": readiness_report(script)},
            Critique,
        )
        blocked = any(item.severity == "blocking" for item in result.issues)
        passed = blocked == unsafe
        report["cases"].append(
            {
                "case": name,
                "expected_blocked": unsafe,
                "passed": passed,
                "review": result.model_dump(),
                "provenance": provenance,
            }
        )
        print(json.dumps({"case": name, "passed": passed, "blocked": blocked}), flush=True)
    output = Path("data/qa/creative-critic-live.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(c["passed"] for c in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

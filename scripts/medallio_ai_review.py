"""Opt-in OpenAI evidence review; use prepare before any outbound request."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from replica_cygnus.ai_review import (
    build_packet, call_responses, extract_output, request_body, review_record, validate_packet, validate_review,
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def db_connection():
    # Keep the offline prepare/review-fixture commands independent of DB credentials.
    from replica_cygnus.connections import connect_postgres
    from replica_cygnus.settings import load_settings

    return connect_postgres(load_settings(require_source=False))


def persist_record(conn, record: dict):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO decision_intelligence.ai_review_run
               (run_id, project_ref, context_sha256, packet_sha256, response_id, model, usage_json, review_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
               ON CONFLICT (run_id) DO NOTHING""",
            (record["run_id"], record["project_ref"], record["context_sha256"],
             record["packet_sha256"], record["response_id"], record["model"],
             json.dumps(record["usage"]), json.dumps(record["review"], ensure_ascii=False)),
        )
        for index, finding in enumerate(record["review"]["findings"]):
            cur.execute(
                """INSERT INTO decision_intelligence.ai_review_finding
                   (run_id, finding_index, category, priority, evidence_ids, hypothesis, next_check)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (run_id, finding_index) DO NOTHING""",
                (record["run_id"], index, finding["category"], finding["priority"],
                 finding["evidence_ids"], finding["hypothesis"], finding["next_check"]),
            )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Build an aggregate-only packet locally")
    prepare.add_argument("--context", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    review = sub.add_parser("review", help="Review one packet with the Responses API or offline fixture")
    review.add_argument("--packet", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--model", default="gpt-4.1-mini")
    review.add_argument("--max-output-tokens", type=int, default=1200)
    review.add_argument("--fixture-response", type=Path, help="Synthetic API response; no network")
    review.add_argument("--send", action="store_true", help="Enable exactly one outbound API request")
    review.add_argument("--data-approved", action="store_true", help="Confirm organization approved this aggregate packet")
    review.add_argument("--persist-db", action="store_true", help="Write only the validated draft to the opt-in review tables")
    feedback = sub.add_parser("feedback", help="Append a human verdict for a draft finding")
    feedback.add_argument("--record", type=Path, required=True)
    feedback.add_argument("--output", type=Path, required=True)
    feedback.add_argument("--finding-index", type=int, required=True)
    feedback.add_argument("--verdict", choices=["ACCEPT", "REJECT", "REVISE"], required=True)
    feedback.add_argument("--reviewer", required=True)
    feedback.add_argument("--note", required=True)
    feedback.add_argument("--persist-db", action="store_true")
    args = parser.parse_args()

    if args.command == "prepare":
        packet = build_packet(read_json(args.context))
        write_json(args.output, packet)
        print(f"packet={args.output} facts={len(packet['facts'])} project_ref={packet['project_ref']}")
        return 0

    if args.command == "review":
        if args.output.exists():
            raise SystemExit("Output already exists: no duplicate API call")
        if bool(args.fixture_response) == bool(args.send):
            raise SystemExit("Choose exactly one of --fixture-response or --send")
        if args.send and not args.data_approved:
            raise SystemExit("Outbound request requires recorded organizational data approval (--data-approved)")
        packet = validate_packet(read_json(args.packet))
        body = request_body(packet, args.model, args.max_output_tokens)
        response = read_json(args.fixture_response) if args.fixture_response else call_responses(body, os.environ.get("OPENAI_API_KEY", ""))
        result = validate_review(packet, extract_output(response))
        record = review_record(packet, result, response)
        write_json(args.output, record)
        if args.persist_db:
            with db_connection() as conn:
                persist_record(conn, record)
        print(f"run={record['run_id']} status={record['status']} findings={len(result['findings'])}")
        return 0

    record = read_json(args.record)
    index = args.finding_index
    if record.get("status") != "DRAFT_REVIEW_REQUIRED" or not 0 <= index < len(record["review"]["findings"]):
        raise SystemExit("Unknown draft finding")
    if not 1 <= len(args.reviewer) <= 120 or not 1 <= len(args.note) <= 1000:
        raise SystemExit("Reviewer or note length invalid")
    event = {"run_id": record["run_id"], "finding_index": index, "verdict": args.verdict,
             "reviewer": args.reviewer, "note": args.note}
    if args.persist_db:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO decision_intelligence.ai_review_feedback
                       (run_id, finding_index, verdict, reviewer, note) VALUES (%s,%s,%s,%s,%s)""",
                    tuple(event.values()),
                )
            conn.commit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(f"feedback recorded for {record['run_id']} finding={index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

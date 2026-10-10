"""Tiny command-line chat: one prompt in, one reply out, saved and traced."""

import sys

from friday import db
from friday.llm import ask
from friday.trace import Tracer


def main() -> None:
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        print('Usage: python -m friday.cli "your message"')
        raise SystemExit(1)

    conn = db.connect()
    tracer = Tracer(conn)

    with tracer.step("save_user_message", prompt) as out:
        db.add_message(conn, "user", prompt)
        out["output"] = "saved"

    with tracer.step("llm", prompt) as out:
        reply = ask([{"role": "user", "content": prompt}])
        out["output"] = f"{reply.provider}/{reply.model}: {reply.text}"

    with tracer.step("save_reply", reply.text) as out:
        db.add_message(conn, "assistant", reply.text)
        out["output"] = "saved"

    print(reply.text)
    print(f"[{reply.provider} {reply.model} {reply.ms} ms | run {tracer.run_id}]")


if __name__ == "__main__":
    main()
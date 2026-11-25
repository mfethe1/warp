# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SQLite Cloud, Inc.
"""
test_stream_watermark.py — what a streaming client assembles after the
reply parser takes back text it had already let through.

`_run` in serve/server.py streams `parser.content` past a watermark,
`content_sent`. Two things shrink `parser.content` after part of it was
sent: the DSML parser trimming the "\\n\\n<" / "<" that opens a tool-call
block (dsml.py, `_tag`), and a stop string cutting the content. A shrink
leaves the watermark past the end of the text, and what the server does
with it then decides whether the client sees bytes twice, or never.

The two tests here are the two halves of one contract, and a fix has to
satisfy both: a streamed reply must not repeat text it already sent, and
it must not drop text the blocking reply contains. The obvious fix for the
first ("never move the watermark backward") breaks the second, which is
why the second exists.

Run from the repo root (imports are package-relative):

    python3 -m unittest tests.serve.test_stream_watermark -v
"""

import unittest

from serve import dsml
from tests.serve.test_server import ServerTestCase

D = dsml.DSML
CALL = (
    f"<{D} calls>\n"
    f'<{D} invoke name="get">\n'
    f'<{D} parameter name="city" string="true">Rome</{D} parameter>\n'
    f"</{D} invoke>\n"
    f"</{D} calls>"
)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
            },
        },
    }
]


def is_subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(c in it for c in needle)


class TestStreamWatermark(ServerTestCase):
    """A DSML container, so the parser that trims is the one in play."""

    engine_kwargs = {
        "no_markers": True,
        "markers": {100 + i: m for i, m in enumerate(dsml.MARKERS)},
    }

    def both(self, reply: str, **body):
        """The same scripted reply, blocking and streamed: (blocking, streamed)
        content as the client sees it."""
        self.engine.reply = reply
        status, blocking = self.chat(tools=TOOLS, **body)
        self.assertEqual(status, 200, blocking)
        events = self.stream(tools=TOOLS, **body)
        streamed = "".join(
            (c.get("delta", {}).get("content") or "")
            for e in events[:-1]
            for c in e.get("choices", [])
        )
        return blocking["choices"][0]["message"]["content"] or "", streamed

    def test_trim_under_a_stop_prefix_does_not_resend_streamed_text(self):
        """The watermark must not move back over bytes the client already has.

        "Let me check." is held back while it could still be the stop
        "check.\\n"; the "<" after it rules that out, so "check.<" goes out
        and the watermark sits at 14. Then the DSML block opens, the parser
        trims the "<", and the held-back suffix pulls the safe end down to 7
        ("Let me "). The watermark is set to 7 — backward — and the final
        delivery sends content[7:13], "check.", a second time. Measured on
        main at 99a07e0: streamed 'Let me check.<check.' against blocking
        'Let me check.' (the 883 differential found the same string).

        This test pins only the duplication. The stray "<" is a separate,
        lesser defect (a leak, not a repeat) and is deliberately not asserted
        here, so a fix for one is not blocked on the other.
        """
        reply = dsml.THINK_CLOSE + "Let me check." + CALL + dsml.EOS
        blocking, streamed = self.both(reply, stop=["check.\n"])
        self.assertEqual(blocking.count("check."), 1, blocking)
        self.assertEqual(
            streamed.count("check."),
            blocking.count("check."),
            f"stream re-sent already-delivered text: streamed {streamed!r}, "
            f"blocking {blocking!r}",
        )

    def test_trim_does_not_silently_drop_text_the_blocking_reply_has(self):
        """Every character of the blocking answer reaches a streaming client.

        After the trim the parser's content is shorter than what was sent,
        and text arriving afterward starts below the watermark. A fix that
        simply refuses to move the watermark backward would skip the first
        few characters of that text: "After the call." would arrive as
        "er the call." and nobody would be told. Main today over-delivers
        (the trimmed "\\n\\n<" stays in the stream) but loses nothing; that
        is the half of today's behaviour a fix must keep.

        The blocking answer must be a subsequence of the streamed one — not
        equal to it, so this test does not also pin the leaked "<".
        """
        cases = {
            "text after the call, no stop": (
                dsml.THINK_CLOSE
                + "Let me check.\n\n"
                + CALL
                + "After the call."
                + dsml.EOS,
                {},
            ),
            "trim under a stop prefix": (
                dsml.THINK_CLOSE + "Let me check." + CALL + dsml.EOS,
                {"stop": ["check.\n"]},
            ),
        }
        for name, (reply, body) in cases.items():
            with self.subTest(name):
                blocking, streamed = self.both(reply, **body)
                self.assertTrue(blocking, "blocking reply has no content")
                self.assertTrue(
                    is_subsequence(blocking, streamed),
                    f"stream dropped text the blocking reply has: streamed "
                    f"{streamed!r}, blocking {blocking!r}",
                )
                if not body:
                    self.assertIn("After the call.", streamed)

    def test_second_trim_does_not_resend_text_streamed_after_the_first(self):
        """Two tool-call blocks, two trims: neither may re-send streamed text.

        Each block's opening "\\n\\n<" is let through and then trimmed, so
        after the first trim the text the client holds no longer lines up
        character for character with the parser's content: it still carries
        the leaked "\\n\\n<". A re-sync that looks for the first place the
        two diverge finds that old leak rather than the second trim, and
        re-sends everything after it — "B." a second time. Measured at
        c4e8469: streamed 'A.\\n\\n<B.\\n\\n<B.' against blocking 'A.B.'.

        As in the first test, only the repeat is pinned; the leaked "<"s
        are not asserted on.
        """
        reply = (
            dsml.THINK_CLOSE + "A.\n\n" + CALL + "B.\n\n" + CALL + dsml.EOS
        )
        blocking, streamed = self.both(reply)
        self.assertEqual(blocking.count("B."), 1, blocking)
        self.assertEqual(
            streamed.count("B."),
            blocking.count("B."),
            f"stream re-sent already-delivered text: streamed {streamed!r}, "
            f"blocking {blocking!r}",
        )

    def test_post_trim_text_is_not_skipped_against_stale_pre_trim_bytes(self):
        """Text after a trim must not be matched against the leaked bytes.

        After the trim the client's stream still ends in the leaked
        "\\n\\n<". Once a regrown character that differs from them is sent
        ("X"), those stale bytes now sit *before* the send point in the
        client's stream — but a re-sync that keeps matching new text against
        them treats the next character that happens to equal one ("\\n") as
        already delivered and skips it. The text is gone, and out of order:
        the client has its "\\n" before the "X", not after. Measured at
        35cc20e: streamed 'a\\n\\n<XY' against blocking 'aX\\nY', and
        streamed 'a\\n\\n<X\\nY' against blocking 'aX\\n\\nY'.

        As in the second test, the assertion is no silent loss — the blocking
        answer is a subsequence of the streamed one — so the leaked "\\n\\n<"
        is not pinned.
        """
        for tail in ("X\nY", "X\n\nY"):
            with self.subTest(tail=tail):
                reply = dsml.THINK_CLOSE + "a\n\n" + CALL + tail + dsml.EOS
                blocking, streamed = self.both(reply)
                self.assertEqual(blocking, "a" + tail, blocking)
                self.assertTrue(
                    is_subsequence(blocking, streamed),
                    f"stream dropped text the blocking reply has: streamed "
                    f"{streamed!r}, blocking {blocking!r}",
                )

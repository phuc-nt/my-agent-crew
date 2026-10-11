"""What a script printed, held to the most it may print.

A script that prints more than that is not ended for it. The start of what it printed is
kept, and the end of it, where the total or the conclusion usually is; what lay between is
counted and left out, with a line saying so. However much is printed, little more than the
most is ever held, so a script that prints for long is not ended for what it holds either.
"""

from __future__ import annotations

from collections import deque

from my_agent_crew import texts_script as t
from my_agent_crew.script.limits import MAX_OUTPUT_CHARS

# Of what is kept once too much was printed: three parts from the start, one from the end.
HEAD_CHARS = MAX_OUTPUT_CHARS * 3 // 4
TAIL_CHARS = MAX_OUTPUT_CHARS - HEAD_CHARS


class Printed:
    def __init__(self) -> None:
        self.total = 0
        self._head: list[str] = []
        self._head_chars = 0
        # The latest pieces: all that came after the start, or the last `TAIL_CHARS` of it.
        self._tail: deque[str] = deque()
        self._tail_chars = 0

    def write(self, text: str) -> None:
        self.total += len(text)
        room = HEAD_CHARS - self._head_chars
        if room:
            self._head.append(text[:room])
            self._head_chars += min(len(text), room)
            text = text[room:]
        if not text:
            return
        piece = text[-TAIL_CHARS:]  # no more of one piece could be kept
        self._tail.append(piece)
        self._tail_chars += len(piece)
        while self._tail_chars - len(self._tail[0]) >= TAIL_CHARS:
            self._tail_chars -= len(self._tail.popleft())

    @property
    def held(self) -> int:
        """How many characters are kept, whatever was printed."""
        return self._head_chars + self._tail_chars

    def text(self) -> str:
        head, tail = "".join(self._head), "".join(self._tail)
        if self.total <= MAX_OUTPUT_CHARS:
            return head + tail
        # The line that says what was left out is paid for out of the end, sized for the
        # widest it can be, so the whole never passes the most.
        widest = t.SCRIPT_OUTPUT_DROPPED.format(total=self.total, dropped=self.total)
        tail = tail[-(TAIL_CHARS - len(widest)) :]
        dropped = self.total - len(head) - len(tail)
        return head + t.SCRIPT_OUTPUT_DROPPED.format(total=self.total, dropped=dropped) + tail

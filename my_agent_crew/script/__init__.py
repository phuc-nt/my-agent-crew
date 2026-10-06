"""`tool_script`: a short script a model writes to make many read-only tool calls and keep
only what it prints.

The script is a small part of Python, parsed with `ast` and walked by an interpreter that
holds nothing else: no import, no file, no attribute but the methods it lists. It runs in a
child process with an empty environment, so a mistake here costs that process and not the
server. `tool.py` is the tool; `runner.py` talks to the child; `machine.py` is the
interpreter both of them and the tests share.
"""

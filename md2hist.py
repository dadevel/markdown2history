#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "markdown-it-py>=3.0",
#     "tree-sitter>=0.23",
#     "tree-sitter-bash>=0.23",
# ]
# ///

from __future__ import annotations
from collections.abc import Iterator
from pathlib import Path
import argparse
import re
import sys

from markdown_it import MarkdownIt
from tree_sitter import Language, Parser
import tree_sitter_bash

SHELL_LANGS = {'shell', 'bash', 'sh'}
TEXT_LANGS = {'text'}
PS1_PROMPTS = {'$ ', '❯ '}
PS2_PROMPTS = {'> '}
MD_SUFFIXES = {'.md', '.markdown', '.mdown', '.mkd'}
# bash treats any history line starting with '#<digit>' as a timestamp, even mid-entry
TIMESTAMP_LIKE = re.compile(r'^#\d', re.MULTILINE)

BASH = Parser(Language(tree_sitter_bash.language()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', default='.', type=Path)
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error(f'not a directory: {args.directory}')

    for path in find_markdown_files(args.directory):
        try:
            text = path.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeDecodeError) as exc:
            print(f'warning: skipping {path}: {exc}', file=sys.stderr)
            continue
        timestamp = int(path.stat().st_mtime)
        for offset, cmd in enumerate(commands_from_markdown(text)):
            if TIMESTAMP_LIKE.search(cmd):
                print(f'warning: skipping command from {path}, a line starting with "#<digit>" would corrupt the histfile:\n{cmd}', file=sys.stderr)
                continue
            sys.stdout.write(f'#{timestamp + offset}\n{cmd}\n')


def find_markdown_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*') if p.suffix.lower() in MD_SUFFIXES and p.is_file())


def commands_from_markdown(text: str) -> Iterator[str]:
    md = MarkdownIt('commonmark')
    for token in md.parse(text):
        if token.type != 'fence':
            continue
        lang = (token.info.split() or [''])[0].lower()
        if lang in SHELL_LANGS:
            yield from commands_from_shell_block(token.content)
        elif lang in TEXT_LANGS:
            yield from commands_from_prompt_block(token.content)


def commands_from_shell_block(code: str) -> Iterator[str]:
    """Yield commands from a shell block, one per top-level statement.

    Statements sharing a line (``a; b``, trailing comments) stay together as
    one entry, as they would in bash history. Comment-only lines are dropped.
    """
    # not splitlines(): it also splits on \x0c etc., which tree-sitter rows don't count
    lines = code.split('\n')
    # Group top-level nodes into runs of whole lines: [first_row, last_row, ...].
    groups: list[list] = []
    for node in BASH.parse(code.encode()).root_node.children:
        start, end = node.start_point.row, node.end_point.row
        is_comment = node.type == 'comment'
        if groups and start <= groups[-1][1]:
            group = groups[-1]
            group[1] = max(group[1], end)
            group[2] = group[2] and is_comment
            group[3] = group[3] or node.has_error
        else:
            groups.append([start, end, is_comment, node.has_error])

    for start, end, comment_only, has_error in groups:
        if comment_only:
            continue
        group_lines = lines[start:end + 1]
        if has_error:
            yield from _split_lines(group_lines)
        else:
            yield '\n'.join(group_lines).rstrip()


def commands_from_prompt_block(code: str) -> Iterator[str]:
    """Yield commands from lines prefixed with a prompt; other lines are output.

    A prompt line whose command is incomplete (heredoc, trailing backslash, open quote, ...) absorbs the following non-prompt lines, minus any PS2 "> " prefix, until it parses cleanly.
    If it never does, only the prompt line itself is used, so command output is not swallowed.
    """
    lines = code.splitlines()
    i = 0
    while i < len(lines):
        cmd = _strip_prompt(lines[i])
        i += 1
        if cmd is None or not cmd.strip() or cmd.lstrip().startswith('#'):
            continue
        parts = [cmd]
        j = i
        complete = _is_complete(cmd)
        while not complete and j < len(lines) and _strip_prompt(lines[j]) is None:
            continuation = _strip_prompt(lines[j], PS2_PROMPTS)
            parts.append(lines[j] if continuation is None else continuation)
            j += 1
            complete = _is_complete('\n'.join(parts))
        if complete:
            i = j
            yield '\n'.join(parts).rstrip()
        else:
            yield cmd.rstrip()


def _is_complete(code: str) -> bool:
    """True if code parses as complete bash (no unclosed heredoc/quote/etc)."""
    return not BASH.parse(code.encode()).root_node.has_error


def _strip_prompt(line: str, prompts: set[str] = PS1_PROMPTS) -> str|None:
    stripped = line.lstrip()
    for prompt in prompts:
        # editors often trim the trailing space of an empty prompt line
        if stripped.rstrip() == prompt.rstrip():
            return ''
        if stripped.startswith(prompt):
            return stripped[len(prompt):]
    return None


def _split_lines(lines: list[str]) -> Iterator[str]:
    """Fallback for unparsable code: one command per non-comment line."""
    for line in lines:
        if line.strip() and not line.lstrip().startswith('#'):
            yield line.rstrip()


if __name__ == '__main__':
    main()

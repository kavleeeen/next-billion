"""The entry point has to import and parse.

No other test imports cli, so a broken import there passes the whole suite and
fails only when a person runs the command.
"""
from __future__ import annotations

import pytest

from pipeline.cli import build_parser
from pipeline.prepare import MAX_SELECTION

# Command, plus whatever positional arguments it requires.
COMMANDS = (
    ("sync", ["AI agents for SMBs"]),
    ("search", ["agents"]),
    ("enrich", []),
    ("comments", []),
    ("prepare", ["1,2"]),
    ("score", ["1,2"]),
)


@pytest.fixture
def parser():
    return build_parser()


class TestParser:
    @pytest.mark.parametrize("command,argv", COMMANDS)
    def test_every_command_parses(self, parser, command, argv):
        assert callable(parser.parse_args([command, *argv]).func)

    @pytest.mark.parametrize("command", ["prepare", "score"])
    def test_the_cap_is_not_typed_twice(self, parser, command):
        # A number typed here would drift from prepare.MAX_SELECTION.
        assert f"max {MAX_SELECTION}" in _help_for(parser, command)

    def test_score_takes_force(self, parser):
        assert parser.parse_args(["score", "1,2", "--force"]).force is True


def _help_for(parser, command: str) -> str:
    action = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    return action.choices[command].format_help()

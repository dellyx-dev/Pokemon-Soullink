"""GBA link cable run: connects two players as a ProcessGroup through the plugin and plays key scripts. ROM and save state
are copies; they can be passed as arguments or through SOULLINK_LINK_ROM, SOULLINK_LINK_STATE and SOULLINK_LINK_OUTPUT,
and both players start from the same save."""
from __future__ import annotations

import os
import shutil
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import link_run  # noqa: E402

ID = "link_cable_gba"
_START = "-:5 " + link_run.repeats(7, "A:5 -:50") + " -:60 A:5 -:60 A:5 -:800 A:5 -:300 A:5 -:300"
DEFAULT = (
    _START + " A:5 -:300 A:5 -:300 A:5 -:200 -:500 LEFT:40 -:10 UP:40 -:10 LEFT:10 -:40 RIGHT:4 -:20 A:5 -:200"
              " IMAGE:u1 -:300 IMAGE:u2 -:300 IMAGE:u3 -:300 IMAGE:u4",
    _START + " -:300 -:300 -:200 -:500 RIGHT:24 -:10 UP:40 -:10 RIGHT:10 -:40 LEFT:4 -:20 A:5 -:200"
              " IMAGE:u1 -:300 IMAGE:u2 -:300 IMAGE:u3 -:300 IMAGE:u4",
)


def main(argv: list[str] | None = None) -> int:
    """Runs the link cable session and prints the report."""
    from soullink.player import ProcessGroup, PlayerProcess

    a = link_run.arguments(__doc__.splitlines()[0], ".gba", argv)
    scripts = a.scripts or list(DEFAULT)
    group = ProcessGroup(len(scripts))
    player = [PlayerProcess(nr, link_run.player_dir(a.work, nr, a.rom, a.state, "gba"), False, group=group,
                              plugins=[link_run.entry(ID)], base=a.work) for nr in range(1, len(scripts) + 1)]
    b = link_run.Observer(player, ID)
    try:
        for sp in player:
            sp.start()
        if not b.wait(lambda: all(sp.ready_info for sp in player), 60):
            print("Players do not start:", [sp.error for sp in player])
            return 1
        print("ready", [sp.ready_info["plugins"] for sp in player])
        for sp in player:
            sp.pause(True)
        for sp in player:
            sp.plugin_command(ID, True)
        connected = b.wait(lambda: all(a_[-1:] == [True] for a_ in b.reply.values()), 5)
        print("connected", connected, b.reply)
        for sp in player:
            sp.pause(False)
        duration = link_run.play(b, [link_run.plan(s) for s in scripts], a.output_dir)
        print("Scripts done after", round(duration, 1), "s; frames", [link_run.frame_number(sp) for sp in player])
        b.wait(lambda: False, 2)
        for sp in player:
            sp.plugin_command(ID, False)
        b.wait(lambda: all(a_[-1:] == [False] for a_ in b.reply.values()), 5)
        print("Replies of the worker part:", b.reply)
    finally:
        for sp in player:
            sp.end()
        if a.own_work:
            shutil.rmtree(a.work, ignore_errors=True)
    print("error", [sp.error for sp in player], "ended", [sp.ended for sp in player])
    return 0 if connected and not b.error and not any(sp.error for sp in player) else 1


if __name__ == "__main__":
    raise SystemExit(main())

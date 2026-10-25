"""Tests of the randomizer calls."""

import subprocess
from pathlib import Path

from soullink import paths
from soullink import randomizer as R

LOG = (
    "Randomization of POKEMON EMER (BPED) completed.\n"
    "Random Seed: 151306480286548\n"
    "KINGDRA Lvs 10-30     HP 75  ATK 95\n"
)


def test_command():
    """The randomizer command line is correct."""
    cmd = R.command(Path("java"), Path("z.jar"), Path("p.rnqs"), Path("in.gba"), Path("out") / "rom.gba")
    assert cmd == ["java", "-jar", "z.jar", "cli", "-s", "p.rnqs", "-i", "in.gba",
                   "-o", str(Path("out") / "rom.gba"), "-l"]


def test_read_seed():
    """The seed is read from the log."""
    assert R.read_seed(LOG) == "151306480286548"
    assert R.read_seed("nothing") is None


def test_error_text():
    """The error text is extracted from the output."""
    output = "ERROR: Destination ROM path not writable\nUsage: java -jar ...\n-d: Save 3DS"
    assert R.error_text(output) == "Destination ROM path not writable"
    assert R.error_text("java.lang.Exception: broken\n\n") == "java.lang.Exception: broken"
    assert R.error_text("") == "Unknown error"


def _fake_ok(cmd, **kw):
    """Fake run that creates the target ROM and a log with a seed."""
    target = Path(cmd[cmd.index("-o") + 1])
    target.write_bytes(b"rom")
    Path(str(target) + ".log").write_bytes(b"\xef\xbb\xbf" + LOG.encode("utf-8"))
    return subprocess.CompletedProcess(cmd, 0, "Randomized successfully!\n", "")


def _fake_error(cmd, **kw):
    """Fake run that fails with an error message."""
    return subprocess.CompletedProcess(cmd, 1, "ERROR: Randomization failed\nUsage: x\n", "")


def _source(tmp_path, name="in.gba"):
    """Creates a source ROM file."""
    file = tmp_path / name
    file.write_bytes(b"base")
    return file


def test_randomize_ok(tmp_path):
    """A successful run returns the seed."""
    dir = tmp_path / "p1"
    e = R.randomize(1, Path("java"), Path("z.jar"), Path("p.rnqs"), _source(tmp_path), dir, run=_fake_ok)
    assert e.ok and e.seed == "151306480286548" and e.nr == 1
    assert (dir / "randomizer.log").exists()
    assert not (dir / "rom.gba.log").exists()


def test_randomize_error(tmp_path):
    """A failing run returns the error."""
    e = R.randomize(2, Path("java"), Path("z.jar"), Path("p.rnqs"), _source(tmp_path), tmp_path / "p2",
                       run=_fake_error)
    assert not e.ok and e.message == "Randomization failed"


def test_randomize_java_missing(tmp_path):
    """Missing Java is reported."""
    def broken(cmd, **kw):
        """Fake run that behaves as if Java is missing."""
        raise FileNotFoundError("java")
    e = R.randomize(1, Path("java"), Path("z.jar"), Path("p.rnqs"), _source(tmp_path), tmp_path / "p1",
                       run=broken)
    assert not e.ok and "java" in e.message


def test_without_randomizer(tmp_path):
    """Without a randomizer the ROM is copied."""
    source = tmp_path / "base.gba"
    source.write_bytes(b"abc")
    e = R.without_randomizer(3, source, tmp_path / "p3")
    assert e.ok and e.seed is None
    assert (tmp_path / "p3" / "rom.gba").read_bytes() == b"abc"


def test_find_presets(tmp_path):
    """Presets are found and sorted."""
    assert R.find_presets(tmp_path / "missing") == []
    (tmp_path / "b.rnqs").write_bytes(b"x")
    (tmp_path / "A.rnqs").write_bytes(b"x")
    (tmp_path / "note.txt").write_text("x")
    assert [p.name for p in R.find_presets(tmp_path)] == ["A.rnqs", "b.rnqs"]


def test_real_run(tmp_path, test_rom, test_preset):
    """A real randomizer run works (needs ROM and preset)."""
    e = R.randomize(1, paths.java_program(), paths.randomizer_jar(), test_preset, test_rom, tmp_path / "p1")
    assert e.ok, e.message
    assert (tmp_path / "p1" / "rom.gba").stat().st_size == 16 * 1024 * 1024
    assert e.seed and e.seed.lstrip("-").isdigit()


def test_randomize_nds_suffix(tmp_path):
    """NDS ROMs keep their suffix."""
    dir = tmp_path / "p1"
    e = R.randomize(1, Path("java"), Path("z.jar"), Path("p.rnqs"), _source(tmp_path, "in.nds"), dir,
                       run=_fake_ok)
    assert e.ok and (dir / "rom.nds").exists() and (dir / "randomizer.log").exists()
    assert not (dir / "rom.nds.log").exists()
    source = tmp_path / "b.nds"
    source.write_bytes(b"ds")
    assert R.without_randomizer(2, source, tmp_path / "p2").ok
    assert (tmp_path / "p2" / "rom.nds").read_bytes() == b"ds"


def test_same_game_gets_own_input_file(tmp_path):
    """Players with the same game get own input files."""
    source = _source(tmp_path, "base-1.nds")
    inputs = []

    def remember(cmd, **kw):
        """Fake run that remembers the input file name."""
        input = Path(cmd[cmd.index("-i") + 1])
        inputs.append((input.name, input.read_bytes()))
        return _fake_ok(cmd, **kw)

    for nr in (1, 2):
        assert R.randomize(nr, Path("java"), Path("z.jar"), Path("p.rnqs"), source, tmp_path / f"p{nr}",
                              run=remember).ok
    assert [n for n, _ in inputs] == ["input-p1.nds", "input-p2.nds"]
    assert all(data == b"base" for _, data in inputs)
    assert not list(tmp_path.glob("p*/input-*")) and source.exists()


def test_error_text_java_exception():
    """A Java exception line is used as the error text."""
    stack = ("java.lang.ArrayIndexOutOfBoundsException: Index 210248 out of bounds for length 0\n"
             "\tat com.dabomstew.pkrandom.FileFunctions.read2ByteInt(FileFunctions.java:127)\n")
    assert R.error_text(stack).startswith("java.lang.ArrayIndexOutOfBoundsException")

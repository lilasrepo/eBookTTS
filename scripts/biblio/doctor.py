# -*- coding: utf-8 -*-
"""doctor -- environment self-check for a fresh machine.

Confirms the toolchain matches what golden.json was frozen against, so a byte-drift in
regress is diagnosed as "wrong OpenCC install" (its usual cause) rather than a code bug.
Build-critical checks (Python, OpenCC convert version, TSCharacters.txt) fail the command;
tts-only checks (edge-tts, mutagen, ffmpeg) only warn.
"""
import os
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (scripts/biblio/..)


_VERIFIED_PY = ((3, 13), (3, 14))   # (major, minor) pairs where regress.py passed against golden


def _req_pin(name):
    """Exact version pinned for `name` in requirements.txt (single source of truth), or None."""
    try:
        with open(os.path.join(_ROOT, "requirements.txt"), encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#")[0].strip()
                if "==" in line and line.split("==")[0].strip().lower() == name.lower():
                    return line.split("==", 1)[1].strip()
    except Exception:
        pass
    return None


def run_doctor():
    """Print a check report; return True iff all build-critical checks pass."""
    ok = [True]

    def check(label, good, detail="", fatal=True):
        mark = "OK  " if good else ("FAIL" if fatal else "WARN")
        # remediation detail is only useful when the check did NOT pass
        print("  [%s] %s%s" % (mark, label, ("  -- " + detail) if (detail and not good) else ""))
        if not good and fatal:
            ok[0] = False

    print("[doctor] environment self-check")

    v = sys.version_info
    check("Python %d.%d.%d (%s)" % (v[0], v[1], v[2], sys.executable), v >= (3, 7), "need >= 3.7")
    check("Python %d.%d in golden-verified set (%s)"
          % (v[0], v[1], ", ".join("%d.%d" % p for p in _VERIFIED_PY)),
          (v[0], v[1]) in _VERIFIED_PY, "not yet verified; run scripts/regress.py", fatal=False)

    # OpenCC convert: version must match the golden pin (1.4.x produces different bytes).
    pin = _req_pin("OpenCC")
    try:
        import opencc
        ver = str(getattr(opencc, "__version__", "?"))
        check("OpenCC %s (requirements pin %s)" % (ver, pin or "?"),
              pin is not None and ver == pin,
              "golden frozen on %s; other builds drift -> regress FAIL" % (pin or "1.3.1"))
    except Exception as e:
        check("import opencc", False, str(e))

    # TSCharacters.txt gates Simplified-marker precision (from opencc-python-reimplemented).
    try:
        from . import textconv
        keys = textconv._ts_keys()
        check("OpenCC TSCharacters.txt (%d keys)" % len(keys), len(keys) > 1000,
              "install opencc-python-reimplemented==%s" % (_req_pin("opencc-python-reimplemented") or "0.1.7"))
    except Exception as e:
        check("read TSCharacters.txt", False, str(e))

    # Audiobook-only python deps (warn, not fatal -- .md build does not need them).
    for mod in ("edge_tts", "mutagen"):
        try:
            __import__(mod)
            check("import %s (tts)" % mod, True, fatal=False)
        except Exception as e:
            check("import %s (tts only)" % mod, False, str(e), fatal=False)

    # ffmpeg + libmp3lame (tts only, warn).
    ff = shutil.which("ffmpeg")
    if ff:
        try:
            enc = subprocess.run([ff, "-hide_banner", "-encoders"],
                                 capture_output=True, text=True, timeout=15).stdout
            check("ffmpeg + libmp3lame (tts)", "libmp3lame" in enc,
                  "ffmpeg lacks libmp3lame encoder", fatal=False)
        except Exception as e:
            check("ffmpeg -encoders", False, str(e), fatal=False)
    else:
        check("ffmpeg on PATH (tts only)", False, "install ffmpeg with libmp3lame", fatal=False)

    # Fixture source present (the sample epub is tracked).
    have_gate = os.path.exists(os.path.join(_ROOT, "book", "_fixtures", "sample", "source", "sample.epub"))
    check("fixture source (sample.epub)", have_gate, "run scripts/make_epub_fixture.py", fatal=False)

    print("[doctor] %s" % ("all build-critical checks passed"
                           if ok[0] else "BUILD-CRITICAL failure(s) above -- see README.md (Install section)"))
    return ok[0]

#!/usr/bin/env python3
"""
Generate or load a pinned camoufox fingerprint at .camoufox-fingerprint.pkl.
DataDome binds its cookie to fingerprint; random fingerprints break session reuse.
"""
import pathlib, pickle, sys
from browserforge.fingerprints import FingerprintGenerator

REPO = pathlib.Path(__file__).resolve().parent.parent
FP_FILE = REPO / ".camoufox-fingerprint.pkl"


def load_or_create():
    if FP_FILE.exists():
        return pickle.loads(FP_FILE.read_bytes())
    fp = FingerprintGenerator(browser="firefox", os="macos").generate()
    FP_FILE.write_bytes(pickle.dumps(fp))
    return fp


if __name__ == "__main__":
    fp = load_or_create()
    ua = getattr(fp.navigator, "userAgent", "?")
    print(f"[fp] {'loaded' if FP_FILE.stat().st_size else 'created'} fingerprint at {FP_FILE}")
    print(f"[fp] UA: {ua[:100]}")
    sys.exit(0)

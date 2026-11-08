"""Entry point of the packaged Mac app (PyInstaller): `shadow-brain` runs the server,
`shadow-brain tts TEXT` / `shadow-brain tts --prefetch TEXT` plays or caches one sentence."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tts":
        from brain import tts
        tts.cli(sys.argv[2:])
    else:
        from brain import server
        server.main()

# Windows background runtime

`start_fastapi.ps1` starts the local FastAPI runtime from the repository's
`.venv` in the interactive user's session. The interactive session is
intentional: CityResponder's shared vision worker may need access to the USB
webcam and local desktop camera drivers.

The script is safe to run repeatedly. If `http://127.0.0.1:8020/health` is
already healthy, it exits without starting a second process. Runtime stdout
and stderr are written under the ignored `data/runtime_logs/` directory.

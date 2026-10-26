# Backend test data and isolation

`pytest` uses a process-local settings boundary from `conftest.py`: SQLite is a
temporary file under a unique OS temp directory, MQTT points to loopback port
18884, live vision/evidence publishing are disabled, the operator runtime
config file is bypassed, and the JWT/seed password are generated for that test
process only. The generated values are never written to disk or logged. The
temporary database directory is removed when the test session finishes.

Most tests are self-contained. The camera-alignment and historical road-vision
regression tests additionally need the locally held development artifact tree
that contains `reports/debug/camera_alignment/` and
`reports/debug/road_vision_tests/`. Those artifacts include the reviewed ROI and
road graph drafts, their source camera frame, and the existing SHA-256 manifest
for historical test outputs. They are intentionally ignored by Git and are
read-only test inputs; this suite does not create or update them.

To run the complete suite where those development artifacts are available,
point `CITYRESPONDER_TEST_DATA_ROOT` at a CityResponder root containing
`reports/debug/`:

```powershell
$env:CITYRESPONDER_TEST_DATA_ROOT = 'C:\path\to\CityResponder'
py -3.14 -m pytest backend\tests -q
```

The variable is optional for tests that do not need these artifacts. A CI or
other clean checkout can mount its approved development artifact bundle at any
path and set the same variable. No production database, broker, credentials,
or sensor values are test fixtures.

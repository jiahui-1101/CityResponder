# Focused requirements validation

Run from the repository root with the project environment:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m scripts.validate_requirements --output ..\reports\validation\step16_result.json
Pop-Location
```

The harness uses the running backend for real login/RBAC responses and isolated
temporary SQLite/filesystem fixtures for mutation-sensitive checks. It is not a
full test suite and does not add production defaults for unresolved policies.

`step16_manual_live_latency.json` records one manually controlled MQ2 live-update
run; it must not be interpreted as a general benchmark.

## Validation index

- Step 16 Requirements Validation: `backend/scripts/validate_requirements.py`
- Step 17 Controlled E2E: `backend/scripts/validate_e2e_cycle.py` and `step17_e2e_cycle.*`
- Step 18 Response Timing: `backend/scripts/benchmark_response_timing.py` and `step18_response_timing.*`
- Step 19 Vision/Hardware Acceptance: `step19/` templates and acceptance report
- Final Validation Summary: `final_validation_summary.*`

Step 16 is software/API evidence with one manually observed latency run. Steps
17–18 are controlled software/mock integration evidence. Step 19 awaits real
camera/model and AC1 hardware observations; those results are not inferred from
mock ACKs.

Final status: `SOFTWARE_IMPLEMENTATION_FROZEN`. Software FAIL count is 0;
Step 19 external/manual acceptance remains separate and is not represented as
software PASS.

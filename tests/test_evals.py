import sqlite3
from evals import run_evals


def test_cached_evals_pass_all_gates(tmp_path):
    db_path = str(tmp_path / "app.db")
    res = run_evals.run(mode="cached", db_path=db_path, verbose=False)
    assert res["status"] == "PASSED", res["blocking_failures"]
    assert res["dataset_version"] == "golden-demo-1.0"
    conn = sqlite3.connect(db_path)
    run = conn.execute("SELECT status, prompt_version, rule_version FROM evaluation_runs").fetchone()
    assert run[0] == "PASSED" and run[1] and run[2]
    stages = {r[0] for r in conn.execute("SELECT DISTINCT stage FROM evaluation_results")}
    assert stages == {"raw", "validated"}
    cases = {r[0] for r in conn.execute("SELECT DISTINCT eval_case_id FROM evaluation_results")}
    assert len(cases) == 8

"""Offline guard checks. Local metadata only; no fabricated provider replies or live-proof claims."""
import json
import pathlib
import subprocess
import sys
from unittest.mock import patch

import pytest

import fleet_graduation as fleet


def write_metadata(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_old_single_row_label_cannot_admit(tmp_path):
    artifact = write_metadata(tmp_path / "local.json", {"host": "local-metadata-only"})
    report = write_metadata(tmp_path / "report.json", {"results": [{"verdict": "REPLAY_OK"}]})
    with pytest.raises(RuntimeError, match="PROOF_ATTEMPT_MISMATCH"):
        fleet.checked_proof(report, artifact, "a" * 32)


def test_wrong_artifact_and_changed_bytes_are_rejected(tmp_path):
    artifact = write_metadata(tmp_path / "local.json", {"host": "local-metadata-only"})
    row = {"attemptId": "a" * 32, "file": "another.json", "host": "local-metadata-only"}
    report = write_metadata(tmp_path / "report.json", {"results": [row]})
    with pytest.raises(RuntimeError, match="IDENTITY_MISMATCH"):
        fleet.checked_proof(report, artifact, "a" * 32)
    row["file"] = artifact.name
    row["artifactSha256"] = "not-the-artifact-hash"
    write_metadata(report, {"results": [row]})
    with pytest.raises(RuntimeError, match="ARTIFACT_CHANGED"):
        fleet.checked_proof(report, artifact, "a" * 32)


def test_attempt_keeps_stage_history_and_refuses_path_escape(tmp_path):
    with patch.object(fleet, "ATTEMPTS", tmp_path):
        with pytest.raises(RuntimeError, match="INVALID_ATTEMPT_ID"):
            fleet.save_attempt("../outside", stage="capture", state="BLOCKED")
        fleet.save_attempt("a" * 32, stage="login", state="OBSERVED")
        fleet.save_attempt("a" * 32, stage="capture", state="BLOCKED")
    value = json.loads((tmp_path / (("a" * 32) + ".json")).read_text())
    assert [event["stage"] for event in value["events"]] == ["login", "capture"]


def test_single_owner_lock_rejects_second_real_process(tmp_path):
    script = ("import sys,pathlib;sys.path.insert(0,sys.argv[1]);import fleet_graduation as f;"
              "f.STATE=pathlib.Path(sys.argv[2]);\nwith f.controller_lock(): pass")
    with patch.object(fleet, "STATE", tmp_path), fleet.controller_lock():
        child = subprocess.run([sys.executable, "-c", script, str(pathlib.Path(fleet.__file__).parent), str(tmp_path)],
                               capture_output=True, timeout=20)
    assert child.returncode != 0
    assert b"another graduation controller" in child.stderr
    with patch.object(fleet, "STATE", tmp_path), fleet.controller_lock():
        pass  # OS release permits the next real owner without deleting a PID file.


def test_missing_media_verifier_stops_before_any_download():
    with patch.object(fleet.shutil, "which", return_value=None), \
         patch.object(fleet.urllib.request, "urlopen") as request:
        with pytest.raises(RuntimeError, match="MEDIA_VERIFIER_OR_URL_UNAVAILABLE"):
            fleet.verify_media_delivery("https://local-test.invalid/not-requested")
    request.assert_not_called()


def test_replay_timeout_does_not_admit_or_reuse_old_report(tmp_path):
    artifact = write_metadata(tmp_path / "local.json", {"host": "local-metadata-only", "modality": "chat"})
    with patch.object(fleet, "ATTEMPTS", tmp_path / "attempts"), \
         patch.object(fleet, "admission_problem", return_value=None), \
         patch.object(fleet, "run_bounded_child", return_value=None), \
         patch.object(fleet, "admit") as admit:
        with pytest.raises(SystemExit, match="timed out"):
            fleet.verify_and_admit(artifact)
    admit.assert_not_called()
    receipt = json.loads(next((tmp_path / "attempts").glob("*.json")).read_text())
    assert receipt["state"] == "BLOCKED"
    assert "runtime" not in json.loads(artifact.read_text())


def test_failed_plan_stops_before_login_capture_or_replay(tmp_path):
    with patch.object(fleet, "STATE", tmp_path), \
         patch.object(fleet, "E2E_RUN", tmp_path / "run.json"), \
         patch.object(fleet, "declared_fleet", return_value=[{"port": 9222, "profile": "local-test-only"}]), \
         patch.object(fleet, "run_bounded_child", return_value=1) as child:
        fleet.e2e_chat_apply(10, 10, 1)
    assert child.call_count == 1
    result = json.loads((tmp_path / "run.json").read_text())
    assert result["profiles"][0]["failedStage"] == "login"
    assert result["profiles"][0]["captures"] == []


def test_no_current_admissions_cannot_probe_historical_registry(tmp_path):
    run_path = write_metadata(tmp_path / "run.json", {"profiles": []})
    with patch.object(fleet, "E2E_RUN", run_path), \
         patch.object(fleet, "load_registry", return_value={"entries": [
             {"state": "ADMITTED", "modality": "chat", "host": "local-metadata-only", "sessionFile": "old.json"}]}), \
         patch.object(fleet, "consumer_chat_probe") as consumer:
        fleet.e2e_chat_consumer_proofs()
    consumer.assert_not_called()
    assert json.loads(run_path.read_text())["consumerProofs"] == []


def test_consumer_exception_is_persisted_as_failure(tmp_path):
    run_path = write_metadata(tmp_path / "run.json", {"profiles": [{"captures": [
        {"sessionFile": "local.json", "state": "ADMITTED_TO_8190_PURE_PYTHON"}]}]})
    with patch.object(fleet, "E2E_RUN", run_path), patch.object(fleet, "SECRETS", tmp_path), \
         patch.object(fleet, "load_registry", return_value={"entries": [
             {"state": "ADMITTED", "modality": "chat", "host": "local-metadata-only", "sessionFile": "local.json"}]}), \
         patch.object(fleet, "consumer_chat_probe", side_effect=TimeoutError):
        fleet.e2e_chat_consumer_proofs()
    result = json.loads(run_path.read_text())["consumerProofs"][0]
    assert result["state"] == "CONSUMER_TRANSPORT_FAILED"
    assert result["reason"] == "TimeoutError"

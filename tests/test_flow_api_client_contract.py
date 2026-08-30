from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from flow_api_client import FlowApiClient


def test_completed_flow_result_exposes_consumer_ledger_cost_compatibility_key(monkeypatch):
    client = FlowApiClient()
    client.confirm_spend = True
    client.max_spend = 30
    monkeypatch.setattr(client, "_quote", lambda model: {"quote": 20, "balance": 100})
    monkeypatch.setattr(client, "_ledger", lambda item: None)
    monkeypatch.setattr(client, "_call", lambda *args, **kwargs: {
        "status": "succeeded",
        "id": "safe-test-job",
        "model": "veo_3_1_t2v_fast",
        "duration": "8s",
        "credits_charged": 20,
        "content_url": "/v1/videos/safe-test-job/content",
    })

    result = client.chat([{"role": "user", "content": "A calm paper boat floats across a gentle river."}])

    assert result["credits"] == 20.0
    assert result["credits_spent"] == 20.0

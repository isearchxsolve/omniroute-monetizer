"""video_provider_digen.py -- digen.ai as a router provider.

Replays the session captured by sweep_grab.py over plain HTTP.
Fixes applied:
1. Synthesizes `code` idempotency key.
2. Implements quote() and confirm() via /v1/credit/remain.
3. Removes hardcoded status=2 from poll URL.
4. Uses separate request_timeout and poll_budget.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import uuid

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import video_provider as vp  # noqa: E402

SECRET = pathlib.Path("D:/omniroute-monetizer/state/secrets/session_digen_ai.json")
_DROP_HDR = {"content-length", "accept-encoding", "cookie"}

class DigenProvider(vp.Provider):
    name = "digen"
    title = "digen.ai"
    tab_match = ""
    default_url = "https://digen.ai/"
    out_dir = pathlib.Path("state/harvest/digen")
    est_cost = 30
    max_spend_default = 60
    quotes_before_spending = True
    proven = {"digen"}
    aliases = {"digen": "digen", "wan": "digen"}

    def __init__(self):
        self._headers = {}
        self._submit_tmpl = {}
        self._submit_url = "https://api.digen.ai/v1/scene/job/submitv1"
        self._loaded = False

    def _load_session(self):
        if self._loaded:
            return
        if not SECRET.exists():
            raise RuntimeError(f"no grabbed session at {SECRET}")
        data = json.loads(SECRET.read_text(encoding="utf-8"))
        
        exchanges = data.get("recorded_job", {}).get("exchanges", [])
        if not exchanges:
            raise RuntimeError("recorded_job has no exchanges")

        for ex in exchanges:
            h = ex.get("request_headers", {})
            if "Digen-Token" in h:
                for k, v in h.items():
                    if not k.startswith(":") and k.lower() not in _DROP_HDR:
                        self._headers[k] = v
                break
        if not self._headers:
            raise RuntimeError("Could not find Digen-Token in recorded exchanges")
            
        self._headers["accept-encoding"] = "gzip, deflate"

        submit_ex = None
        for ex in exchanges:
            if "submit" in ex.get("url", ""):
                submit_ex = ex
                break
                
        if not submit_ex:
            raise RuntimeError("No submit exchange found in capture")
            
        self._submit_tmpl = json.loads(submit_ex["request_body"])
        self._loaded = True

    def _get_balance(self) -> int:
        self._load_session()
        url = "https://api.digen.ai/v1/credit/remain"
        r = requests.get(url, headers=self._headers, timeout=10)
        r.raise_for_status()
        res = r.json()
        if res.get("errCode") != 0:
            raise RuntimeError(f"credit/remain failed: {res}")
        # Digen usually returns data.remain
        return int(res.get("data", {}).get("remain", 0))

    def normalise(self, req: dict) -> tuple[dict | None, str | None]:
        model = "digen"
        prompt = str(req.get("prompt") or "")
        return {"model": model, "prompt": prompt, "duration": 5, "resolution": 720, "audio": False, "aspect": "16:9"}, None

    def geometry(self, width: int | None, height: int | None) -> dict:
        return {"aspect": "16:9", "resolution": 720}

    def estimate(self, params: dict) -> int:
        return self.est_cost

    def quote(self, acct: vp.Account, params: dict) -> tuple[int | None, str | None]:
        try:
            bal = self._get_balance()
            if bal < self.est_cost:
                return self.est_cost, f"balance {bal} is too low"
            return self.est_cost, None
        except Exception as e:
            return None, f"quote failed: {vp.scrub(e)}"

    def confirm(self, acct: vp.Account, params: dict, max_spend: int | None = None) -> tuple[int | None, str | None]:
        if max_spend is not None and self.est_cost > max_spend:
            return None, f"est_cost {self.est_cost} exceeds max_spend {max_spend}"
        try:
            bal = self._get_balance()
            if bal < self.est_cost:
                return None, f"balance {bal} is too low"
            return self.est_cost, None
        except Exception as e:
            return None, f"confirm failed: {vp.scrub(e)}"

    def probe(self, acct: vp.Account) -> None:
        try:
            bal = self._get_balance()
            acct.credits = bal
            acct.ready, acct.reason, acct.fault = True, "ok", vp.FAULT_NONE
        except Exception as e:
            acct.ready, acct.fault = False, vp.FAULT_AUTH
            acct.reason = f"{type(e).__name__}: {vp.scrub(e)[:160]}"

    def submit(self, acct: vp.Account, params: dict) -> dict:
        self._load_session()
        payload = dict(self._submit_tmpl)
        if "scene_params" in payload:
            sp = json.loads(payload["scene_params"])
            sp["video_gen_prompt"] = params["prompt"]
            # Synthesize idempotency key!
            sp["code"] = f"{time.time_ns()}_{uuid.uuid4()}"
            payload["scene_params"] = json.dumps(sp)

        before = self._get_balance()
        
        r = requests.post(self._submit_url, headers=self._headers, json=payload, timeout=20)
        r.raise_for_status()
        res = r.json()
        if res.get("errCode") != 0:
            raise RuntimeError(f"submit failed: {res}")
            
        queue_id = res.get("data", {}).get("queueId")
        if not queue_id:
            vp.log(f"!! {acct.label}: submit returned no queue_id. Raw: {res}")
            
        try:
            after = self._get_balance()
        except Exception:
            after = None

        return {"items": [queue_id] if queue_id else [], "credits_before": before, "credits_after": after,
                "media_count": 1 if queue_id else 0, "workflow_count": 1 if queue_id else 0,
                "quoted": params.get("quoted")}

    def wait(self, acct: vp.Account, item: str, budget: int, on_status) -> dict:
        self._load_session()
        # Remove hardcoded status=2 filter
        poll_url = "https://api.digen.ai/v1/queue/list?page=0&pageSize=10"
        start_t = time.time()
        
        while time.time() - start_t < budget:
            time.sleep(5)
            try:
                import urllib.parse
                # Digen API might expect a pure GET.
                pr = requests.get(poll_url, headers=self._headers, timeout=10)
                if pr.status_code == 200:
                    pres = pr.json()
                    jobs = pres.get("data", {}).get("list", [])
                    for job in jobs:
                        jid = str(job.get("id")) or str(job.get("jobId"))
                        if jid == str(item):
                            st = job.get("status")
                            if on_status:
                                on_status(f"status {st}")
                            if st == 2:  # done
                                return job
                            if st in (3, 4, -1):  # error states? just an example
                                raise RuntimeError(f"generation failed: status {st}, job: {job}")
            except requests.RequestException:
                pass
                
        raise RuntimeError(f"still not finished after {budget}s")

    def duration_of(self, meta: dict) -> str | None:
        return "5s"  # Digen clips are 5 seconds

    import urllib.request
    def download(self, acct: vp.Account, item: str, meta: dict | None = None) -> pathlib.Path:
        if not meta:
            raise RuntimeError(f"no meta provided for {item}")
        url = meta.get("videoUrl") or meta.get("videoURLV1")
        if not url:
            raise RuntimeError(f"no downloadable url for {item}")
            
        self.out_dir.mkdir(parents=True, exist_ok=True)
        dest = self.out_dir / f"{item}.mp4"
        import urllib.request
        with urllib.request.urlopen(url, timeout=300) as r, dest.open("wb") as fh:
            fh.write(r.read())
        return dest

    def doctor_chain(self, acct: vp.Account, deep: bool = False):
        try:
            bal = self._get_balance()
            yield vp.Step("session auth", True, f"balance {bal}")
        except Exception as e:
            yield vp.Step("session auth", False, str(e))

PROVIDER = vp.register(DigenProvider())

import asyncio
import json
import os
import re
import sys
import time
import urllib.parse
import requests
from typing import Dict, Any, Optional, List
from playwright.async_api import async_playwright

from universal_replay import UniversalSessionClient, SessionExpired, ChatError

STATE_FILE = r"D:\omniroute-monetizer\state\video_accounts.json"

class VideoUniversalSessionClient(UniversalSessionClient):
    """
    Dedicated HTTP Replay Adapter for Video Generation Providers.
    Transforms video generation JSON payloads (mapping prompt, aspect_ratio, duration),
    submits job requests, and polls job status endpoints until completion to extract the MP4/WebM URL.
    """
    PROMPT_KEYS = [
        "prompt", "video_gen_prompt", "input_prompt", "text", "description",
        "video_prompt", "user_prompt", "query", "input_text"
    ]
    
    JOB_ID_KEYS = [
        "queueId", "queue_id", "job_id", "jobId", "taskId", "task_id",
        "id", "generation_id", "generationId", "work_id", "workId"
    ]
    
    VIDEO_URL_KEYS = [
        "video_url", "videoUrl", "url", "mp4_url", "mp4Url", "result_url",
        "resultUrl", "downloadUrl", "download_url", "video_path", "play_url"
    ]

    def __init__(self, secret, timeout: int = 1800):
        # 1800s (30min), NOT 120s. History: the synchronous oioi pipeline generated video fine and
        # failed ONLY on a timeout mid-stage. Moving to async /v1/video/jobs fixes the HTTP timeout
        # (the face returns 202 immediately), but the ceiling would just move DOWN here -- a 120s
        # poll budget is far below a real multi-minute render, so every clip would report
        # "timed out" while the provider was still working, and oioi would retry a live job forever.
        # The async face is what makes a long ceiling safe: nothing is holding a socket open.
        super().__init__(secret)
        self.timeout = timeout

    def _transform_video_payload(self, new_prompt: str, aspect_ratio: str = "16:9", duration: int = 5) -> str:
        if not self.base_body:
            return ""
            
        body = self.base_body
        
        # 1. Try JSON object manipulation if body is valid JSON
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                # Handle nested stringified JSON like scene_params in Digen
                if "scene_params" in payload and isinstance(payload["scene_params"], str):
                    try:
                        sp = json.loads(payload["scene_params"])
                        sp["video_gen_prompt"] = new_prompt
                        payload["scene_params"] = json.dumps(sp)
                    except Exception:
                        pass
                
                # Top level replacement
                replaced = False
                for pk in self.PROMPT_KEYS:
                    if pk in payload:
                        payload[pk] = new_prompt
                        replaced = True
                
                if not replaced:
                    payload["prompt"] = new_prompt
                    
                if "aspect_ratio" in payload:
                    payload["aspect_ratio"] = aspect_ratio
                if "aspectRatio" in payload:
                    payload["aspectRatio"] = aspect_ratio
                if "duration" in payload:
                    payload["duration"] = duration
                    
                return json.dumps(payload)
        except Exception:
            pass
            
        # 2. Fallback to generic prompt injection from UniversalSessionClient
        return self._inject_prompt(new_prompt)

    def _extract_job_id(self, data: Any) -> Optional[str]:
        if isinstance(data, dict):
            for k in self.JOB_ID_KEYS:
                if k in data and data[k]:
                    return str(data[k])
            # Check nested data/result object
            for sub in ("data", "result", "job", "task", "output"):
                if sub in data and isinstance(data[sub], dict):
                    res = self._extract_job_id(data[sub])
                    if res:
                        return res
        elif isinstance(data, str):
            for k in self.JOB_ID_KEYS:
                m = re.search(rf'"{k}"\s*:\s*"([^"]+)"', data)
                if m:
                    return m.group(1)
                m_num = re.search(rf'"{k}"\s*:\s*(\d+)', data)
                if m_num:
                    return m_num.group(1)
        return None

    def _extract_video_url(self, data: Any) -> Optional[str]:
        if isinstance(data, dict):
            for k in self.VIDEO_URL_KEYS:
                v = data.get(k)
                if isinstance(v, str) and (v.startswith("http://") or v.startswith("https://") or v.endswith(".mp4") or v.endswith(".webm")):
                    return v
            # Check list or nested objects
            for sub in ("data", "result", "list", "output", "videos", "files"):
                val = data.get(sub)
                if isinstance(val, dict):
                    res = self._extract_video_url(val)
                    if res:
                        return res
                elif isinstance(val, list):
                    for item in val:
                        res = self._extract_video_url(item)
                        if res:
                            return res
        elif isinstance(data, str):
            m = re.search(r'https?://[^\s"}]+\.(?:mp4|webm|mov)(?:\?[^\s"}]*)?', data, re.IGNORECASE)
            if m:
                return m.group(0)
        return None

    def poll_job_status(self, poll_url: str, job_id: str) -> str:
        start_t = time.time()
        s = requests.Session()
        
        while time.time() - start_t < self.timeout:
            time.sleep(4)
            try:
                # Format job_id into poll URL if placeholder exists
                target_url = poll_url.replace("{job_id}", job_id).replace("{id}", job_id).replace("{queue_id}", job_id)
                r = s.get(target_url, headers=self.headers, timeout=15)
                if r.status_code == 200:
                    try:
                        res_data = r.json()
                    except Exception:
                        res_data = r.text
                        
                    video_url = self._extract_video_url(res_data)
                    if video_url:
                        return video_url
            except Exception:
                pass
                
        raise ChatError("TIMEOUT", f"Video generation timed out after {self.timeout}s for job {job_id}")

    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None, **kw) -> Dict[str, Any]:
        if not messages:
            raise ChatError("NO_MESSAGES", "no messages provided")
            
        new_prompt = messages[-1]["content"]
        aspect_ratio = kw.get("aspect_ratio", "16:9")
        duration = kw.get("duration", 5)
        
        new_body_str = self._transform_video_payload(new_prompt, aspect_ratio=aspect_ratio, duration=duration)
        
        if str(self.method).upper() in ("POST", "PUT", "PATCH") and not new_body_str:
            raise ChatError("EMPTY_BODY", f"No replayable request body for video provider {self.raw.get('host')}")
            
        try:
            req_kwargs = {
                "headers": self.headers,
                "timeout": 60
            }
            if self.base_body:
                req_kwargs["data"] = new_body_str.encode("utf-8")
                
            r = requests.request(self.method, self.url, **req_kwargs)
            if r.status_code in (401, 403):
                raise SessionExpired("Auth rejected: " + r.text[:100])
            r.raise_for_status()
            
            try:
                res_data = r.json()
            except Exception:
                res_data = r.text
                
            # 1. Direct video URL in response
            video_url = self._extract_video_url(res_data)
            if video_url:
                return {
                    "text": video_url,
                    "label": self.raw.get("host", "video-provider"),
                    "status": "completed"
                }
                
            # 2. Extract job ID and poll if poll URL available in exchange/recorded job
            job_id = self._extract_job_id(res_data)
            poll_url = self.raw.get("poll_url") or self.raw.get("status_url")
            
            if not poll_url and isinstance(self.raw.get("recorded_job"), dict):
                exchanges = self.raw["recorded_job"].get("exchanges", [])
                for ex in exchanges:
                    u = ex.get("url", "")
                    if u != self.url and ("status" in u or "list" in u or "detail" in u or "query" in u):
                        poll_url = u
                        break
                        
            if job_id and poll_url:
                final_video_url = self.poll_job_status(poll_url, job_id)
                return {
                    "text": final_video_url,
                    "label": self.raw.get("host", "video-provider"),
                    "status": "completed"
                }
                
            # Fallback text representation if response returned OK
            if isinstance(res_data, dict):
                text_out = json.dumps(res_data)
            else:
                text_out = str(res_data)
                
            return {
                "text": text_out,
                "label": self.raw.get("host", "video-provider"),
                "status": "submitted"
            }
            
        except requests.exceptions.RequestException as e:
            raise ChatError("HTTP_ERROR", str(e))

async def generate_video(prompt, target_provider="flow"):
    # 1. Load accounts
    if not os.path.exists(STATE_FILE):
        print(f"[-] Error: {STATE_FILE} not found.")
        return False
        
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # 2. Find a healthy account for this provider
    account = None
    for acct in data.get("accounts", []):
        if acct.get("provider") == target_provider and acct.get("health") == "green":
            account = acct
            break
            
    if not account:
        print(f"[-] Error: No healthy '{target_provider}' accounts available.")
        return False
        
    port = account["port"]
    url = account.get("url")
    label = account["label"]
    
    if not url:
        print(f"[-] Error: Account {label} has no project URL saved.")
        return False
        
    print(f"[+] Routing to {label} (Port: {port})")
    
    async with async_playwright() as p:
        try:
            print(f"[+] Connecting to CDP on port {port}...")
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0]
            
            # Find or open the target URL
            page = None
            for p_tab in context.pages:
                if target_provider == "flow" and "labs.google/fx/tools/flow" in p_tab.url:
                    page = p_tab
                    break
            
            if not page:
                page = context.pages[0]
                
            print(f"[+] Navigating to {url}")
            await page.goto(url, wait_until="load")
            await page.wait_for_timeout(3000)
            
            if target_provider == "flow":
                # Use Shadow DOM traversal to find the textarea and submit button
                js_inject = """
                (promptText) => {
                    const getShadows = (root) => {
                        let shadows = [];
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                        let node;
                        while (node = walker.nextNode()) {
                            if (node.shadowRoot) {
                                shadows.push(node.shadowRoot);
                                shadows = shadows.concat(getShadows(node.shadowRoot));
                            }
                        }
                        return shadows;
                    };
                    
                    const roots = [document].concat(getShadows(document));
                    let textarea = null;
                    let submitBtn = null;
                    
                    for (const root of roots) {
                        if (!textarea) {
                            const tas = root.querySelectorAll('textarea');
                            for (const ta of tas) {
                                textarea = ta;
                                break;
                            }
                        }
                        if (!submitBtn) {
                            const btns = root.querySelectorAll('button');
                            for (const b of btns) {
                                let label = (b.getAttribute('aria-label') || '').toLowerCase();
                                let text = (b.innerText || b.textContent || '').toLowerCase();
                                if (label.includes('generate') || label.includes('create') || text.includes('generate')) {
                                    submitBtn = b;
                                    break;
                                }
                            }
                        }
                    }
                    
                    if (textarea && submitBtn) {
                        textarea.value = promptText;
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                        
                        setTimeout(() => {
                            submitBtn.click();
                        }, 500);
                        return "SUCCESS";
                    }
                    
                    return `Missing elements. Textarea: ${!!textarea}, Button: ${!!submitBtn}`;
                }
                """
                
                print(f"[+] Injecting prompt: '{prompt}'")
                result = await page.evaluate(js_inject, prompt)
                print(f"[+] Injection Result: {result}")
                
                if result == "SUCCESS":
                    print("[+] Video generation triggered successfully!")
                
            await page.wait_for_timeout(2000)
            await browser.close()
            return True
            
        except Exception as e:
            print(f"[-] Playwright Error: {e}")
            return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python video_universal_replay.py <provider: flow|veo> <prompt>")
        sys.exit(1)
        
    provider = sys.argv[1].lower()
    prompt = sys.argv[2]
    
    asyncio.run(generate_video(prompt, provider))

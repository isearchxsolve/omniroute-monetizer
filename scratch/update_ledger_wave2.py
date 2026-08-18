import json, time, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "state" / "all_296_providers_execution_ledger.json"

ts = time.strftime("%Y%m%d-%H%M%S")
backup = LEDGER.with_suffix(f".json.bak-124-{ts}")
shutil.copy2(LEDGER, backup)
print("backup ->", backup.name)

d = json.loads(LEDGER.read_text(encoding="utf-8"))
ps = d["providers"] if isinstance(d, dict) and "providers" in d else d

updates = {
    "chatgpt-web": ("LIVE", "LIVE", "E2E HTTP 200 real content 'OK' on gpt-5.5/gpt-5.6-thinking/o3; test valid=true. conn 8ae51957."),
    "grok-web": ("AUTHENTICATED_CLOUDFLARE_TLS_BLOCKED", "AUTHENTICATED_CLOUDFLARE_TLS_BLOCKED", "Real Google SSO login; sso+sso-rw+cf_clearance harvested+injected (conn 142fea8e) but 403 anti-bot/502 persists. Executor TLS profile chrome_146 != browser Chrome 151 that earned cf_clearance (JA3 pin). Upstream limitation."),
    "veoaifree-web": ("NOT_CHAT_COMPLETABLE", "NOT_CHAT_COMPLETABLE", "serviceKinds=[video], noAuth. text-to-video/image/TTS via admin-ajax.php, not chat completions."),
    "suno": ("NOT_CHAT_COMPLETABLE", "NOT_CHAT_COMPLETABLE", "Music generation; no suno.ts executor in open-sse/executors."),
    "udio": ("NOT_CHAT_COMPLETABLE", "NOT_CHAT_COMPLETABLE", "Music generation; no udio.ts executor in open-sse/executors."),
    "microsoft-designer-web": ("NOT_CHAT_COMPLETABLE", "NOT_CHAT_COMPLETABLE", "DallE image generation (DallE.ashx), not chat completions."),
    "adapta-web": ("BLOCKED_NO_GOOGLE_SSO", "BLOCKED_NO_GOOGLE_SSO", "agent.adapta.one/sign-in = email/password (Clerk) + passkey only. No Google SSO. Needs Adapta creds."),
    "yuanbao-web": ("BLOCKED_WECHAT_QR", "BLOCKED_WECHAT_QR", "yuanbao.tencent.com login = WeChat QR scan. No Google SSO. Needs human WeChat scan."),
    "codebuddy-cn": ("BLOCKED_WECHAT_QR", "BLOCKED_WECHAT_QR", "copilot.tencent.com -> codebuddy.cn login = Tencent WeChat QR. No Google SSO. Needs WeChat scan."),
    "zed-hosted": ("NEEDS_ZED_OAUTH_IMPORT", "NEEDS_ZED_OAUTH_IMPORT", "zedAuth.ts requires RSA-encrypted OAuth import (native-app callback user_id+access_token), not cookie harvest. zed.dev/sign_in -> GitHub OAuth."),
}

for slug, (status, cls, note) in updates.items():
    if slug not in ps:
        print(f"MISSING in ledger: {slug}")
        continue
    e = ps[slug]
    e["status"] = status
    e["classification"] = cls
    e["note"] = note
    e["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    e["worklog_entry"] = 124
    print(f"updated {slug} -> {status}")

LEDGER.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
print("ledger saved")

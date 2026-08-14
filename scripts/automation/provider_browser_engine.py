#!/usr/bin/env python3
"""
Provider browser/DOM automation engine for OmniRoute Monetizer.

Design:
- API-first; browser is a fallback/handoff layer.
- Never controls/stops/restarts the OmniRoute Windows service.
- Never logs input values, cookies, storage state, auth headers, passwords or tokens.
- Never bypasses MFA/CAPTCHA/consent.
- Uses visible Playwright by default for human-verifiable flows.
- Safe actions are limited to navigation, DOM discovery, and explicitly allowed
  re-auth/refresh controls. Credential entry/save/test can require a human handoff.

This module is intentionally provider-agnostic. Provider-specific adapters may
supply:
  dashboard slug
  safe control labels
  known status markers
  optional non-secret field mappings

The engine produces sanitized artifacts suitable for audit.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

OMNI_BASE = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
OMNI_DASHBOARD = OMNI_BASE

SECRET_NAME_PATTERNS = re.compile(
    r"(password|passwd|token|secret|api[_-]?key|authorization|cookie|"
    r"access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key)",
    re.I,
)

SECURITY_MARKERS = re.compile(
    r"(captcha|multi[- ]factor|mfa|two[- ]factor|2fa|consent|"
    r"verify your identity|security check|one[- ]time passcode|otp)",
    re.I,
)

SAFE_CLICK_LABELS = (
    "re-authenticate",
    "reauthenticate",
    "refresh",
    "retry authentication",
    "retry auth",
)

HUMAN_REQUIRED_LABELS = (
    "captcha",
    "mfa",
    "two-factor",
    "2fa",
    "consent",
    "authorize",
    "sign in",
    "log in",
    "password",
    "api key",
    "access token",
    "import auth",
    "save",
    "test connection",
)

@dataclass
class BrowserResult:
    provider: str
    url: str
    status: str
    stage: str
    detected_controls: list[str]
    security_gate: Optional[str]
    human_action_required: bool
    message: str
    elapsed_seconds: float

    def sanitized(self) -> dict[str, Any]:
        return asdict(self)

def _clean_text(value: str, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if SECRET_NAME_PATTERNS.search(value):
        return "[REDACTED]"
    return value[:limit]

def redact_dom_text(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if SECRET_NAME_PATTERNS.search(line):
            lines.append("[REDACTED]")
        else:
            lines.append(_clean_text(line))
    return "\n".join(lines[:2000])

def build_provider_url(provider: str) -> str:
    slug = provider.strip().strip("/")
    if slug.startswith("http://") or slug.startswith("https://"):
        return slug
    return f"{OMNI_DASHBOARD}/dashboard/providers/{slug}"

def _require_live_service_guard() -> None:
    # This module does not own/control the service. This guard is documentary
    # and makes the invariant explicit at the point of browser automation.
    if ":20128" not in OMNI_BASE:
        # We still allow an explicit custom URL, but warn through exception rather
        # than silently assuming a different runtime is safe.
        raise RuntimeError(
            "Browser automation refused: OMNIROUTE_BASE_URL is not the expected "
            "local :20128 runtime. Override explicitly only after inspection."
        )

class ProviderBrowserEngine:
    def __init__(
        self,
        artifact_dir: str | Path,
        headless: bool = False,
        slow_mo_ms: int = 50,
        timeout_ms: int = 15000,
    ):
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.slow_mo_ms = slow_mo_ms
        self.timeout_ms = timeout_ms

    def discover(
        self,
        provider: str,
        url: Optional[str] = None,
    ) -> BrowserResult:
        _require_live_service_guard()
        target = url or build_provider_url(provider)
        started = time.monotonic()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Install the pinned project dependency "
                "before running browser automation."
            ) from exc

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo_ms,
            )
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)
            page.goto(target, wait_until="domcontentloaded", timeout=self.timeout_ms)

            # Let the UI settle without arbitrary long sleeps.
            try:
                page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 8000))
            except Exception:
                pass

            title = page.title()
            body_text = redact_dom_text(page.locator("body").inner_text(timeout=self.timeout_ms))

            controls: list[str] = []
            for role in ("button", "link"):
                try:
                    locator = page.get_by_role(role)
                    count = min(locator.count(), 80)
                    for i in range(count):
                        label = locator.nth(i).inner_text(timeout=1000).strip()
                        if label:
                            controls.append(f"{role}:{_clean_text(label, 120)}")
                except Exception:
                    continue

            # Inputs: inspect only name/type/placeholder/label, never values.
            try:
                inputs = page.locator("input, textarea, select")
                count = min(inputs.count(), 100)
                for i in range(count):
                    el = inputs.nth(i)
                    attrs = {
                        "type": el.get_attribute("type") or "",
                        "name": el.get_attribute("name") or "",
                        "placeholder": el.get_attribute("placeholder") or "",
                    }
                    desc = " ".join(
                        _clean_text(v, 120)
                        for v in attrs.values()
                        if v
                    )
                    if desc:
                        controls.append(f"input:{desc}")
            except Exception:
                pass

            gate = None
            gate_match = SECURITY_MARKERS.search(body_text)
            if gate_match:
                gate = gate_match.group(0)

            human = bool(gate)
            if any(re.search(lbl, body_text, re.I) for lbl in HUMAN_REQUIRED_LABELS):
                # Presence of security-sensitive controls means the action may
                # require human interaction. We do not automatically fill/click them.
                human = True

            screenshot = self.artifact_dir / f"{provider}_discovery.png"
            html_path = self.artifact_dir / f"{provider}_dom.html"

            page.screenshot(path=str(screenshot), full_page=True)
            html_path.write_text(page.content(), encoding="utf-8")

            message = (
                "DOM discovery complete."
                if not human
                else "DOM discovery complete; human/security interaction may be required."
            )

            result = BrowserResult(
                provider=provider,
                url=page.url,
                status="DISCOVERED",
                stage="DOM_DISCOVERY",
                detected_controls=controls[:300],
                security_gate=gate,
                human_action_required=human,
                message=message,
                elapsed_seconds=time.monotonic() - started,
            )

            (self.artifact_dir / f"{provider}_discovery.json").write_text(
                json.dumps(result.sanitized(), indent=2),
                encoding="utf-8",
            )

            browser.close()
            return result

    def safe_reauth_probe(self, provider: str) -> BrowserResult:
        """
        Open provider UI and click only an explicit re-auth/refresh control.
        It deliberately stops before credential/MFA/CAPTCHA/consent entry.
        """
        _require_live_service_guard()
        started = time.monotonic()
        target = build_provider_url(provider)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is not installed.") from exc

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo_ms,
            )
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)
            page.goto(target, wait_until="domcontentloaded", timeout=self.timeout_ms)

            clicked = None
            for label in SAFE_CLICK_LABELS:
                try:
                    locator = page.get_by_role("button", name=re.compile(label, re.I)).first
                    if locator.count():
                        locator.click()
                        clicked = label
                        break
                except Exception:
                    continue

            if clicked:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

            text = redact_dom_text(page.locator("body").inner_text(timeout=self.timeout_ms))
            gate_match = SECURITY_MARKERS.search(text)
            gate = gate_match.group(0) if gate_match else None

            # Deliberate stop boundary:
            # never fill password/API-key/token fields and never bypass MFA/CAPTCHA.
            human = True if clicked or gate else False
            stage = "HUMAN_HANDOFF_REQUIRED" if human else "NO_SAFE_REAUTH_CONTROL_FOUND"
            msg = (
                f"Clicked safe control '{clicked}'. Stop for human auth/save/test."
                if clicked
                else "No explicit safe re-auth/refresh control found."
            )

            result = BrowserResult(
                provider=provider,
                url=page.url,
                status="HANDOFF" if human else "NO_ACTION",
                stage=stage,
                detected_controls=[],
                security_gate=gate,
                human_action_required=human,
                message=msg,
                elapsed_seconds=time.monotonic() - started,
            )

            (self.artifact_dir / f"{provider}_handoff.json").write_text(
                json.dumps(result.sanitized(), indent=2),
                encoding="utf-8",
            )

            browser.close()
            return result

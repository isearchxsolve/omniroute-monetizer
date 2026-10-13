'''cdp_first_graduation.py - CDP-FIRST ORCHESTRATOR (new architecture, 2026-10-12).

Phase pipeline over the gate-OK targets ONLY:
  PHASE 1 batch auth  - cdp_sso.py per provider, verified per session.
  PHASE 2 cdp capture - capture_websocket_cdp.py (Network reload capture).
  PHASE 3 replay      - replay_check.py per blueprint (python adapter).
  PHASE 4 receipts    - graduation_receipts.jsonl rows with lane.
Resumable state: war-log/cdp-first-state.json
'''
import argparse
import json
import os
import subprocess
import sys
import time

AUTOMATION = r'D:\omniroute-monetizer\scripts\automation'
STATE = r'd:\anonym\war-log\cdp-first-state.json'
LEDGER = r'd:\anonym\war-log\graduation_receipts.jsonl'
PY = sys.executable


def load_state():
    try:
        with open(STATE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    # ATOMIC: never truncate-then-write (a kill mid-save zeroed the file 2026-10-13).
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE)


def run_tool(args, timeout):
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, encoding='utf-8', errors='replace')
        return (p.stdout or '') + '\n' + (p.stderr or '')
    except Exception as e:
        return 'TOOL_ERROR: ' + repr(e)[:200]


def phase_auth(t, st):
    pid = t['provider_id']
    print('  [AUTH] ' + pid, flush=True)
    out = run_tool([PY, AUTOMATION + r'\cdp_sso.py', '--port', '9222',
                    '--url', t.get('login_url') or ('https://' + t['host']),
                    '--match', (t['host'] or pid)[:40]], 220)
    done = 'SSO_DONE' in out
    note = 'silent'
    rows = [ln for ln in out.splitlines() if ln.strip()]
    if rows:
        note = rows[-1][:120]
    for ln in rows:
        if ln.startswith('VERDICT:'):
            note = ln[:160]
    st[pid] = dict(st.get(pid) or {}, phase=2 if done else 1,
                   auth='SSO_DONE' if done else note)
    return done


def phase_capture(t, st):
    pid = t['provider_id']
    print('  [CAPTURE] ' + pid, flush=True)
    out = run_tool([PY, AUTOMATION + r'\capture_websocket_cdp.py', '--port', '9222',
                    '--match', (t['host'] or pid)[:40], '--name', pid], 300)
    ok = 'CAPTURED' in out
    st[pid] = dict(st.get(pid) or {}, phase=3 if ok else 2,
                   capture='CAPTURED' if ok else out[-160:].replace('\n', ' '))
    return ok


def phase_replay(t, st):
    pid = t['provider_id']
    print('  [REPLAY] ' + pid, flush=True)
    out = run_tool([PY, AUTOMATION + r'\replay_check.py', '--only', pid], 300)
    ok = 'REPLAY_OK' in out
    verdict = 'REPLAY_OK' if ok else 'not_ok'
    for v in ('NO_ANSWER', 'BAD_FILE', 'AUTH', 'WALL', 'SINGLE_USE', 'RATE'):
        if v in out:
            verdict = v
            break
    st[pid] = dict(st.get(pid) or {}, phase=4 if ok else 3, replay=verdict)
    return ok, verdict


def receipt(t, st, verdict):
    row = {'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'provider_id': t['provider_id'], 'provider_name': t.get('name'),
           'graduated': verdict == 'REPLAY_OK', 'auth_verified': True,
           'lane': 'cdp_first', 'replay': verdict,
           'account': 'isearch.xsolve@gmail.com'}
    with open(LEDGER, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gate', required=True, help='target-gate jsonl (OK rows used)')
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    ok_rows = []
    with open(a.gate, 'r', encoding='utf-8') as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get('verdict') == 'OK':
                ok_rows.append(r)
    if a.limit:
        ok_rows = ok_rows[:a.limit]
    print('CDP-FIRST pipeline over %d gate-OK targets' % len(ok_rows), flush=True)
    import os
    _px = dict((k, os.environ[k]) for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy',
                                          'https_proxy', 'ALL_PROXY', 'all_proxy')
               if os.environ.get(k))
    print('env proxies: ' + (repr(_px) if _px else 'none')
          + ' (localhost calls are proxy-free regardless)', flush=True)
    st = load_state()
    for t in ok_rows:
        pid = t['provider_id']
        cur = st.get(pid) or {}
        ph = cur.get('phase', 1)
        if ph >= 4 or cur.get('replay') == 'REPLAY_OK':
            print('skip ' + pid + ' (done)', flush=True)
            continue
        print('[%s] phase %d' % (pid, ph), flush=True)
        if not ensure_cdp_chrome():
            print('CDP Chrome unavailable - pausing pass.', flush=True)
            time.sleep(30)
            continue
        if ph < 2:
            phase_auth(t, st)
            save_state(st)
        if st.get(pid, {}).get('phase', 1) >= 2:
            phase_capture(t, st)
            save_state(st)
        if st.get(pid, {}).get('phase', 1) >= 3:
            ok, verdict = phase_replay(t, st)
            save_state(st)
            receipt(t, st, verdict)
    print('PIPELINE PASS COMPLETE', flush=True)






def ensure_cdp_chrome():
    '''9222 health check. Proxy-free (env proxies poison localhost - 2026-10-13),
    retried, and LOUD: a silent false-negative cost two full passes of nothing.'''
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last = ''
    for _attempt in range(3):
        try:
            opener.open('http://127.0.0.1:9222/json/version', timeout=6).read()
            return True
        except Exception as e:
            last = repr(e)[:200]
            time.sleep(4)
    print('  [HEAL] CDP Chrome down - supervisor owns the relaunch. last-error: '
          + last, flush=True)
    return False

if __name__ == '__main__':
    main()

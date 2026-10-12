import json
import base64
import subprocess
import os

def solve_deepseek_pow(pow_challenge_json_str) -> str:
    """
    Takes a JSON string representing the DeepSeekHashV1 challenge,
    solves it using the Node.js headless solver, and returns the base64-encoded
    response header ready for x-ds-pow-response.
    """
    try:
        challenge_data = json.loads(pow_challenge_json_str)
    except Exception as e:
        if isinstance(pow_challenge_json_str, dict):
            challenge_data = pow_challenge_json_str
        else:
            raise e
            
    salt = challenge_data.get("salt")
    challenge = challenge_data.get("challenge")
    
    if not salt or not challenge:
        raise ValueError("Missing 'salt' or 'challenge' in PoW payload.")
        
    # Paths for Node executable and our JS solver script
    import shutil
    default_node = r"D:\DOWNLOADS\node-v24.18.0-win-x64\node-v24.18.0-win-x64\node.exe"
    node_exe = default_node if os.path.exists(default_node) else (shutil.which("node") or "node")
    solver_script = os.path.join(os.path.dirname(__file__), "ds_pow_solver.js")
    
    # Run the Node script synchronously (it prints the JSON answer to stdout)
    res = subprocess.run(
        [node_exe, solver_script, json.dumps(challenge_data)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    
    if res.returncode != 0:
        raise ValueError(f"PoW solver failed: {res.stderr}")
        
    # Extract the answer JSON from stdout
    output = res.stdout.strip()
    try:
        solved_payload = json.loads(output)
        answer = solved_payload.get("answer", {}).get("answer")
        if answer is None:
            raise ValueError("No answer field in output")
    except Exception as e:
        raise ValueError(f"Failed to parse Node solver output: {output}, Error: {e}")
        
    response_obj = {
        "algorithm": "DeepSeekHashV1",
        "challenge": challenge,
        "salt": salt,
        "answer": answer,
        "signature": challenge_data.get("signature", ""),
        "target_path": challenge_data.get("target_path", "/api/v0/chat/completion")
    }
    
    # Must serialize closely to what the server expects: no spaces
    json_str = json.dumps(response_obj, separators=(',', ':'))
    return base64.b64encode(json_str.encode('utf-8')).decode('utf-8')


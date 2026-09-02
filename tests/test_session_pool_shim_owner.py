from pathlib import Path

from scripts.automation.session_pool_shim_owner import is_owned_shim_process


SCRIPT = Path(r"D:\omniroute-monetizer\scripts\automation\session_pool_shim.py")


def test_matches_exact_launcher_and_base_interpreter_argv() -> None:
    assert is_owned_shim_process(
        "python.exe",
        [
            r"D:\omniroute-monetizer\.venv\Scripts\python.exe",
            "-u",
            str(SCRIPT),
            "8190",
        ],
        8190,
        shim_script=SCRIPT,
    )
    assert is_owned_shim_process(
        "python.exe",
        [
            r"C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe",
            "-u",
            str(SCRIPT),
            "8190",
        ],
        8190,
        shim_script=SCRIPT,
    )


def test_rejects_foreign_processes_paths_and_ports() -> None:
    good = ["python.exe", "-u", str(SCRIPT), "8190"]
    assert not is_owned_shim_process(
        "powershell.exe", good, 8190, shim_script=SCRIPT
    )
    assert not is_owned_shim_process(
        "python.exe", ["python.exe", str(SCRIPT), "8189"], 8190, shim_script=SCRIPT
    )
    assert not is_owned_shim_process(
        "python.exe",
        ["python.exe", r"D:\foreign\session_pool_shim.py", "8190"],
        8190,
        shim_script=SCRIPT,
    )
    assert not is_owned_shim_process(
        "python.exe",
        ["python.exe", str(SCRIPT), "--port", "8190"],
        8190,
        shim_script=SCRIPT,
    )
    assert not is_owned_shim_process("python.exe", None, 8190, shim_script=SCRIPT)

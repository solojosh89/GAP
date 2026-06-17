"""GAP sandbox runner.

Runs a generated script in a throwaway working directory with a hard time limit,
captures its output, and contains the damage if the script misbehaves.

WHAT IS CONTAINED (proven by tests/test_sandbox_safety.py):
  - Runaway time          -> hard timeout.
  - Crashes               -> captured, not propagated.
  - Orphaned child procs  -> the WHOLE process tree is killed, not just the
                             direct child (Windows Job Object / POSIX process group).
  - Memory exhaustion     -> per-job memory cap; an over-allocating script is
                             killed instead of taking the host down.
  - Fork bombs            -> active-process cap inside the job.

WHAT IS STILL **NOT** CONTAINED (honest limit -- do not claim otherwise):
  - Filesystem access. A script can still read/write/delete files it has rights
    to (absolute paths included). A Job Object does NOT jail the filesystem.
  - Network access. Sockets are not blocked.
  True filesystem/network isolation needs an OS-level jail (Windows AppContainer,
  a container, or a separate low-privilege user). That is the remaining job and
  is why app.py binds to localhost only.
"""
from __future__ import annotations
import os
import subprocess
import sys
import time

from .contract import RunResult

# Defaults: generous enough for honest proofs, tight enough to protect the host.
_DEFAULT_MEMORY_MB = 512
_DEFAULT_MAX_PROCESSES = 16


def _minimal_env() -> dict:
    # Enough for Python to start, not the parent's full environment.
    return {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),   # Python needs this on Windows
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_script(entry_name: str, workdir: str, timeout_s: float = 10.0,
               memory_mb: int = _DEFAULT_MEMORY_MB,
               max_processes: int = _DEFAULT_MAX_PROCESSES) -> RunResult:
    """Run `python <entry_name>` inside workdir, contained, with a hard timeout."""
    if sys.platform == "win32":
        return _run_windows(entry_name, workdir, timeout_s, memory_mb, max_processes)
    return _run_posix(entry_name, workdir, timeout_s, memory_mb, max_processes)


# --------------------------------------------------------------------------- #
# Windows: contain the child in a Job Object (kill-on-close + memory/process caps).
# --------------------------------------------------------------------------- #
def _run_windows(entry_name, workdir, timeout_s, memory_mb, max_processes) -> RunResult:
    import ctypes
    from ctypes import wintypes

    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9

    ULONG_PTR = ctypes.c_size_t

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ULONG_PTR),
                    ("MaximumWorkingSetSize", ULONG_PTR),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ULONG_PTR),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ULONG_PTR),
                    ("JobMemoryLimit", ULONG_PTR),
                    ("PeakProcessMemoryUsed", ULONG_PTR),
                    ("PeakJobMemoryUsed", ULONG_PTR)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                            wintypes.LPVOID, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    job = k32.CreateJobObjectW(None, None)

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE      # closing the job kills the whole tree
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS       # cap process count (fork bombs)
        | JOB_OBJECT_LIMIT_PROCESS_MEMORY       # cap per-process memory (OOM)
    )
    info.BasicLimitInformation.ActiveProcessLimit = max_processes
    info.ProcessMemoryLimit = memory_mb * 1024 * 1024
    k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                ctypes.byref(info), ctypes.sizeof(info))

    start = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, entry_name],
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_minimal_env(),
    )
    # Assign immediately. CPython interpreter startup (tens of ms) far outlasts
    # this call (microseconds), so the child is in the job before any user code
    # (the imported `target`) runs.
    k32.AssignProcessToJobObject(job, int(proc._handle))

    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout_s)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        k32.TerminateJobObject(job, 1)   # kill the entire tree, not just the child
        proc.kill()
        out, err = proc.communicate()
        code = None
        err = (err or "") + "\n[sandbox] killed: exceeded time limit"
    finally:
        # Closing the job handle enforces KILL_ON_JOB_CLOSE: any survivor dies here.
        k32.CloseHandle(job)

    return RunResult(
        exit_code=code,
        stdout=out or "",
        stderr=err or "",
        timed_out=timed_out,
        duration_s=time.monotonic() - start,
    )


# --------------------------------------------------------------------------- #
# POSIX: own process group + rlimits; kill the group on timeout.
# --------------------------------------------------------------------------- #
def _run_posix(entry_name, workdir, timeout_s, memory_mb, max_processes) -> RunResult:
    import signal

    def _limits():
        import resource
        soft = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (soft, soft))           # memory cap
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (max_processes, max_processes))
        except (ValueError, OSError):
            pass

    start = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, entry_name],
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_minimal_env(),
        start_new_session=True,        # child leads its own process group
        preexec_fn=_limits,
    )
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout_s)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)   # kill the whole group
        except ProcessLookupError:
            pass
        out, err = proc.communicate()
        code = None
        err = (err or "") + "\n[sandbox] killed: exceeded time limit"

    return RunResult(
        exit_code=code,
        stdout=out or "",
        stderr=err or "",
        timed_out=timed_out,
        duration_s=time.monotonic() - start,
    )

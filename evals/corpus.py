"""GAP validation corpus — the ground-truth eval set.

Two kinds of sample:
  - has_bug=True  : contains ONE real, provable bug. A working engine should FIND
                    and PROVE it (true positive).
  - has_bug=False : genuinely correct AND robust (no crash on any reasonable input).
                    A working engine should stay SILENT — confidence 'none', nothing
                    proven. Surfacing a "proven" bug here is a FALSE POSITIVE, the
                    single most damaging failure for a prove-don't-assert tool.

The clean samples are the real test. Anyone can find bugs in buggy code; the thesis
GAP must defend is that it does NOT invent bugs in correct code.

All Python for Floor 1 (the sandbox runs Python; node routing is future work).
Expand freely — more samples = a stronger verdict.
"""

SAMPLES = [
    # ─────────────── BUGGY (provable) ───────────────
    {
        "name": "migrate_count",
        "language": "python",
        "has_bug": True,
        "note": "counts attempts, not inserts (migrated += 1 outside the if)",
        "code": (
            "def migrate(rows, destination):\n"
            "    migrated = 0\n"
            "    for key, value in rows:\n"
            "        if key not in destination:\n"
            "            destination[key] = value\n"
            "        migrated += 1\n"
            "    return migrated\n"
        ),
        # Behavioural oracle: the CORRECT contract on in-domain input. 'a' is a
        # duplicate (already present once) -> must be skipped -> real inserts = 2.
        "smoke": (
            "import target\n"
            "n = target.migrate([('a', 1), ('a', 2), ('b', 3)], {})\n"
            "print('GAP_SMOKE:OK' if n == 2 else 'GAP_SMOKE:FAIL %r' % (n,))\n"
        ),
    },
    {
        "name": "count_passing",
        "language": "python",
        "has_bug": True,
        "note": "returns total count, ignores the threshold entirely",
        "code": (
            "def count_passing(scores, threshold):\n"
            "    passed = 0\n"
            "    for s in scores:\n"
            "        passed += 1\n"
            "    return passed\n"
        ),
        # Correct: count scores meeting the threshold. Inputs avoid the == boundary
        # so a >= vs > fix both score 2 (robust to that reasonable ambiguity).
        "smoke": (
            "import target\n"
            "n = target.count_passing([10, 20, 30, 5], 15)\n"
            "print('GAP_SMOKE:OK' if n == 2 else 'GAP_SMOKE:FAIL %r' % (n,))\n"
        ),
    },
    {
        "name": "is_even",
        "language": "python",
        "has_bug": True,
        "note": "named is_even but tests for odd",
        "code": (
            "def is_even(n):\n"
            "    return n % 2 == 1\n"
        ),
        "smoke": (
            "import target\n"
            "ok = target.is_even(4) and not target.is_even(3)\n"
            "print('GAP_SMOKE:OK' if ok else 'GAP_SMOKE:FAIL')\n"
        ),
    },
    {
        "name": "average_off_by_one",
        "language": "python",
        "has_bug": True,
        "note": "divides by len+1, so the average is always too low",
        "code": (
            "def average(numbers):\n"
            "    return sum(numbers) / (len(numbers) + 1)\n"
        ),
        "smoke": (
            "import target\n"
            "v = target.average([2, 4, 6])\n"
            "print('GAP_SMOKE:OK' if abs(v - 4.0) < 1e-9 else 'GAP_SMOKE:FAIL %r' % (v,))\n"
        ),
    },
    {
        "name": "running_max",
        "language": "python",
        "has_bug": True,
        "note": "named running_max but keeps the minimum (comparison inverted)",
        "code": (
            "def running_max(nums):\n"
            "    m = nums[0]\n"
            "    for n in nums:\n"
            "        if n < m:\n"
            "            m = n\n"
            "    return m\n"
        ),
        "smoke": (
            "import target\n"
            "v = target.running_max([1, 5, 3])\n"
            "print('GAP_SMOKE:OK' if v == 5 else 'GAP_SMOKE:FAIL %r' % (v,))\n"
        ),
    },
    {
        # Hard recall case (senior async mistake). Class-level state is shared across
        # concurrent requests, so one request logs another's id. Proving it needs the
        # RIGHT property — "Alice's line must read Alice", not "the id is stable within
        # a coroutine" (which is true even when wrong). See the oracle below.
        "name": "async_context_leak",
        "language": "python",
        "has_bug": True,
        "note": "class-level tracking id shared; concurrent async requests log the wrong id",
        "code": (
            "import asyncio\n"
            "\n"
            "class RequestContextManager:\n"
            "    current_tracking_id = \"DEFAULT\"\n"
            "    def __init__(self, tracking_id):\n"
            "        RequestContextManager.current_tracking_id = tracking_id\n"
            "    async def process_payment(self, user_name, amount):\n"
            "        print(f\"[{RequestContextManager.current_tracking_id}] start {user_name}\")\n"
            "        await asyncio.sleep(0.05)\n"
            "        print(f\"[{RequestContextManager.current_tracking_id}] done {user_name}\")\n"
        ),
        # Behavioural oracle via captured stdout, so it works for ANY correct fix
        # (instance attr OR contextvars): every line about Alice must carry Alice's id.
        "smoke": (
            "import asyncio, io, contextlib, target\n"
            "async def _m():\n"
            "    a = target.RequestContextManager('TXN-ALICE')\n"
            "    t1 = a.process_payment('Alice', 1)\n"
            "    await asyncio.sleep(0.01)\n"
            "    b = target.RequestContextManager('TXN-BOB')\n"
            "    t2 = b.process_payment('Bob', 2)\n"
            "    await asyncio.gather(t1, t2)\n"
            "buf = io.StringIO()\n"
            "with contextlib.redirect_stdout(buf):\n"
            "    asyncio.run(_m())\n"
            "al = [ln for ln in buf.getvalue().splitlines() if 'Alice' in ln]\n"
            "ok = bool(al) and all('TXN-ALICE' in ln for ln in al)\n"
            "print('GAP_SMOKE:OK' if ok else 'GAP_SMOKE:FAIL')\n"
        ),
    },

    {
        "name": "mutable_default",
        "language": "python",
        "has_bug": True,
        "note": "mutable default arg accumulates across calls (classic AI/Python bug)",
        "code": (
            "def collect(item, into=[]):\n"
            "    into.append(item)\n"
            "    return into\n"
        ),
        "smoke": (
            "import target\n"
            "a = target.collect('x')\n"
            "b = target.collect('y')\n"
            "print('GAP_SMOKE:OK' if a == ['x'] and b == ['y'] else 'GAP_SMOKE:FAIL %r %r' % (a, b))\n"
        ),
    },
    {
        "name": "or_default_zero",
        "language": "python",
        "has_bug": True,
        "note": "`config.get(k) or 30` swallows a valid 0 (the or-default falsy trap)",
        "code": (
            "def get_timeout(config):\n"
            "    return config.get('timeout') or 30\n"
        ),
        "smoke": (
            "import target\n"
            "ok = target.get_timeout({'timeout': 0}) == 0 and target.get_timeout({}) == 30\n"
            "print('GAP_SMOKE:OK' if ok else 'GAP_SMOKE:FAIL')\n"
        ),
    },
    {
        "name": "regex_unanchored",
        "language": "python",
        "has_bug": True,
        "note": "re.match without end-anchor accepts trailing junk (intent: exactly 3 caps)",
        "code": (
            "import re\n"
            "def is_code(s):\n"
            "    return re.match(r'[A-Z]{3}', s) is not None\n"
        ),
        "smoke": (
            "import target\n"
            "ok = target.is_code('ABC') and not target.is_code('ABCD') and not target.is_code('AB')\n"
            "print('GAP_SMOKE:OK' if ok else 'GAP_SMOKE:FAIL')\n"
        ),
    },
    {
        "name": "missing_branch",
        "language": "python",
        "has_bug": True,
        "note": "no branch for 0 -> returns None silently (intent: classify any int)",
        "code": (
            "def classify(n):\n"
            "    if n > 0:\n"
            "        return 'positive'\n"
            "    elif n < 0:\n"
            "        return 'negative'\n"
        ),
        "smoke": (
            "import target\n"
            "r = target.classify(0)\n"
            "ok = (target.classify(5) == 'positive' and target.classify(-5) == 'negative'\n"
            "      and isinstance(r, str) and r and r not in ('positive', 'negative'))\n"
            "print('GAP_SMOKE:OK' if ok else 'GAP_SMOKE:FAIL %r' % (r,))\n"
        ),
    },
    {
        "name": "aliased_rows",
        "language": "python",
        "has_bug": True,
        "note": "[[0]*n]*n aliases one row n times; editing one edits all",
        "code": (
            "def make_matrix(n):\n"
            "    return [[0] * n] * n\n"
        ),
        "smoke": (
            "import target\n"
            "m = target.make_matrix(3)\n"
            "m[0][0] = 1\n"
            "ok = m[1][0] == 0 and m[2][0] == 0 and len(m) == 3 and len(m[0]) == 3\n"
            "print('GAP_SMOKE:OK' if ok else 'GAP_SMOKE:FAIL')\n"
        ),
    },

    # ─────────────── CLEAN (false-positive traps) ───────────────
    {
        "name": "add",
        "language": "python",
        "has_bug": False,
        "note": "trivially correct",
        "code": (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
    },
    {
        "name": "clamp",
        "language": "python",
        "has_bug": False,
        "note": "correct and total over its domain",
        "code": (
            "def clamp(x, low, high):\n"
            "    if x < low:\n"
            "        return low\n"
            "    if x > high:\n"
            "        return high\n"
            "    return x\n"
        ),
    },
    {
        "name": "to_fahrenheit",
        "language": "python",
        "has_bug": False,
        "note": "correct unit conversion",
        "code": (
            "def to_fahrenheit(celsius):\n"
            "    return celsius * 9 / 5 + 32\n"
        ),
    },
    {
        "name": "safe_divide",
        "language": "python",
        "has_bug": False,
        "note": "intended: returns 0.0 on zero divisor (implicit intent from name+guard)",
        "code": (
            "def safe_divide(a, b):\n"
            "    if b == 0:\n"
            "        return 0.0\n"
            "    return a / b\n"
        ),
    },
    {
        "name": "safe_divide_documented",
        "language": "python",
        "has_bug": False,
        "note": "same, but intent is stated explicitly in a docstring",
        "code": (
            "def safe_divide(a, b):\n"
            '    """Return a / b, or 0.0 when b is 0. The 0.0 default is intentional."""\n'
            "    if b == 0:\n"
            "        return 0.0\n"
            "    return a / b\n"
        ),
    },
    {
        "name": "memoized_fib",
        "language": "python",
        "has_bug": False,
        "note": "INTENT PAIR with mutable_default: the mutable default is a deliberate, correct cache",
        "code": (
            "def fib(n, _memo={0: 0, 1: 1}):\n"
            "    if n not in _memo:\n"
            "        _memo[n] = fib(n - 1) + fib(n - 2)\n"
            "    return _memo[n]\n"
        ),
    },
    {
        "name": "greet_or_default",
        "language": "python",
        "has_bug": False,
        "note": "INTENT PAIR with or_default_zero: same `or` pattern, but the fallback is the documented intent",
        "code": (
            "def greet(name):\n"
            '    """Greet the user; fall back to a friendly default when no name is given."""\n'
            "    return \"Hello, \" + (name or \"there\")\n"
        ),
    },
    {
        "name": "is_power_of_two",
        "language": "python",
        "has_bug": False,
        "note": "correct, idiomatic bit trick; looks odd but is right over its whole domain",
        "code": (
            "def is_power_of_two(n):\n"
            "    return n > 0 and (n & (n - 1)) == 0\n"
        ),
    },
]

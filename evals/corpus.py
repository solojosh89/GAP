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
]

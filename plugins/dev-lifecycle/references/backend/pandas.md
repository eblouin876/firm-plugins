<!--
library: pandas
versions-covered: "pandas 2.x (+ pyarrow, numpy)"   # real verified majors
last-verified: 2026-07-12
provenance: auto-generated (pending review)
sources:
  - https://pandas.pydata.org/docs/whatsnew/v3.0.0.html
  - https://pandas.pydata.org/docs/whatsnew/v2.0.0.html
  - https://pandas.pydata.org/docs/user_guide/copy_on_write.html
  - https://pandas.pydata.org/community/blog/pandas-3.0.html
  - https://pypi.org/project/pandas/
  - https://arrow.apache.org/docs/python/index.html
-->

# pandas conventions

Correctness and performance idioms for pandas in the `schwab_trader` market-data pipeline (`pandas>=2.1`, `pyarrow>=14`, `numpy>=1.26`). Load when the working set touches `pandas` (imports, DataFrame/Series code). Subordinate to project conventions — these are defaults, not overrides.

## Contents
- Version check (do this first)
- Copy-on-Write & chained assignment
- Vectorization over row loops
- Dtypes discipline
- Datetime & market-calendar time series
- Reading/writing (parquet first)
- Merge/join correctness
- Groupby idioms
- Memory
- Numerical correctness
- When NOT to use pandas
- Testing DataFrames

## Version check (do this first)
Detect the installed line — behavior diverges sharply across the 2.x/3.0 boundary:
```python
import pandas as pd; pd.__version__
```
- **pandas 2.x** (app floor `>=2.1`): PyArrow-backed dtypes available via `dtype_backend="pyarrow"` (since 2.0); `pd.NA` nullable scalar. **Copy-on-Write (CoW) is opt-in** — enable globally with `pd.options.mode.copy_on_write = True`; 2.2 adds a `"warn"` mode to surface future breakage. numpy 2.x is supported from **pandas 2.2.2+** (pair with `pyarrow>=14` for numpy-2 wheels).
- **pandas 3.0** (GA 2026-01-21, current `3.0.x`): **CoW is the default and only mode.** Chained assignment silently no-ops, and `SettingWithCopyWarning` is *removed*. Requires Python `>=3.11`. Upgrade to 2.3 warning-clean before jumping to 3.0.
- Under CoW, any indexing result behaves as a copy — the old `SettingWithCopyWarning` heuristic is gone, so write 2.x code as if CoW is on to stay 3.0-clean.

## Copy-on-Write & chained assignment
Chained assignment mutates a temporary and is lost under CoW (and unreliable before it):
```python
df[df.symbol == "AAPL"]["px"] = 0.0   # anti-pattern: no-op under CoW
df.loc[df.symbol == "AAPL", "px"] = 0.0   # single .loc, one indexing op
```
Rule: one `.loc[rows, cols]` for every in-place set. To edit a slice independently, take an explicit `.copy()`. Do not sprinkle defensive `.copy()` to silence warnings — under CoW copies are already lazy/free until mutation.

## Vectorization over row loops
`.iterrows()` and `.apply(axis=1)` are Python-level loops — orders of magnitude slower and they box dtypes to `object`. Use column arithmetic / numpy ufuncs:
```python
df["notional"] = df["px"] * df["qty"]            # vectorized
df["side"] = np.where(df["qty"] >= 0, "buy", "sell")
# multi-branch: np.select([...cond...], [...choice...], default=...)
```
Reserve `.apply` for genuinely non-vectorizable logic, and prefer a built-in agg/transform when one exists (next sections).

## Dtypes discipline
Never let ingest infer silently. Declare dtypes; use `category` for low-cardinality strings (symbol, venue, side) and nullable/arrow types for missing-aware numerics.
```python
df = df.astype({"symbol": "category", "venue": "category"})
prices = pd.array(raw, dtype="float64[pyarrow]")   # arrow-backed, pd.NA-aware
```
- Arrow strings (`"string[pyarrow]"`) cut memory vs `object` and are far faster for string ops.
- Anti-pattern: leaving id/enum columns as `object`; mixing `np.nan` and `pd.NA` in one nullable column.

## Datetime & market-calendar time series
Market data is tz-sensitive — a naive timestamp is a bug waiting to misalign sessions.
```python
ts = pd.to_datetime(raw, utc=True).dt.tz_convert("America/New_York")
bars = df.set_index("ts").resample("1min").agg({"px": "last", "qty": "sum"})
import pandas_market_calendars as mcal
sched = mcal.get_calendar("XNYS").schedule(start_date="2026-07-01", end_date="2026-07-12")
```
Keep a `DatetimeIndex` (sorted, monotonic) for `resample`/`asof`. Use `pd.merge_asof` for as-of joins (quote to trade). Align to real sessions via `pandas-market-calendars`; do not assume calendar-day continuity.

## Reading/writing (parquet first)
Prefer parquet via pyarrow over CSV — typed, columnar, compressed, ~orders faster and preserves dtypes/tz.
```python
df.to_parquet("bars.parquet", engine="pyarrow", compression="zstd")
df = pd.read_parquet("bars.parquet", columns=["ts", "px", "qty"])   # projection pushdown
```
For unavoidable CSV, pass `dtype=`, `usecols=`, `parse_dates=`, and `chunksize=` for large files. `pd.read_*(..., dtype_backend="pyarrow")` returns arrow-backed frames directly.

## Merge/join correctness
Assert cardinality so a bad key blows up loudly instead of fanning out rows:
```python
out = trades.merge(ref, on="symbol", how="left",
                   validate="many_to_one", indicator=True)
```
`validate=` catches unexpected duplicates; `indicator=True` reveals unmatched keys. Ensure join-key dtypes match exactly (a `category` vs `object` or `int64` vs `float64` mismatch degrades or silently drops matches).

## Groupby idioms
Use built-in aggregations (C-level, release the GIL) over `apply`:
```python
g = df.groupby("symbol", observed=True)
g.agg(vwap=("px", "mean"), vol=("qty", "sum"))
```
Set `observed=True` with categorical keys (avoids materializing the full cartesian product — becomes the default in 3.0). Use `transform` for group-broadcast results; reserve `apply` for logic no agg/transform covers.

## Memory
`df.memory_usage(deep=True)` to see real cost. Downcast wide integer/float columns (`pd.to_numeric(s, downcast="float")`), convert repeated strings to `category`, and select columns at read time rather than dropping after. Under CoW, avoid pre-emptive `.copy()`; let the engine copy lazily.

## Numerical correctness
Floats carry NaN; nullable/arrow dtypes carry `pd.NA` — `pd.NA` propagates through comparisons (`pd.NA == x` is `pd.NA`, not `False`), so branch with `.isna()`. Never test float equality with `==`:
```python
np.isclose(a, b)               # not a == b
mask = df["px"].sub(ref).abs() < 1e-9
```
`NaN != NaN`; use `.isna()`/`.fillna()`, not `== np.nan`.

## When NOT to use pandas
Pandas is single-node, memory-bound. For datasets beyond RAM or heavy out-of-core scans, reach for **polars**, **duckdb** (SQL over parquet), or raw **pyarrow** compute — often 10x+ on the same box. Keep pandas for the interactive/last-mile layer.

## Testing DataFrames
Assert on frames, not repr strings:
```python
from pandas.testing import assert_frame_equal
assert_frame_equal(got, want, check_dtype=True, check_like=True)
```
`check_like=True` ignores row/column order; keep `check_dtype=True` so a silent `object`/`float64` regression fails the test. Use `assert_series_equal` / `check_exact=` for tolerance control.

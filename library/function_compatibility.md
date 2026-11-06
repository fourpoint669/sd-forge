# Function compatibility: Vensim function vs PySD support

PySD version in the report: 3.14.3. Source of truth: `engine/translation_report.csv` (505 models, 401 translate, 372 run).

## Not implemented / unsupported in PySD 3.14.3 `[verified: engine/translation_report.csv]`

Names are what PySD's `NotImplementedError` reported (lower-cased). `my_func`, `find_market_price`, `size` are model-defined macros or names, not Vensim built-ins `[unverified]`.

| Function (as reported) | Source folder(s) where it blocked translation |
|---|---|
| `cgrowth` | bptk-py |
| `depreciate_straightline` | sdeverywhere |
| `derivn` | bptk-py |
| `find_market_price` | sdeverywhere |
| `gamma_ln` | sdeverywhere |
| `invnorm` | bptk-py |
| `lognormal` | bptk-py |
| `lookuparea` | bptk-py |
| `my_func` | pysd |
| `negbinomial` | bptk-py |
| `normalcdf` | bptk-py |
| `npv` | bptk-py, sdeverywhere |
| `pareto` | bptk-py |
| `percent` | bptk-py |
| `permutations` | bptk-py |
| `poisson` | bptk-py |
| `random` | bptk-py |
| `size` | sdeverywhere |
| `triangular` | bptk-py |
| `vector_elm_map` | sdeverywhere |
| `weibull` | bptk-py |

## Rewrites that make unsupported functions run `[verified: engine/translation_report.csv; bptk-py test models]`

| Function (XMILE/Vensim) | Rewrite used | Check |
|---|---|---|
| `LOG10(x)` | `LN(x)/LN(10)` | log10(100000) = 5.0 |
| `ROOTN(x, n)` | `IF_THEN_ELSE(x < 0, -((-x)^(1/n)), x^(1/n))` (`<` must be written `&lt;` inside XMILE) | rootn(-27, 3) = -3; rootn(144, 2) = 12. Odd-root behavior for negative x is assumed `[unverified]` |
| `SINWAVE(a, p)` / `COSWAVE(a, p)` | `a*SIN(2*pi*TIME/p)` / `a*COS(2*pi*TIME/p)` | wave(0)=0, wavecos(0)=10. Definition assumed `[unverified]` |
| `LOGISTIC(mean, scale[, seed])` | a random draw, not a sigmoid: `mean + scale*LN(u/(1-u))` with `u = RANDOM_UNIFORM(0,1[,seed])` held in one aux | Runs; same distribution, not the same random stream as the original tool |

Harness note: Vensim models with data variables read from `.tab` files need `data_files=`; `engine/translate_all.py` now retries with the `.tab` files beside the model when PySD reports "before loading the data".

## Other failure classes `[verified: engine/translation_report.csv]`

| Class | Meaning |
|---|---|
| ParseError / IncompleteParseError | PySD XMILE/Vensim parser rejects syntax, mainly XMILE array expressions (`Inventory[*, *]`, `[1:2]`), simlin builtins (`isModuleInput`), `???` placeholders |
| FileNotFoundError (`_ext_*_from_csv`) | external data/lookup/constant references to files not present beside the model |
| RecursionError | models with cyclic or deeply nested dependency PySD cannot order |
| ValueError / KeyError / IndexError | subscript/array-size mismatches and special values (`inf`, `nan`, `dt`) in PySD's reader |

## Verified against the committed cross-tool references `[verified: engine/tests/test_pysd_constructs.py]`

Every row translates with PySD 3.14.3, runs, and reproduces the reference frame committed beside its model in
`raw/test-models/tests/`. Tolerance: 1e-5 scale-relative, which is what those references support - they carry 6
significant digits, and `EXP` and `SQRT`, functions the engine already exports, need the same tolerance
(`test_an_already_supported_construct_needs_the_same_tolerance`). Runs use each model's own control values and the
reference time grid is exactly the grid such a run returns, so nothing is interpolated.

| Function | Fixture(s) under `raw/test-models/tests/` |
|---|---|
| `DELAY1`, `DELAY1I`, `DELAY3`, `DELAY3I`, `DELAY N` | `delays`, `delay_parentheses`, `delay_numeric_error`, `delay_pipeline` |
| `DELAY FIXED` | `delay_fixed`, `delay_pipeline` |
| `SMOOTH`, `SMOOTHI`, `SMOOTH3`, `SMOOTH3I`, `SMOOTH N` | `smooth`, `smooth_and_stock` |
| `TREND` | `trend` |
| lookup variable called like a function, with and without a declared range | `lookups`, `lookups_without_range`, `lookups_funcnames` |
| `WITH LOOKUP`, plain, bounded, and over an expression | `lookups_inline`, `lookups_inline_bounded`, `lookups_with_expr` |
| `MODULO` | `lookups_funcnames` |
| `INITIAL`, `ACTIVE INITIAL`, a stock initialised from another stock | `initial_function`, `active_initial`, `chained_initialization` |
| `STEP`, `RAMP`, `PULSE`, `PULSE TRAIN` | `input_functions` |
| `ABS`, `MIN`, `MAX`, `EXP`, `SQRT`, `IF THEN ELSE`, `:AND:`/`:OR:`/`:NOT:`, `TIME` | `abs`, `builtin_max`, `builtin_min`, `exp`, `sqrt`, `logicals`, `time` |

**PySD support is not engine support.** Of the table above, only the last row is reachable end to end in this
repository. `validate.check_units` fails any stateful that is not a plain `INTEG` ("write delays as explicit
stocks"), `loop_detector` cannot score a loop that passes through one, and `export_js` rejects every delay,
smoothing, trend, lookup and test-input construct, so a model using one of them can be neither validated nor given
an explorer page `[verified: engine/tests/test_pysd_constructs.py::test_the_engine_still_refuses_these_constructs]`.

**A stateful built directly out of another stateful does not reproduce its reference.** In `arguments`,
`SMOOTH N(DELAY3(Time, MODULO(constant, 3)), constant, 1, 2)` is off by about 7e-3 - three orders of magnitude
beyond the references' precision - while the same equation with `ABS` in place of `MODULO` agrees. Name the
intermediate variable rather than nesting statefuls
`[verified: engine/tests/test_pysd_constructs.py::test_a_stateful_nested_inside_another_statefuls_arguments_disagrees_with_vensim]`.

## Still `[unverified]` (documented as supported by PySD, not checked here)

`LN`, `SIN`/`COS`, `INTEGER`, `FORECAST` (its only fixture, `forecast`, is subscripted, so it gives no
unsubscripted reference), `GET XLS/DIRECT DATA/CONSTANTS/LOOKUPS`, `RANDOM UNIFORM`/`RANDOM NORMAL`,
`VMIN`/`VMAX`/`SUM`/`PROD` over subscripts, `ELMCOUNT`, `VECTOR SELECT`/`VECTOR ELM MAP`/`VECTOR SORT ORDER`
(partial; `vector_elm_map` failed in one model above).

## Practical rules

- Before relying on a function, grep this file, then run `engine/translate_all.py` on the model. A function in the
  verified table above is known to work *in PySD*; check that `validate.py` and `export_js.py` accept it before
  building a model on it.
- Replace unsupported distributions (`weibull`, `pareto`, `poisson`, `triangular`, ...) with `RANDOM UNIFORM`-based or precomputed lookup equivalents, or compute them outside the model.
- Prefer `.mdl` over `.stmx` for array models; PySD's XMILE array support is narrower `[verified: bptk-py array tests fail]`.

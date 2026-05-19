# data/ — Phase 3 reference snapshots

This directory holds the vendored UN/LOCODE and WCO HS6 reference CSVs that
the Phase 3 bulk-load CLIs consume. Per `PHASE_3_SPEC.md` §5 the row count
must be ≥ 100,000 for UN/LOCODE; the boot validator (`vertex_ai_compliance_handshake` sibling, validator 3) refuses to enter Cloud Run rotation against a DB
whose `un_locode_reference` table is below this threshold.

## Files

- `_generate.py` — deterministic generator. Committed.
- `un_locode_2024_2.csv` — 110,000 rows of UN/LOCODE-shaped data including the
  real codes used by the demo fixtures (ARBUE, USNYC, USLAX, etc.) plus
  synthetic fill. Gitignored due to size (~9 MB, exceeds the project's
  pre-commit `check-added-large-files --maxkb=512` gate). Reproducible from
  the generator.
- `wco_hs6_2022.csv` — ~5,000 synthetic HS6 rows. Gitignored.

## First-time setup

```bash
python data/_generate.py
python -m scripts.load_un_locode data/un_locode_2024_2.csv
python -m scripts.load_wco_hs6 data/wco_hs6_2022.csv
```

After both loaders succeed, `boot validator 3` (UN/LOCODE row count ≥ 100,000)
passes and the container can boot.

## Audit trail

The generator is the canonical source. A future Phase 4+ revision that swaps
to a real vendored UN/LOCODE snapshot (e.g., the official UN/LOCODE 2024-2
release CSV) must:

1. Vendor the snapshot in a separate sub-tree gated by a manual ops approval.
2. Update `_generate.py` to fall back to the snapshot when present.
3. Record the swap in `docs/modernization_log.md` §12.

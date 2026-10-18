# GhostReview examples

A small sample project (`sample_project/`: `app.py` imports
`pricing.compute_total`), a set of diffs (`diffs/`), sample
optional reports (`sample_reports/`), and the shape of a finished
review (`sample_output/`, labelled as a sample, not a captured
run). Commands assume the install from the main README.

## 1. Review a clean small change

```bash
ghostreview review examples/sample_project \
  --diff examples/diffs/clean_small.diff -o /tmp/review-out
cat /tmp/review-out/REVIEW.md   # verdict, what changed, dependents
cat /tmp/review-out/review.json # the same facts, machine-readable
echo $?  # 0: straightforward or needs-a-look
```

The review names `pricing.py`, counts its added and deleted
lines, and lists `app.py` as a dependent: it imports the changed
file and is not itself in the diff (one-hop import scan only).

## 2. Watch the flags fire

```bash
# A test file was edited in the diff: TEST-EDIT.
ghostreview review examples/sample_project \
  --diff examples/diffs/test_edit.diff -o /tmp/review-out

# A secret-shaped path changed: SECRET-PATH, high. The review
# names the path and never prints the value from the diff.
ghostreview review examples/sample_project \
  --diff examples/diffs/secret_path.diff -o /tmp/review-out
echo $?  # 1: needs-attention

# A whole 120-line file deleted: LARGE-DELETION, high.
ghostreview review examples/sample_project \
  --diff examples/diffs/large_deletion.diff -o /tmp/review-out

# Everything at once: test edit + secret path + a deleted file.
ghostreview review examples/sample_project \
  --diff examples/diffs/mixed_risky.diff -o /tmp/review-out
```

## 3. Cite Verify and Scope when you have them

```bash
ghostreview review examples/sample_project \
  --diff examples/diffs/clean_small.diff \
  --verify-report examples/sample_reports/verify-report.json \
  --scope-pack examples/sample_reports/scope.json \
  -o /tmp/review-out
```

The sample Verify report has a non-passing verdict, so the
review flags VERIFY-FAILED (high) and cites the verdict. The
sample Scope pack contributes its recorded risk reasons for
`pricing.py`. With neither report supplied, a review says so in
plain words and claims no check ran.

## 4. Review your own working tree

```bash
cd your-project
ghostreview review . -o /tmp/review-out   # git diff HEAD
ghostreview review . --staged -o /tmp/review-out
```

Nothing here modifies `sample_project/`: reviews are written
only to the output directory you name.

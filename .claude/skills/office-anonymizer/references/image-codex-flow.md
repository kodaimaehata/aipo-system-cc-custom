# Image Anonymization via Codex CLI

`scripts/image_codex_anonymize.py` is the adapter between the Office
Anonymizer skill and the Codex CLI (`codex` 0.122+). It walks every picture
shape in a pptx and, when needed, replaces the image blob with an anonymized
copy produced by Codex.

## Per-Image Pipeline

1. Extract the picture blob, hash it (`sha1`), and dedupe against prior
   pictures — shapes that point at the same blob are processed together.
2. Write the original blob to `work_dir/<image_id>_source.<ext>` at `0o600`.
3. Compose a minimal prompt in `work_dir/<image_id>_prompt.md` listing every
   approved `original -> replacement` pair.
4. Run `codex exec --skip-git-repo-check --sandbox read-only -i <source> -m
   <model> -` with the prompt on stdin. `output=<work_dir/anonymized.png>` is
   appended to the prompt so Codex knows where to write.
5. Parse `findings=N` from Codex's stdout.
6. If `findings == 0` or the returned blob is byte-identical, the picture is
   marked `unchanged`.
7. Otherwise the image part is cloned and the shape's `r:embed` is rewritten
   (see "Safe Part Swap" below).

## Defaults

| Knob              | Default         | Override              |
| ----------------- | --------------- | --------------------- |
| Model             | `gpt-5-codex`   | `model=` kwarg        |
| Per-image timeout | 300 s           | `timeout_sec=`        |
| Retries           | 2 (3 attempts)  | `retries=`            |
| Images per run    | 20              | `max_images=`         |

Exceeding `max_images` raises `CodexBudgetExceeded`; the caller is expected
to pause and confirm before retrying with a raised cap.

## Failure Policy

- Timeouts and non-zero exits trigger exponential-backoff retries up to
  `retries + 1` attempts.
- A persistently failing image is logged to `image_codex_log.md` and the
  original image remains in place. The pipeline does **not** abort on a
  single failed image; it records the outcome and continues.
- Byte-identical outputs are treated as "no change"; this guards against
  Codex returning a copy of the source when it finds nothing.

## Safe Part Swap

Pptx packages frequently share one image part across many slides (masters,
layouts, or explicit re-use). Overwriting the part in place would ripple
into every consumer. To avoid that:

- A new `ImagePart` is added to the package with a fresh `partname`
  (`/ppt/media/image{N+1}.png`).
- The target slide's relationship table gains a new `rId` pointing at that
  new part.
- The picture shape's `blipFill/blip@r:embed` is rewritten to the new `rId`.
- Other shapes that referenced the original part are untouched.

`references/replay-examples.md` shows how to verify this after a run by
comparing slide-by-slide picture hashes.

## Test Coverage Expectations

- A fixture with one image part referenced by two slides.
- Replace on slide A only — slide B's sha1 must stay unchanged.
- Save and reopen the resulting pptx: all shapes enumerable, no dangling
  rels, no part-name collisions.
- `[Content_Types].xml` and `_rels/*.rels` contain the new part registration.

## Environment Requirements

- Codex CLI authenticated; `codex --version` returns `0.122.0` or newer.
- Network access to the Codex model endpoint.
- Sufficient disk for per-image temporary output in the run cache.

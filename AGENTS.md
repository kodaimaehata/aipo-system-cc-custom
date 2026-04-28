# Repository Guidelines

## Project Structure & Module Organization

- `src/aipo (AI-PO) system/`: Source-of-truth documentation for the AIPO (AI Product Owner) system (core commands `CMD_aipo_*`, context docs `CTX_*`, and role templates).
- `src/aipo (AI-PO) system/CTX_command_templates/`: Reusable command templates grouped by domain (e.g., `project_management_templates/`, `content_creation_templates/`).
- `src/aipo (AI-PO) system/aipo_LT用スクリプト/`: LT/presentation materials (includes `image.png` and Marp slide content).
- `.codex/skills/`: Repository-local Codex skills (auto-discovered by Codex when run from this repo).
- `programs/`: Per-project AIPO runs (each `programs/<project>/` is intended to be its own Git repo; the parent repo should not track it).
- `docs/`: Reserved for generated/published artifacts (currently empty).

## Build, Test, and Development Commands

This repository is documentation-only (Markdown); no build/test toolchain is checked in.

- Search content: `rg "CMD_aipo_02" src/`
- List files (paths contain spaces): `ls "src/aipo (AI-PO) system"`
- Optional slide export (requires Marp installed): create `slides.md` from the template in `src/aipo (AI-PO) system/aipo_LT用スクリプト/`, then run `marp slides.md --pdf`

## Coding Style & Naming Conventions

- Keep files UTF-8. Preserve existing export-style formatting (e.g., `<aside>`, tables, long lines) unless you have a specific reason to reflow.
- Avoid renaming/moving files: many internal links include URL-encoded filenames and will break on rename.
- When adding new docs, follow the existing prefixes: `CMD_<area>_*` for commands and `CTX_<topic>_*` for context/templates.

## Testing Guidelines

- No automated tests. Before opening a PR, verify Markdown renders and that relative links/images resolve (e.g., `src/aipo (AI-PO) system/aipo_LT用スクリプト/image.png`).

## Commit & Pull Request Guidelines

- If Git history isn’t available, use a simple Conventional Commits style:
  - `docs: clarify CTX_session_rules`
  - `templates: add CMD_prj_...`
- PRs should include: a short summary, affected paths, and notes on any renames/moves (they break links). Add screenshots when changing slide layouts.

## Agent-Specific Instructions

- Quote paths with spaces in shell commands and keep edits narrowly scoped to the requested documents.
- When the work benefits from parallel investigation, implementation, or review, use sub-agents as appropriate. Keep each delegated task concrete, bounded, and coordinated through written handoffs or file changes rather than relying only on conversation context.

## Response Style Addendum

- Favor readability over exhaustiveness when the user is asking for explanation, review, or summary.
- Start with a short conclusion in 2 to 3 sentences before expanding.
- Organize the body into 2 to 4 meaningful sections with short headings when the topic is non-trivial.
- Do not turn the whole answer into a flat list of bullets. Use bullets only when enumerating distinct items is genuinely clearer.
- Keep each sentence relatively short. Avoid stacking many clauses into one sentence.
- Avoid repeating the same point in slightly different words.
- When using bullets, keep one bullet to one point and keep each bullet compact.
- Prefer a natural explanatory flow where the reader can understand what matters, why it matters, and what to do next.
- Avoid overly formal report-like phrasing unless the user explicitly asks for it.
- When presenting problems or findings, pair each point with the corresponding implication or response so the structure is easy to scan.
- End with a short practical next step only when it helps the user move forward.

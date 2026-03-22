---
name: powerpoint-layout-recommender
description: Recommend PowerPoint slide layouts and deck-level continuity guidance from slide content. Use when planning a deck, choosing between cover/agenda/comparison/flow/graph/table/parallel layouts, or preparing a structured handoff to an implementation skill.
---

# PowerPoint Layout Recommender

## Overview

Use this skill before actual slide authoring. It turns slide content, section plans, or deck outlines into layout recommendations, explains why those layouts fit, and returns structured guidance that can be handed to `slides` or another PPTX implementation workflow.

## When To Use

- The user has slide content but has not decided the PowerPoint layout yet.
- The user wants to review a multi-slide outline for chapter rhythm or continuity.
- The user wants a structured recommendation before using `slides` or a template-based PPTX workflow.

## When Not To Use

- The user already wants a finished `.pptx` and layout recommendation is no longer the bottleneck.
- The request is mainly about asset production such as illustrations, photo selection, or template design.
- The slide type is outside the current V1 scope and needs a domain-specific pattern that is not close to the supported set.

## Inputs To Collect

- `deck_goal` and `audience` when available
- For each slide:
  - `page_purpose`
  - `key_message`
  - `content_items`
  - `item_count`
  - `text_density`
  - `emphasis_target`
- Useful optional signals:
  - `relation_type`
  - `quantitative_shape`
  - `time_axis`
  - `deck_role`
  - `design_constraints`

If those fields are missing:

- ask when the ambiguity changes the layout family
- otherwise infer conservatively and state the assumptions explicitly

## Workflow

### 1. Normalize The Request

- Decide whether you are answering for a single slide or for a deck.
- Reduce each slide to a `key_message` plus content signals.

### 2. Choose The Pattern Family

- Read [`references/layout-signals.md`](./references/layout-signals.md).
- First decide whether the slide is:
  - a fixed page type
  - relation-heavy
  - relation-light but format-bound

### 3. Choose The Specific Layout

- Read [`references/pattern-dictionary.md`](./references/pattern-dictionary.md) when you need the supported V1 patterns:
  - cover
  - agenda
  - comparison
  - flow
  - graph
  - table
  - parallel

### 4. Review Deck Continuity

- If the user has multiple slides, read [`references/deck-review.md`](./references/deck-review.md).
- Check chapter rhythm, adjacency, density shifts, and repeated layout fatigue.

### 5. Apply Design Constraints

- Read [`references/design-guide.md`](./references/design-guide.md).
- Default to `Noto Sans JP` and a white/black/red palette with restrained use of red emphasis.

### 6. Return Structured Recommendations

- Follow [`references/output-contract.md`](./references/output-contract.md).
- Always include:
  - `recommended_family`
  - `recommended_variant`
  - `why`
  - `content_blocks`
  - `visual_direction`
  - `fallback_layouts`
  - `handoff_notes`
- If assumptions were needed, also include:
  - `assumptions`
- For multi-slide requests, also include:
  - `deck_review_notes`

## Output Rules

- Do not jump straight to implementation code or `.pptx` authoring.
- Do not invent unsupported V1 patterns unless you clearly mark them as an approximation.
- If graph or table is recommended, stay at the level of representation choice, not rendering details.
- If the user wants actual deck authoring after recommendation, hand off to `slides` or another implementation workflow.

## Reference Map

- [`references/layout-signals.md`](./references/layout-signals.md): signal taxonomy and high-level decision flow
- [`references/pattern-dictionary.md`](./references/pattern-dictionary.md): supported pattern details
- [`references/deck-review.md`](./references/deck-review.md): multi-slide continuity review
- [`references/output-contract.md`](./references/output-contract.md): response structure
- [`references/design-guide.md`](./references/design-guide.md): typography, palette, and density rules

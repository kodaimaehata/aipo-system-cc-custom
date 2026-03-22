# Output Contract

Return structured recommendations. A concise markdown table is acceptable, but include these fields for each slide.

```json
{
  "recommended_family": "comparison",
  "recommended_variant": "two-column compare",
  "why": ["...", "..."],
  "content_blocks": [
    {"role": "title", "content": "..."},
    {"role": "lead", "content": "..."}
  ],
  "visual_direction": {
    "tone": "white-black-red",
    "density": "medium",
    "emphasis": "delta"
  },
  "fallback_layouts": ["comparison table"],
  "handoff_notes": ["..."],
  "assumptions": ["..."],
  "deck_review_notes": [
    {
      "status": "warning",
      "note": "..."
    }
  ]
}
```

## Required Behavior

- `recommended_family` and `recommended_variant` must both be present.
- State assumptions if signals are missing.
- Give at least one fallback layout when ambiguity is material.
- `fallback_layouts` must contain layout alternatives, not editorial instructions.
- Always include `handoff_notes`, even if short.
- For multi-slide input, include `deck_review_notes`.
- Do not output implementation code unless the user explicitly asks for the next authoring step.

# Layout Signals

## Core Dimensions

| Signal | Values |
|---|---|
| `page_purpose` | cover, agenda, comparison, flow, graph, table, parallel |
| `relation_type` | fixed_page, compare, sequential, parallel, quantitative, none |
| `item_count` | 1, 2-3, 4+ |
| `text_density` | low, medium, high |
| `time_axis` | none, ordered_steps, chronology |
| `quantitative_shape` | ranking, composition, trend, tabular |
| `deck_role` | opening, orientation, evidence, transition, close |
| `emphasis_target` | headline, delta, process, evidence, brand |

## Mapping To Branch Types

| Branch label | Allowed `relation_type` values | Meaning |
|---|---|---|
| fixed page | `fixed_page` | page purpose itself determines the layout family |
| relation-heavy | `compare`, `sequential`, `parallel` | meaning comes from relationships among elements |
| relation-light but format-bound | `quantitative`, `none` | meaning comes from the required expression form or data lookup need |

If `relation_type` is missing, infer it from `page_purpose`, `time_axis`, `quantitative_shape`, and `emphasis_target`.

## Decision Flow

1. If `page_purpose` is explicitly cover or agenda, use the fixed page type.
2. Otherwise ask whether the slide is relation-heavy:
   - compare -> comparison
   - sequential -> flow
   - parallel -> parallel
3. If the slide is not relation-heavy but is format-bound:
   - ranking / composition / trend -> graph
   - tabular or dense comparison axes -> table
4. Apply `deck_role` to refine tone and density.

## Minimum Normalized Contract

Before choosing a layout, normalize each slide to the following fields:

```yaml
page_purpose: "cover|agenda|comparison|flow|graph|table|parallel|unknown"
key_message: "one-sentence slide takeaway"
item_count: "1|2-3|4+"
text_density: "low|medium|high"
emphasis_target: "headline|delta|process|evidence|brand"
relation_type: "fixed_page|compare|sequential|parallel|quantitative|none|unknown"
quantitative_shape: "ranking|composition|trend|tabular|none"
time_axis: "none|ordered_steps|chronology"
deck_role: "opening|orientation|evidence|transition|close|unknown"
```

If `item_count`, `text_density`, `time_axis`, or `emphasis_target` are inferred rather than provided, record them under `assumptions`.

## Normalization Notes

- If item count exceeds 4, parallel often becomes table or a split sequence.
- If the key message is about difference, prefer comparison over table.
- If the key message is about precise lookup, prefer table over graph.

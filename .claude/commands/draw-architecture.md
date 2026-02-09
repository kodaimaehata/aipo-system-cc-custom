# /draw-architecture

**Usage**: `/draw-architecture [description]`

Generates a draw.io architecture diagram from a text description.

## Inputs
- `description`: Text description of the architecture using arrow notation (e.g., "User -> WebServer -> DB(database)")
- `output_path` (optional): Output file path (default: ./architecture.drawio)

## Component Types
Specify type with `(type)` suffix: `(db)`, `(cache)`, `(external)`, `(container)`, `(queue)`, `(storage)`, `(user)`, `(lb)`

## Execution
1. Read `.claude/skills/draw-architecture/SKILL.md` and execute its instructions.

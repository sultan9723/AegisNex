# Figma Specification: AI Workflow Diagram

## Purpose
Visual representation of the LangGraph workflow for documentation and README.

## Canvas
- Frame: 1200 × 900 px
- Background: `#0E1016`

## Node Styling

### Start / End Nodes
- Shape: Circle (60 × 60 px)
- Fill: `#37474F`
- Text: "START" / "END", white, 12px bold
- Centered on connection points

### Workflow Nodes (Standard)
- Shape: Rounded rectangle (160 × 44 px, 8px radius)
- Fill: Color-coded by function:
  - Green `#2E7D32`: Planner, Skill Executor, Runbook Executor
  - Orange `#F57F17`: Tool Executor
  - Blue `#0288D1`: Verifier, Goal Evaluator
  - Red `#FF7043`: Self-Corrector
  - Purple `#6A1B9A`: Learning
  - Brown `#8D6E63`: Scheduler
  - Dark Red `#C62828`: Risk Assessor, Policy Checker
- Text: Node name, white, 13px semibold
- Number prefix in lighter shade: "1. Planner"

### Edge Styling
- Stroke: 2px, matching source node color
- Arrow: block arrow at end, 12px size
- Labels on conditional edges:
  - `[active_skills]`, `[runbook/trigger]`, `[parallel_batches]`
  - `[plan exists]`, `[empty plan]`
  - `[errors]`, `[ok]`, `[replan]`, `[end]`
  - `[pending_approval]`
- Label font: 10px, `rgba(255,255,255,0.5)`, italic
- Dashed lines for retry loop back to Planner

### Positioning
- Main vertical flow: START → Planner → Tool Executor → Verifier → Goal Evaluator → Learning → END
- Left column: Skill Executor, Self-Corrector
- Right column: Parallel Supervisor, Scheduler, Runbook Executor, Risk Assessor, Policy Checker
- Y spacing between nodes: 40px
- X offset for side columns: 300px from center

### Legend
- Bottom-left corner box
- Color legend for node types
- "Solid = normal flow, Dashed = retry/conditional"

## Typography
- Title: "AI Intelligence Engine — LangGraph Workflow", 22px, white, bold
- Body: Inter, various sizes
- Edge conditions: 10px, italic, muted

## Export
- SVG (for docs), PNG (for README)

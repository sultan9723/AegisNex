# Design Decisions

Brief rationale for every structural and content decision made when creating this project's documentation.

---

## 1. README Structure

**Decision**: Single big README.md at root, not docs/README.md.

**Why**: GitHub displays the root README on the repo landing page. Developers discover the project there first. A secondary README in docs/ would be invisible until the user navigates.

**Trade-off**: The root README is long (~500 lines). Solved by using dense tables and a clear table of contents.

---

## 2. Badge Placement

**Decision**: Badges placed below the hero H1 and tagline, above the table of contents.

**Why**: The hero + tagline + badges is the standard top-of-fold pattern for professional open-source repos (Vercel, Next.js, LangChain). Users evaluate a project in the first 3 seconds — badges signal quality and tech stack immediately.

---

## 3. Hero Section

**Decision**: Text-only H1 + tagline with an `assets/screenshots/hero.png` reference rather than an ASCII art logo.

**Why**: ASCII art in READMEs is divisive and unprofessional for production projects. A real screenshot or logo is the standard. The placeholder references a real image.

---

## 4. Feature Tables Instead of Bullet Lists

**Decision**: All feature descriptions use two-column Markdown tables.

**Why**: Tables consume less vertical space, group related items visually, and are easier to scan than long bullet lists. This is critical for a project with as many features as AegisNex (~30 feature rows across 5 tables).

---

## 5. Architecture Section: ASCII Diagram + Document Link

**Decision**: Show a simplified ASCII architecture diagram inline, then link to ARCHITECTURE.md for the full version.

**Why**: GitHub does not render Mermaid or other diagram formats natively without a plugin. ASCII diagrams render reliably and immediately. The full draw.io diagram goes in the docs. Users see the big picture instantly and can click through for detail.

---

## 6. AI Architecture: Simplified Workflow

**Decision**: Show a condensed linear workflow (`START → Planner → Tool Executor → Verifier → Goal Evaluator → END`) and then a table of all 12 nodes, rather than trying to render the full StateGraph with all conditional edges.

**Why**: The full LangGraph graph with 12 nodes and ~15 conditional edges is too complex for inline text. The simplified version communicates the core loop. The full diagram belongs in the dedicated AI_ARCHITECTURE.md and a separate diagram file.

---

## 7. Repository Structure: Explicit File Listing

**Decision**: The repository structure section lists every `.py` file in `src/` with a one-line description, every route in `frontend/app/`, every test file, and every doc.

**Why**: This is the most valuable section for new contributors. It tells them exactly where to look for each concern. An abbreviated listing would hide important modules (e.g., intelligence/providers/, compliance/, multitenant/).

**Trade-off**: Very long. Mitigated by indentation and grouping.

---

## 8. Table of Contents Style

**Decision**: Use `<p align="center">` with pipe-separated links, not a bullet list.

**Why**: Compact. Fits in 2 lines. Matches the convention used by projects like FastAPI, Pydantic, and LangChain.

---

## 9. Screenshots Section: Table with Placeholder Paths

**Decision**: Table mapping screenshot name → description → placeholder PNG path.

**Why**: Acknowledges that screenshots do not exist yet while establishing exactly what should be captured. Makes it easy for someone to add them later without wondering what to name files.

---

## 10. Diagram Inventory: Separate Document

**Decision**: A dedicated `DIAGRAM_INVENTORY.md` in `assets/diagrams/` rather than embedding the list in the README.

**Why**: The diagram inventory is an internal project management artifact, not user-facing content. Keeping it separate avoids cluttering the README.

---

## 11. Diagram Tool Recommendation

**Decision**: Prefer draw.io over Figma for most diagrams.

**Why**: draw.io files are XML-based and can be committed alongside the codebase. Figma files require a hosted account and export workflows. draw.io supports all the shapes needed (boxes, arrows, DB cylinders, cloud shapes) and renders clean SVGs.

**Exception**: Figma recommended for Multi-Agent Architecture and Multi-Tenant Hierarchy because those benefit from Figma's superior text layout and connector routing for complex tree diagrams.

---

## 12. Config/Env Content

**Decision**: Show essential variables only in the README, with a link to DEPLOYMENT_GUIDE.md for the full reference.

**Why**: The full env list is 50+ variables. Showing all of them in the README would overwhelm the quick-start flow. The essential subset (~15 vars) is enough to get started.

---

## 13. Roadmap Content

**Decision**: All completed features are listed explicitly (not "various improvements"). In-progress and planned sections are minimal and based on ROADMAP.md.

**Why**: The repository has 50+ files implementing real features. Listing them all signals maturity. An empty or vague roadmap would misrepresent the scope.

---

## 14. No Invented Features

**Decision**: Every feature, file, and capability listed in the README was verified by reading the actual source code, configuration files, and documentation.

**Why**: Credibility. Users who clone the repo and look around should find exactly what the README describes. Invented features would destroy trust.

**Examples of verification**: Read `src/` subdirectories to confirm all 11 integration providers; counted 200+ API routes by reading dashboards.py and API_REFERENCE.md; read the Grafana JSON dashboards to confirm 4 dashboard types; read the compliance framework source to confirm 5 standards; read the Agent state definitions to confirm 4 supervisor types.

---

## 15. Markdown Style

**Decision**: ATX headers (`##`), pipe tables, fenced code blocks with language tags, no HTML except where necessary (badges).

**Why**: Clean, portable, renders correctly on GitHub, VS Code preview, and npm/git hosting.

---

## 16. assets/screenshots/ as PNG Placeholders

**Decision**: Text-only placeholder files (not actual images).

**Why**: The task explicitly said not to generate diagrams yet. The placeholders establish the correct file paths so that image references in the README will resolve once real screenshots are added.

**File naming convention**: kebab-case matching the section they belong to (e.g., `dashboard-overview.png`, `ai-chat.png`).

---

## 17. Design Decisions Document

**Decision**: Include it in `assets/diagrams/` as `DESIGN_DECISIONS.md`.

**Why**: Keeps all documentation artifacts together. This file explains the README itself, following the principle that design docs should live close to what they describe.

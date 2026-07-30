---
name: mermaid-diagrams
description: "Create, edit, validate, and preview Mermaid diagrams using the Mermaid Chart VS Code extension. Covers the validate-then-preview workflow, the LM tools (mermaid-diagram-validator, mermaid-diagram-preview, get-syntax-docs-mermaid), the mermaidChart.* commands, @mermaid-chart slash commands, and the Mermaid Chart cloud sync flow. Load whenever a task involves producing a flowchart, sequence, ER, class, state, C4, architecture, or any other diagram."
license: MIT
metadata:
  author: MAFVoiceSeed
  version: "1.0.0"
  last-reviewed: "2026-07-28"
  verified-against: "MermaidChart.vscode-mermaid-chart marketplace listing, 2026-07"
---

# Mermaid Diagrams

Unrelated to MAF — this is editor tooling. It is a skill rather than an always-on instruction
file precisely so it costs nothing on the many tasks that involve no diagram.

## Workflow

1. Pick the diagram type and check its syntax with `get-syntax-docs-mermaid` if you have not
   authored that type recently.
2. Write the diagram to a `.mmd` file in the project.
3. **Validate with `mermaid-diagram-validator` before showing the diagram to the user.** Never
   return unvalidated Mermaid syntax.
4. **Preview with `mermaid-diagram-preview` after generating.** For a diagram that already
   exists as a file, pass `documentUri`, not `code`.

## LM tools

| Tool | Use |
|---|---|
| `get-syntax-docs-mermaid` | Fetch syntax docs for a diagram type — do this *before* authoring an unfamiliar one |
| `mermaid-diagram-validator` | Validate syntax. Required before presenting any diagram |
| `mermaid-diagram-preview` | Render a live preview in VS Code. Required after generating |

## VS Code commands

Invoke via the Command Palette or the command API. Do not invent command IDs — prefer writing
or editing a `.mmd` file when no command is needed.

| Command | ID | Notes |
|---|---|---|
| Preview | `mermaidChart.preview` | Requires an open `.mmd` / `.mermaid` editor |
| Create Diagram | `mermaidChart.createMermaidFile` | Demo flowchart + side-by-side preview |
| Repair Diagram | `mermaidChart.repairDiagram` | **Consumes Mermaid AI credits — tell the user first** |
| Improve Diagram | `mermaidChart.improveDiagram` | Layout and styling variants via the LM API |
| Install AI Skills | `mermaidChart.installAiSkills` | Reinstalls this pack — see the caveat below |

Generation commands (need GitHub Copilot): `mermaidChart.generateDiagramFromCode`,
`generateCloudDiagram`, `generateERDiagram`, `generateDockerDiagram`,
`mermaidChart.openCopilotChat`.

Cloud commands: `mermaidChart.login` / `logout`,
`mermaidChart.connectDiagramToMermaidChart`, `mermaidChart.syncDiagramWithMermaid` (only for
diagrams whose frontmatter already carries an `id:`).

## `@mermaid-chart` slash commands

Prefer these for complex generation over hand-authoring.

| Command | Produces |
|---|---|
| `/generate_diagram_from_code` | General diagram from any source file |
| `/generate_execution_sequence` | Sequence diagram from code flow |
| `/generate_er_diagram` | ER diagram from schema or models |
| `/generate_cloud_architecture_diagram` | Cloud / CI-CD architecture |
| `/generate_docker_diagram` | Architecture from Dockerfiles |
| `/generate_c4_topdown_architecture` | C4 top-down architecture |
| `/analyze_code_ownership` | Code ownership diagram |
| `/generate_dependency_diagram` | Dependency / security visualisation |

## Sync-managed diagrams

Diagrams updated by the Mermaid Chart GitHub Sync app (or a pre-commit regenerate) are managed
by the extension. **Do not hand-rewrite them.** Use `mermaidChart.reviewAppCommits` to open the
review flow and `mermaidChart.regenerateDiagramWithMermaidAI` to regenerate from source.
Accept / reject / diff stay in the extension UI.

## Caveat

The Mermaid extension may reinstall `.cursor/instructions/mermaid.instructions.md` with
`applyTo: "**"`, which loads this content into *every* request in the repo. If that file
reappears, delete it — this skill replaces it, and the skill is loaded on demand instead.

Full command list: <https://marketplace.visualstudio.com/items?itemName=MermaidChart.vscode-mermaid-chart>

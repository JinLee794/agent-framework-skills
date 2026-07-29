---
name: skill-pack-audit
description: "Audit a skill pack for duplication, routing drift, description collisions, broken references, and always-on context cost. Produces a findings report and a prioritised fix list. Load when adding a skill to an existing pack, when the agent loads the wrong skill or two overlapping ones, when a fact has been restated in several files, or when asked to review, optimise, slim, or reorganise .cursor/skills."
license: MIT
metadata:
  author: MAFVoiceSeed
  version: "1.0.0"
  last-reviewed: "2026-07-28"
  verified-against: "Cursor Agent Skills and Rules docs, 2026-07"
---

# Skill Pack Audit

A skill pack degrades in predictable ways: routing tables get copied, the same version fact
gets restated, two descriptions start competing for the same task, and the always-on tier
quietly grows. This is the review that finds those.

Adjacent, different job: `maf-dev-loop/references/skill-sync.md` checks whether a claim is
**still true**. This checks whether it is in the **right place, exactly once**.

## Invariants

Every finding below is a violation of one of these. State which one when reporting.

1. **One routing table.** It lives in `.github/copilot-instructions.md`.
  `.cursor/rules/repository.mdc` imports it rather than duplicating it. A skill may link to a
  sibling for a specific reason; it may not list them all.
2. **One owner per falsifiable fact.** A version number, symbol name, enum spelling, or removed
   API belongs to the skill that owns that SDK surface. Everywhere else, cite the owner.
   Exactly one second copy is allowed: a row in a conformance grep table, because there the
   string *is* the search pattern.
3. **Descriptions partition the task space.** Two skills must not plausibly answer the same
   request. Where boundaries are close, say so with an explicit `NOT for … — load X instead`.
4. **Universal rules live in the always-on tier.** A rule that applies to all work must not sit
   inside a task-scoped skill, or it is only conditionally reachable.
5. **The loaded tier stays small.** `SKILL.md` should be roughly a third of its skill's total;
   the rest belongs in `references/`.
6. **Every reference resolves.**

## Procedure

Run all six. Each is cheap and each catches a different class.

### 1. Inventory and size distribution

```powershell
Get-ChildItem .cursor\skills -Recurse -Filter *.md |
  Sort-Object FullName |
  ForEach-Object { [pscustomobject]@{
      Path  = $_.FullName.Replace("$PWD\", '')
      Lines = (Get-Content $_.FullName).Count } } |
  Format-Table -AutoSize
```

For each skill compute `SKILL.md ÷ (SKILL.md + references)`. Report the ratios together — the
outlier is the finding, not any absolute threshold. A skill much above its peers has reference
material sitting in the always-loaded tier (invariant 5).

### 2. Reference integrity

Extract every non-HTTP markdown link and test the path.

```powershell
Get-ChildItem .cursor\skills -Recurse -Filter *.md | ForEach-Object {
  $f = $_
  [regex]::Matches((Get-Content $f.FullName -Raw), '\]\((?!https?:)([^)#]+)') | ForEach-Object {
    $rel = $_.Groups[1].Value.Trim()
    if (-not (Test-Path (Join-Path $f.Directory.FullName $rel))) {
      "$($f.FullName.Replace("$PWD\",'')) -> $rel"
    }
  }
}
```

Multi-line PowerShell can be mangled when pasted into some terminals — if it errors, save it to
a temp `.ps1` and run that rather than collapsing it to one line.

### 3. Repeated-fact scan

The core of the audit. Grep the pack for its own falsifiable claims, then count files per fact.

Build the term list from what the pack actually asserts — removed classes, renamed parameters,
enum spellings, pinned versions, required call sites. Then one regex with alternation:

```
<RemovedClassName>|<enum_spelling>|<RequiredCallSite>|<PinnedVersion>
```

Use the literal terms from the pack under audit, not these placeholders — and keep them out of
this file, or the audit will match itself and inflate every count by one.

Report as a table of *fact → file count*. Anything above 2 violates invariant 2. Sort
descending; the top row is usually the one that has already drifted.

A count of 2 is only clean when the second hit is the conformance grep table. Two hits inside
the owning skill (its `SKILL.md` and one of its own references) is also acceptable — the
invariant is one owning *skill*, not one file.

For each violation, name the owner (the skill documenting that SDK surface), keep the statement
there, and replace the others with a one-line citation.

### 4. Description collision check

Read only the `name` + `description` of every skill — that is all the agent sees at discovery.
Then, for each, ask: *which requests would load this and nothing else?*

Flag a collision when two descriptions share a domain noun (`retrieval`, `memory`, `tools`,
`config`). Fix by adding an explicit exclusion to **both** descriptions, not just one:

```yaml
description: "… Load for X, Y, Z. NOT for <adjacent thing> — load <other-skill> for that."
```

Also check: `name` matches the folder name exactly, and any description containing a colon is
quoted. Both fail silently.

### 5. Routing-surface count

Grep for the header row of your routing table — in this pack, a table whose columns are Task
and Skill. More than one hit is invariant 1.

Prose counts (`"Six skills live in…"`, `"Four sibling
skills…"`) are the reliable tell that copies exist and have to be hand-synced — treat any such
sentence as a defect and delete the number.

### 6. Always-on budget

Add up everything loaded on **every** request: each `.cursor/rules/*.mdc` with
`alwaysApply: true`, any applicable `AGENTS.md`, and all skill descriptions. Include content
imported by an always-on rule once.

`alwaysApply: true` is the usual culprit. A rule that is irrelevant to most tasks in the repo
should be a skill instead — same content, loaded on demand. Watch for user and team rules,
which can add broad context outside the repository.

## Reporting

Order findings by cost, not severity: how much context does this waste, or how many places must
change when one SDK fact changes. Each finding gets:

- the invariant violated,
- a file-and-line citation, not a paraphrase,
- evidence of drift where it exists — an already-inconsistent copy is worth more than a
  hypothetical one,
- a concrete fix.

Then split the fixes: apply defects with one correct answer (broken links, name mismatches,
missing exclusions) directly; ask before structural moves, since those encode an opinion about
what each skill is for.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| Reporting duplication without counting files | The count is what makes it actionable |
| Deduplicating by deleting the better-written copy | Keep the owner's version; the owner is the skill that owns the SDK surface |
| Adding a skill to fix overlap | Usually the fix is moving a rule up to the always-on tier, which removes content |
| Enforcing a fixed SKILL.md line limit | Compare skills to each other; the outlier is the signal |
| Treating a conformance grep table as duplication | Its rows are search patterns, and are the one sanctioned second copy |
| Auditing truth and placement in one pass | Different evidence, different fix — run `skill-sync` separately |

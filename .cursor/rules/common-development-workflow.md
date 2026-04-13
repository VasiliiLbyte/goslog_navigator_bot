# Development Workflow

> This file extends [common/git-workflow.md](./git-workflow.md) with the full feature development process that happens before git operations.

The Feature Implementation Workflow describes the development pipeline: research, planning, TDD, code review, and then committing to git.

## Feature Implementation Workflow

### Task Profiles

Choose the workflow depth based on change risk:

- **quick-fix**: tiny bug fix, doc update, refactor without behavior change.
- **feature**: new behavior, non-trivial refactor, cross-module change.
- **critical**: auth/security, payments, data integrity, concurrency, migrations, externally visible API changes.

0. **Research & Reuse**
   - **quick-fix:** optional, do lightweight local search first.
   - **feature/critical:** mandatory.
   - **GitHub code search first:** Run `gh search repos` and `gh search code` to find existing implementations, templates, and patterns before writing anything new.
   - **Library docs second:** Use Context7 or primary vendor docs to confirm API behavior, package usage, and version-specific details before implementing.
   - **Exa only when the first two are insufficient:** Use Exa for broader web research or discovery after GitHub search and primary docs.
   - **Check package registries:** Search npm, PyPI, crates.io, and other registries before writing utility code. Prefer battle-tested libraries over hand-rolled solutions.
   - **Search for adaptable implementations:** Look for open-source projects that solve 80%+ of the problem and can be forked, ported, or wrapped.
   - Prefer adopting or porting a proven approach over writing net-new code when it meets the requirement.

1. **Plan First**
   - **quick-fix:** short inline plan is enough.
   - **feature/critical:** use **planner** agent to create implementation plan.
   - Generate planning docs before coding: PRD, architecture, system_design, tech_doc, task_list
   - Identify dependencies and risks
   - Break down into phases

2. **TDD Approach**
   - **quick-fix:** add or update focused regression tests for changed behavior.
   - **feature/critical:** use full TDD with **tdd-guide** agent (RED -> GREEN -> IMPROVE).
   - Verify coverage targets according to `common/testing.md`.

3. **Code Review**
   - **quick-fix:** reviewer optional for low-risk localized edits.
   - **feature/critical:** use **code-reviewer** agent immediately after writing code.
   - Address CRITICAL and HIGH issues
   - Fix MEDIUM issues when possible

4. **Commit & Push**
   - Detailed commit messages
   - Follow conventional commits format
   - See [git-workflow.md](./git-workflow.md) for commit message format and PR process

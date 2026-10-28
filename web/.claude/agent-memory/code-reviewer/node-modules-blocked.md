---
name: node-modules-blocked
description: A project hook (scout-block.cjs + .claude/.ckignore) blocks Read/Bash access to node_modules paths; verify library internals another way
metadata:
  type: reference
---

Reading anything under `web/node_modules` (Read tool or a Bash command whose text contains `node_modules`) is blocked by `.claude/hooks/scout-block.cjs`, configured by `.claude/.ckignore`.

**Why:** the hook keeps vendored code out of the agent's context. Do not edit `.ckignore` to get around it.

**How to apply:** to check library behaviour (drei, three, R3F), fetch the upstream source with WebFetch from raw.githubusercontent.com, or run `node --input-type=module -e "import ... from 'three/...'"` with cwd `web/`. Bare imports resolve against the installed versions without naming the node_modules path.

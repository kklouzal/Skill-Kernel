---
name: autoskill-before-prompt-build
description: "Optionally inject a tiny fail-soft cached AutoSkill routing hint."
metadata: {"openclaw":{"events":["before_prompt_build"]}}
---

# autoskill-before-prompt-build

Requests a tiny cached context hint from the sidecar. This hook never calls an LLM synchronously.


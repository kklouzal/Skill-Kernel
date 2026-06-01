# OpenClaw Seam Notes

These notes are the current Phase 0 grounding from the local OpenClaw checkout at `/home/kklouzal/openclaw-git/openclaw`.

## Plugin-Owned Hook Package Shape

Observed fixture: `/home/kklouzal/openclaw-git/openclaw/src/hooks/plugin-hooks.test.ts`.

The fixture creates:

- `.codex-plugin/plugin.json`;
- `hooks/<hook-name>/HOOK.md`;
- `hooks/<hook-name>/handler.js`;
- plugin manifest field `hooks: "hooks"`;
- HOOK frontmatter `metadata.openclaw.events`.

This repo mirrors that shape under `plugin/autoskill/`.

## Hook Names Used in the Bootstrap

Grounded by local tests and hook type references:

- `model_call_started`
- `model_call_ended`
- `llm_input`
- `llm_output`
- `message_sent`
- `before_prompt_build`
- `before_tool_call`
- `after_tool_call`
- `tool_result_persist`

The message receive event naming still needs a live installed-plugin smoke test. The scaffold includes both `message_received` and `message:received` metadata aliases until Phase 0 confirms the exact current event key.

## Prompt Context Hook

`before_prompt_build` is the correct new-work hook for prompt context injection. The bootstrap plugin uses it only for a fail-soft cached sidecar hint and never for synchronous LLM calls.

## Tool Hooks

`before_tool_call` and `after_tool_call` are the relevant attribution/capture hooks. The bootstrap `before_tool_call` handler captures redacted metadata and does not block yet.

## Validation Note

`openclaw plugins validate --root ... --entry ...` validates simple `defineToolPlugin` metadata. The AutoSkill bootstrap plugin is a hook plugin, not a simple tool plugin, so that command currently reports that `src/index.js` does not expose `defineToolPlugin` metadata. Use a real installed-plugin smoke test or OpenClaw hook loader fixture for Phase 0 validation instead.


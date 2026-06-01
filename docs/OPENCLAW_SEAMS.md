# OpenClaw Seam Notes

These notes are the current Phase 0 grounding from the local OpenClaw checkout at `/home/kklouzal/openclaw-git/openclaw`.

## Plugin-Owned Hook Package Shape

Observed fixtures:

- `/home/kklouzal/openclaw-git/openclaw/src/hooks/plugin-hooks.test.ts`
  covers standalone hook-package installation.
- `/home/kklouzal/openclaw-git/openclaw/src/plugins/loader.test.ts`
  covers runtime plugin typed-hook registration through `api.on(...)`.

Standalone hook packages can use:

- `.codex-plugin/plugin.json`;
- `hooks/<hook-name>/HOOK.md`;
- `hooks/<hook-name>/handler.js`;
- plugin manifest field `hooks: "hooks"`;
- HOOK frontmatter `metadata.openclaw.events`.

The AutoSkill bootstrap is a runtime plugin, not a metadata-only Codex bundle.
It uses `openclaw.plugin.json` plus `package.json#openclaw.extensions` pointing at
`plugin/autoskill/src/index.js`, and the runtime entry registers typed hooks with
`api.on(...)`. Do not add `.codex-plugin/plugin.json` back to this package; that
causes OpenClaw to load it as a Codex bundle with zero runtime hooks.

## Hook Names Used in the Bootstrap

Grounded by local tests and hook type references:

- `model_call_started`
- `model_call_ended`
- `llm_input`
- `llm_output`
- `message_received`
- `message_sent`
- `gateway_start`
- `before_prompt_build`
- `before_tool_call`
- `after_tool_call`
- `tool_result_persist`

Installed-plugin smoke proof:

- `openclaw --dev plugins install --link /Warehouse/SkillKernel/plugin/autoskill`
- `openclaw --dev plugins inspect autoskill --json --runtime`
- Result after dev-profile hook policy enabled:
  `status=loaded`, `imported=true`, `hookCount=11`, diagnostics empty.

Required config for full hook coverage:

```json
{
  "plugins": {
    "entries": {
      "autoskill": {
        "enabled": true,
        "hooks": {
          "allowConversationAccess": true,
          "allowPromptInjection": true
        }
      }
    }
  }
}
```

Without `allowConversationAccess`, OpenClaw correctly blocks the non-bundled
`llm_input` and `llm_output` typed hooks. Without `allowPromptInjection`, runtime
context hints from `before_prompt_build` are blocked.

## Prompt Context Hook

`before_prompt_build` is the correct new-work hook for prompt context injection. The bootstrap plugin uses it only for a fail-soft cached sidecar hint and never for synchronous LLM calls.

## Tool Hooks

`before_tool_call` and `after_tool_call` are the relevant attribution/capture hooks. The bootstrap `before_tool_call` handler captures redacted metadata and does not block yet.

## Validation Note

`openclaw plugins validate --root ... --entry ...` validates simple
`defineToolPlugin` metadata. The AutoSkill bootstrap plugin is a runtime hook
plugin, not a simple tool plugin, so use `plugins inspect --runtime` and focused
Node hook tests for Phase 0 validation.

For generated skill loading, the active runtime root is the workspace skill root:
`<workspaceDir>/skills/autoskill/<slug>/SKILL.md`. A dev-profile smoke proved a
fixture there appears as `source='openclaw-workspace'`, `eligible=true`, and
`modelVisible=true`. A paired fixture under `<workspaceDir>/.autoskill/archive`
did not appear in normal or `--eligible` skill discovery, so the archive root is
outside OpenClaw's runtime skill loader.

Hook capture treats current-event forwarding and old-spool replay as separate
failure domains. The current event is spooled only when its own ingest forwarding
fails. Replay of older spool records is best-effort after a successful current
forward and must not re-spool or report the current event as failed.

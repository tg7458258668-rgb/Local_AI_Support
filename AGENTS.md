## Skill Startup Policy

On every new Codex session, treat these installed skills as globally available:

- `frontend-design`
- `ui-ux-pro-max`

For any task involving frontend UI, web pages, dashboards, landing pages, React components, HTML/CSS layouts, visual design, UX review, accessibility, responsive behavior, typography, colors, animation, or product interface polish:

1. Use `frontend-design` for visual direction, aesthetic quality, and production-grade frontend execution.
2. Use `ui-ux-pro-max` for UI/UX rules, accessibility, interaction patterns, design-system checks, responsive behavior, typography, colors, charts, and stack-specific guidance.
3. When useful, run the helper scripts in `/Users/ai_studio/.codex/skills/ui-ux-pro-max/scripts/` to query design-system, color, style, typography, UX, chart, product, and stack recommendations.

These skills do not need to be used for pure backend, database, infrastructure, or non-visual automation tasks.

## gstack Compatibility

Codex may expose `AskUserQuestion` as `request_user_input`. If `request_user_input` is unavailable in the current Codex mode even though a gstack skill asks for `AskUserQuestion`, ask the same decision question in normal chat and wait for the user's reply. Preserve the gstack rule of asking one decision at a time.

This project has enabled Codex's `default_mode_request_user_input` feature in `~/.codex/config.toml`, but existing Codex sessions may need a new thread or app restart before the tool becomes available.

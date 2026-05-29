/**
 * set-feature-flags.ts
 *
 * Writes feature flags to localStorage in a CDT Chrome session via the
 * chrome-proxy HTTP sidecar (localhost:9223), then reloads the page.
 *
 * Used by:
 *   - Architect agent (regression-agent) before selector verification
 *   - test-executor runbook (exploratory-test-agent) before test scenarios
 *
 * Usage:
 *   npx ts-node --transpile-only scripts/set-feature-flags.ts \
 *     --flags=feature-case-agent,feature-case-agent-exhibit \
 *     --action=on \
 *     --session=unit-1
 *
 *   --flags    comma-separated flag names (omit when --action=clear)
 *   --action   on (default) | off | clear
 *   --session  CDT session_id (default: "default")
 */

const SIDECAR_URL = "http://localhost:9223/call";

async function sidecarCall(tool: string, args: Record<string, unknown>, sessionId: string): Promise<string> {
  const res = await fetch(SIDECAR_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool, arguments: args, session_id: sessionId }),
  });
  const body = await res.json() as { result?: { content?: Array<{ text?: string }> }; error?: string };
  if (body.error) throw new Error(`sidecar ${tool} failed: ${body.error}`);
  const text = body.result?.content?.[0]?.text ?? "";
  const match = text.match(/```json\n([\s\S]*?)\n```/);
  return match ? JSON.parse(match[1]) : text;
}

async function main() {
  const args = Object.fromEntries(
    process.argv.slice(2)
      .filter(a => a.startsWith("--"))
      .map(a => {
        const [k, v] = a.slice(2).split("=");
        return [k, v ?? "true"];
      })
  );

  const flagsArg = args["flags"] ?? "";
  const action   = args["action"]  ?? "on";
  const session  = args["session"] ?? "default";
  const flags    = flagsArg.split(",").map(f => f.trim()).filter(Boolean);

  if (action !== "on" && action !== "off" && action !== "clear") {
    console.error("❌ --action must be 'on', 'off', or 'clear'");
    process.exit(1);
  }
  if (flags.length === 0 && action !== "clear") {
    console.error("❌ --flags is required unless --action=clear");
    process.exit(1);
  }

  const script = action === "clear"
    ? `() => { localStorage.removeItem('enabledFeatureFlags'); return ''; }`
    : action === "on"
    ? `() => {
        const raw = localStorage.getItem('enabledFeatureFlags') || '';
        const current = raw.split(',').filter(Boolean);
        const next = Array.from(new Set([...current, ${flags.map(f => JSON.stringify(f)).join(", ")}]));
        localStorage.setItem('enabledFeatureFlags', next.join(','));
        return localStorage.getItem('enabledFeatureFlags');
      }`
    : `() => {
        const raw = localStorage.getItem('enabledFeatureFlags') || '';
        const remove = new Set(${JSON.stringify(flags)});
        const next = raw.split(',').filter(Boolean).filter(f => !remove.has(f));
        localStorage.setItem('enabledFeatureFlags', next.join(','));
        return localStorage.getItem('enabledFeatureFlags');
      }`;

  const stored = await sidecarCall("evaluate_script", { function: script }, session);
  console.log(`   [${session}] localStorage.enabledFeatureFlags = "${stored}"`);

  await sidecarCall("navigate_page", { type: "reload" }, session);
  console.log(`✅ feature flags ${action}: [${flags.join(", ") || "(all cleared)"}] — session=${session} — page reloaded`);
}

main().catch(e => {
  console.error("❌ set-feature-flags failed:", e.message);
  process.exit(1);
});

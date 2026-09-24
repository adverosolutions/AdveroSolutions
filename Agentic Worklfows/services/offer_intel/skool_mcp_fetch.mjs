// Offer Intel: read-only Skool fetch through skool-mcp's own client.
// The client loads its own cookie config; this script never touches it.
// Two GET reads only, nothing that writes to Skool.
//
// Usage:
//   node skool_mcp_fetch.mjs <clientPath> feed <group> <labelId> <page>
//   node skool_mcp_fetch.mjs <clientPath> comments <postId> <groupId>
//
// Prints one JSON object on stdout. On error: one short line on stderr, exit 1.
import { pathToFileURL } from "node:url";

// 50 or 100 answers HTTP 400, so 25 top-level comments is the most one call returns.
const LIMIT = "25";

function fail(err) {
  const text = String((err && err.message) || err).replace(/\s+/g, " ").trim();
  process.stderr.write(text.slice(0, 300) + "\n");
  process.exit(1);
}

async function main() {
  const [clientPath, mode, ...args] = process.argv.slice(2);
  if (!clientPath || !mode) {
    throw new Error("usage: skool_mcp_fetch.mjs <clientPath> feed|comments ...");
  }
  const client = await import(pathToFileURL(clientPath).href);

  if (mode === "feed") {
    const [group, label, page] = args;
    if (!group || !label || !page) throw new Error("feed needs <group> <labelId> <page>");
    const data = await client.nextDataRequest("/" + encodeURIComponent(group), {
      group,
      p: String(page),
      s: "newest",
      c: label,
    });
    const props = (data && data.pageProps) || {};
    // Never print props.self: it holds the logged-in account's details.
    return { self: !!props.self, total: props.total, postTrees: props.postTrees || [] };
  }

  if (mode === "comments") {
    const [postId, groupId] = args;
    if (!postId || !groupId) throw new Error("comments needs <postId> <groupId>");
    return await client.api2Request("/posts/" + encodeURIComponent(postId) + "/comments", {
      method: "GET",
      queryParams: { "group-id": groupId, limit: LIMIT, pinned: "true" },
    });
  }

  throw new Error("mode must be feed or comments");
}

try {
  const out = await main();
  process.stdout.write(JSON.stringify(out));
} catch (err) {
  fail(err);
}

export function GET() {
  return Response.json(
    {
      faro_collector_url: process.env.FARO_COLLECTOR_URL || null,
      release_version: process.env.RELEASE_VERSION || "unknown",
    },
    { headers: { "cache-control": "no-store" } },
  );
}

import type { RefSearchItem } from "@/contracts/creator";
import { creatorRequest } from "./client";

export function searchRefs(
  projectId: string,
  query = "",
  types: RefSearchItem["type"][] = [],
  limit = 20,
): Promise<{ items: RefSearchItem[] }> {
  const params = new URLSearchParams({ query, limit: String(limit) });
  if (types.length) params.set("types", types.join(","));
  return creatorRequest(
    `/projects/${encodeURIComponent(projectId)}/refs?${params}`,
  );
}

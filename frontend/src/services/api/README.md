# API service architecture

`client.ts` — the one typed `apiRequest<T>()` function every feature
hook calls through. Handles the request/response/error envelope from
[`ARCHITECTURE.md`](../../../../docs/ARCHITECTURE.md) section 5, Bearer
auth, and JSON serialization once, centrally.

`query-keys.ts` — the query-key factory every feature hook registers
its namespace in.

**No feature endpoints are wired yet, by design (Phase 1 scope).** The
one route that already exists on the backend today,
`GET /api/health`, predates this envelope standard (it returns a raw
`{"status": "ok"}` dict, not `{"data": ...}`) — reconciling it is
explicitly `ARCHITECTURE.md` section 5's own "(new, M8+)" scope, not
this phase's. Wiring a hook against it now would either misrepresent
the standard or require a one-off exception in `client.ts`; neither
belongs in a foundation phase.

**The pattern every future feature hook follows**, once a real,
envelope-compliant endpoint exists:

```ts
// services/api/<feature>.ts
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { queryKeys } from "./query-keys";

interface Conversation {
  id: string;
  title: string;
}

export function useConversations() {
  return useQuery({
    queryKey: [...queryKeys.all, "conversations"],
    queryFn: () => apiRequest<Conversation[]>("/conversations"),
  });
}
```

Every value a component reads from the backend goes through a hook
shaped like this one — never a raw `fetch` call inside a component
body, per `ARCHITECTURE.md` section 13.

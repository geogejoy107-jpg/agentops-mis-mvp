export type MemoryReviewDecision = "approve" | "reject";

export type MemoryReviewIdempotencyScope = {
  userId: string;
  workspaceId: string;
  memoryId: string;
  decision: MemoryReviewDecision;
};

export type MemoryReviewCandidate = {
  memory_id: string;
  review_status: string;
};

export type MemoryReviewSessionStorage = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem" | "key" | "length"
>;

const STORAGE_PREFIX = "agentops:memory-review:idempotency:v1:";
const IDEMPOTENCY_KEY_PATTERN = /^memory-review-[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export const DIRECT_MEMORY_CANDIDATE_QUEUE_LIMIT = 200;

function encodeScopeSegment(value: string, field: string): string {
  if (!value) throw new Error(`memory review ${field} is required`);
  return encodeURIComponent(value);
}

export function memoryReviewIdempotencyStorageKey(scope: MemoryReviewIdempotencyScope): string {
  return `${STORAGE_PREFIX}${[
    encodeScopeSegment(scope.userId, "user id"),
    encodeScopeSegment(scope.workspaceId, "workspace id"),
    encodeScopeSegment(scope.memoryId, "memory id"),
    scope.decision,
  ].join(":")}`;
}

export function parseMemoryReviewIdempotencyStorageKey(
  storageKey: string,
): MemoryReviewIdempotencyScope | null {
  if (!storageKey.startsWith(STORAGE_PREFIX)) return null;
  const parts = storageKey.slice(STORAGE_PREFIX.length).split(":");
  if (parts.length !== 4 || !["approve", "reject"].includes(parts[3])) return null;
  try {
    const [userId, workspaceId, memoryId] = parts.slice(0, 3).map(decodeURIComponent);
    if (!userId || !workspaceId || !memoryId) return null;
    return {
      userId,
      workspaceId,
      memoryId,
      decision: parts[3] as MemoryReviewDecision,
    };
  } catch {
    return null;
  }
}

export function getMemoryReviewSessionStorage(): MemoryReviewSessionStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function acquireMemoryReviewIdempotencyKey(
  storage: MemoryReviewSessionStorage,
  scope: MemoryReviewIdempotencyScope,
  createKey: () => string = () => `memory-review-${crypto.randomUUID()}`,
): { key: string; persisted: boolean; storageKey: string } {
  const storageKey = memoryReviewIdempotencyStorageKey(scope);
  try {
    const existing = storage.getItem(storageKey);
    if (existing && IDEMPOTENCY_KEY_PATTERN.test(existing)) {
      return { key: existing, persisted: true, storageKey };
    }
  } catch {
    // Continue with an in-memory fallback in the caller.
  }

  const key = createKey();
  if (!IDEMPOTENCY_KEY_PATTERN.test(key)) {
    throw new Error("memory review idempotency key generator returned an invalid key");
  }
  try {
    storage.setItem(storageKey, key);
    return { key, persisted: storage.getItem(storageKey) === key, storageKey };
  } catch {
    return { key, persisted: false, storageKey };
  }
}

export function reconcileMemoryReviewIdempotencyKeys(
  storage: MemoryReviewSessionStorage,
  userId: string,
  workspaceId: string,
  directCandidates: readonly MemoryReviewCandidate[],
): number {
  const queueIsExhaustive = directCandidates.length < DIRECT_MEMORY_CANDIDATE_QUEUE_LIMIT;
  const scopedKeys: string[] = [];
  try {
    for (let index = 0; index < storage.length; index += 1) {
      const storageKey = storage.key(index);
      if (storageKey) scopedKeys.push(storageKey);
    }
  } catch {
    return 0;
  }

  let removed = 0;
  for (const storageKey of scopedKeys) {
    const scope = parseMemoryReviewIdempotencyStorageKey(storageKey);
    if (!scope || scope.userId !== userId || scope.workspaceId !== workspaceId) continue;
    const targetRows = directCandidates.filter((memory) => memory.memory_id === scope.memoryId);
    if (targetRows.some((memory) => memory.review_status === "candidate")) continue;
    if (!targetRows.length && !queueIsExhaustive) continue;
    try {
      storage.removeItem(storageKey);
      removed += 1;
    } catch {
      // A later successful direct refresh can retry cleanup.
    }
  }
  return removed;
}

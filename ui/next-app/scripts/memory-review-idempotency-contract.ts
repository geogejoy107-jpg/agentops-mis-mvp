import assert from "node:assert/strict";
import {
  acquireMemoryReviewIdempotencyKey,
  DIRECT_MEMORY_CANDIDATE_QUEUE_LIMIT,
  memoryReviewIdempotencyStorageKey,
  reconcileMemoryReviewIdempotencyKeys,
  type MemoryReviewIdempotencyScope,
  type MemoryReviewSessionStorage,
} from "../src/lib/memoryReviewIdempotency";

class FakeSessionStorage implements MemoryReviewSessionStorage {
  private readonly values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

const storage = new FakeSessionStorage();
const scope: MemoryReviewIdempotencyScope = {
  userId: "usr_approver_a",
  workspaceId: "ws_review",
  memoryId: "mem_candidate_1",
  decision: "approve",
};
const generated = "memory-review-123e4567-e89b-42d3-a456-426614174000";
const first = acquireMemoryReviewIdempotencyKey(storage, scope, () => generated);
assert.equal(first.persisted, true);
assert.equal(first.key, generated);

const remounted = acquireMemoryReviewIdempotencyKey(
  storage,
  { ...scope },
  () => "memory-review-00000000-0000-4000-8000-000000000000",
);
assert.equal(remounted.key, generated, "remount must reuse the persisted key");

for (const changedScope of [
  { ...scope, userId: "usr_approver_b" },
  { ...scope, workspaceId: "ws_other" },
  { ...scope, memoryId: "mem_candidate_2" },
  { ...scope, decision: "reject" as const },
]) {
  assert.notEqual(
    memoryReviewIdempotencyStorageKey(changedScope),
    first.storageKey,
    "every authorization and decision dimension must alter storage scope",
  );
}

assert.equal(
  reconcileMemoryReviewIdempotencyKeys(storage, scope.userId, scope.workspaceId, [
    { memory_id: scope.memoryId, review_status: "candidate" },
  ]),
  0,
  "a still-pending direct candidate must retain its key",
);
assert.equal(storage.getItem(first.storageKey), generated);

assert.equal(
  reconcileMemoryReviewIdempotencyKeys(storage, scope.userId, scope.workspaceId, [
    { memory_id: scope.memoryId, review_status: "approved" },
  ]),
  1,
  "a terminal direct queue row may release its key",
);
assert.equal(storage.getItem(first.storageKey), null);

const rejected = acquireMemoryReviewIdempotencyKey(storage, { ...scope, decision: "reject" }, () => generated);
assert.equal(
  reconcileMemoryReviewIdempotencyKeys(storage, scope.userId, scope.workspaceId, []),
  1,
  "a successful direct refresh that omits the target may release its key",
);
assert.equal(storage.getItem(rejected.storageKey), null);

const ambiguous = acquireMemoryReviewIdempotencyKey(storage, scope, () => generated);
const fullQueue = Array.from({ length: DIRECT_MEMORY_CANDIDATE_QUEUE_LIMIT }, (_, index) => ({
  memory_id: `mem_other_${index}`,
  review_status: "candidate",
}));
assert.equal(
  reconcileMemoryReviewIdempotencyKeys(storage, scope.userId, scope.workspaceId, fullQueue),
  0,
  "absence from a full bounded queue is ambiguous and must retain the key",
);
assert.equal(storage.getItem(ambiguous.storageKey), generated);

assert.equal(
  reconcileMemoryReviewIdempotencyKeys(storage, scope.userId, scope.workspaceId, [
    ...fullQueue.slice(0, -1),
    { memory_id: scope.memoryId, review_status: "rejected" },
  ]),
  1,
  "an explicit terminal row is proof even when the bounded queue is full",
);
assert.equal(storage.getItem(ambiguous.storageKey), null);

const isolated = acquireMemoryReviewIdempotencyKey(storage, { ...scope, workspaceId: "ws_other" }, () => generated);
assert.equal(reconcileMemoryReviewIdempotencyKeys(storage, scope.userId, scope.workspaceId, []), 0);
assert.equal(storage.getItem(isolated.storageKey), generated, "another workspace must remain isolated");

process.stdout.write("memory review idempotency contract: passed\n");

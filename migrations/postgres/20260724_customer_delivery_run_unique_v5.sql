-- Enforce the commercial invariant that a run can own at most one customer
-- delivery approval. The migration runner owns the surrounding transaction and
-- exact receipt.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $$
BEGIN
  IF EXISTS (
    SELECT approval.run_id
    FROM approvals approval
    WHERE approval.approval_kind='customer_delivery'
    GROUP BY approval.run_id
    HAVING COUNT(*)>1
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23505',
      MESSAGE='customer_delivery_approval_run_duplicate';
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_customer_delivery_run_unique
ON approvals(run_id)
WHERE approval_kind='customer_delivery';

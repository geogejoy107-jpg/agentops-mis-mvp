import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";

type MemoryCandidateRow = {
  memory_id: string;
  workspace_id: string;
  scope: string;
  memory_type: string;
  canonical_text: string;
  source_type: string;
  confidence: number;
  review_status: string;
  task_id: string | null;
  agent_id: string | null;
  created_at: string;
  updated_at: string;
};

export async function listWorkspaceMemoryCandidates(headers: Headers, workspaceId: unknown) {
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const rows = await client.query<MemoryCandidateRow>(
      `SELECT memory_id,workspace_id,scope,memory_type,canonical_text,source_type,confidence,
      review_status,task_id,agent_id,created_at,updated_at
      FROM memories
      WHERE workspace_id=$1 AND review_status='candidate'
      ORDER BY updated_at DESC,memory_id
      LIMIT 200`,
      [identity.workspaceId],
    );
    return {
      status: 200,
      body: rows.rows.map((row) => ({ ...row, credentials_omitted: true })),
    };
  });
}

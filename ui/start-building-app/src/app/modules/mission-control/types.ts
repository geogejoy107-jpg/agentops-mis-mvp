export interface SectionCopy {
  title: string;
  description: string;
  open: string;
  emptyTitle: string;
  emptyDescription?: string;
}

export interface AttentionView {
  id: string;
  title: string;
  summary: string;
  severity: string;
  route: string;
  source: string;
}

export interface WorkPackageView {
  id: string;
  taskId: string;
  title: string;
  owner: string;
  project: string;
  status: string;
  risk: string;
  evidence: number;
}

export interface WorkerLaneView {
  id: string;
  name: string;
  status: string;
}

export interface WorkforceView {
  available: boolean;
  status: string;
  laneCount: number;
  localDaemons: number;
  runningDaemons: number;
  stuckWork: number;
  lanes: WorkerLaneView[];
}

export interface ActivityView {
  id: string;
  title: string;
  status: string;
  route: string;
  meta: string;
}

export interface SpatialGridPoint {
  x: number;
  y: number;
}

export interface SpatialNormalizedPoint {
  x: number;
  y: number;
}

export interface SpatialPathRequest {
  width: number;
  height: number;
  start: SpatialGridPoint;
  goal: SpatialGridPoint;
  blocked?: ReadonlySet<string>;
}

const pointKey = (point: SpatialGridPoint): string => `${point.x},${point.y}`;
const heuristic = (a: SpatialGridPoint, b: SpatialGridPoint): number => Math.abs(a.x - b.x) + Math.abs(a.y - b.y);

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function normalizedPointToGrid(
  point: SpatialNormalizedPoint,
  width: number,
  height: number,
): SpatialGridPoint {
  return {
    x: clamp(Math.round((point.x / 100) * (width - 1)), 0, width - 1),
    y: clamp(Math.round((point.y / 100) * (height - 1)), 0, height - 1),
  };
}

export function gridPointToNormalized(
  point: SpatialGridPoint,
  width: number,
  height: number,
): SpatialNormalizedPoint {
  return {
    x: width <= 1 ? 50 : (point.x / (width - 1)) * 100,
    y: height <= 1 ? 50 : (point.y / (height - 1)) * 100,
  };
}

export function spatialBlockedKey(point: SpatialGridPoint): string {
  return pointKey(point);
}

export function findSpatialPath(request: SpatialPathRequest): SpatialGridPoint[] {
  const { width, height, start, goal } = request;
  const blocked = request.blocked || new Set<string>();
  if (width <= 0 || height <= 0) return [];

  const safeStart = {
    x: clamp(start.x, 0, width - 1),
    y: clamp(start.y, 0, height - 1),
  };
  const safeGoal = {
    x: clamp(goal.x, 0, width - 1),
    y: clamp(goal.y, 0, height - 1),
  };
  const startKey = pointKey(safeStart);
  const goalKey = pointKey(safeGoal);
  if (startKey === goalKey) return [safeStart];

  const open = new Set<string>([startKey]);
  const pointByKey = new Map<string, SpatialGridPoint>([[startKey, safeStart]]);
  const cameFrom = new Map<string, string>();
  const gScore = new Map<string, number>([[startKey, 0]]);
  const fScore = new Map<string, number>([[startKey, heuristic(safeStart, safeGoal)]]);

  while (open.size > 0) {
    let currentKey = "";
    let currentScore = Number.POSITIVE_INFINITY;
    for (const candidateKey of open) {
      const candidateScore = fScore.get(candidateKey) ?? Number.POSITIVE_INFINITY;
      if (candidateScore < currentScore || (candidateScore === currentScore && candidateKey < currentKey)) {
        currentKey = candidateKey;
        currentScore = candidateScore;
      }
    }

    const current = pointByKey.get(currentKey);
    if (!current) break;
    if (currentKey === goalKey) {
      const path: SpatialGridPoint[] = [current];
      let cursor = currentKey;
      while (cameFrom.has(cursor)) {
        cursor = cameFrom.get(cursor) as string;
        const point = pointByKey.get(cursor);
        if (!point) break;
        path.unshift(point);
      }
      return path;
    }

    open.delete(currentKey);
    const neighbors: SpatialGridPoint[] = [
      { x: current.x + 1, y: current.y },
      { x: current.x - 1, y: current.y },
      { x: current.x, y: current.y + 1 },
      { x: current.x, y: current.y - 1 },
    ];

    for (const neighbor of neighbors) {
      if (neighbor.x < 0 || neighbor.x >= width || neighbor.y < 0 || neighbor.y >= height) continue;
      const neighborKey = pointKey(neighbor);
      if (neighborKey !== goalKey && blocked.has(neighborKey)) continue;

      const tentative = (gScore.get(currentKey) ?? Number.POSITIVE_INFINITY) + 1;
      if (tentative >= (gScore.get(neighborKey) ?? Number.POSITIVE_INFINITY)) continue;

      cameFrom.set(neighborKey, currentKey);
      pointByKey.set(neighborKey, neighbor);
      gScore.set(neighborKey, tentative);
      fScore.set(neighborKey, tentative + heuristic(neighbor, safeGoal));
      open.add(neighborKey);
    }
  }

  return [safeStart, safeGoal];
}

export function interpolateSpatialPath(
  path: readonly SpatialNormalizedPoint[],
  progress: number,
): SpatialNormalizedPoint {
  if (path.length === 0) return { x: 50, y: 50 };
  if (path.length === 1) return path[0];

  const wrapped = ((progress % 1) + 1) % 1;
  const scaled = wrapped * (path.length - 1);
  const index = Math.min(path.length - 2, Math.floor(scaled));
  const local = scaled - index;
  const from = path[index];
  const to = path[index + 1];
  return {
    x: from.x + (to.x - from.x) * local,
    y: from.y + (to.y - from.y) * local,
  };
}

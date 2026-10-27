import { MAP_COLUMNS, MAP_ROWS } from '../maps/officeMap'

export type GridCoord = {
  column: number
  row: number
}

type Node = {
  column: number
  row: number
  g: number
  f: number
}

export default class PathfindingSystem {
  private walkableCells: ReadonlySet<string>
  private readonly mapColumns: number
  private readonly mapRows: number

  constructor(
    walkableCells: ReadonlySet<string>,
    mapColumns: number = MAP_COLUMNS,
    mapRows: number = MAP_ROWS,
  ) {
    this.walkableCells = walkableCells
    this.mapColumns = mapColumns
    this.mapRows = mapRows
  }

  setWalkableCells(walkableCells: ReadonlySet<string>) {
    this.walkableCells = walkableCells
  }

  isWalkable(
    column: number,
    row: number,
    dynamicObstacles?: ReadonlySet<string>,
  ): boolean {
    if (
      column < 0 ||
      column >= this.mapColumns ||
      row < 0 ||
      row >= this.mapRows
    ) {
      return false
    }

    const key = `${column},${row}`
    if (!this.walkableCells.has(key)) {
      return false
    }

    if (dynamicObstacles?.has(key)) {
      return false
    }

    return true
  }

  /**
   * Finds a 4-directional path between start and destination using A*.
   * Returns an array of waypoints (excluding start, ending at destination),
   * or empty array if start === destination, or null if no valid path exists.
   */
  findPath(
    start: GridCoord,
    destination: GridCoord,
    dynamicObstacles?: ReadonlySet<string>,
  ): GridCoord[] | null {
    // 1. Validate destination walkability
    if (!this.isWalkable(destination.column, destination.row, dynamicObstacles)) {
      return null
    }

    // 2. Trivial case: already at destination
    if (
      start.column === destination.column &&
      start.row === destination.row
    ) {
      return []
    }

    const startKey = `${start.column},${start.row}`
    const destKey = `${destination.column},${destination.row}`

    const openSet: Node[] = [
      {
        column: start.column,
        row: start.row,
        g: 0,
        f: this.heuristic(start, destination),
      },
    ]

    const cameFrom = new Map<string, GridCoord>()
    const gScore = new Map<string, number>([[startKey, 0]])
    const closedSet = new Set<string>()

    const cardinalDirections = [
      { column: 0, row: -1 }, // up
      { column: 0, row: 1 },  // down
      { column: -1, row: 0 }, // left
      { column: 1, row: 0 },  // right
    ]

    while (openSet.length > 0) {
      // Find node with lowest f score
      let lowestIndex = 0
      for (let i = 1; i < openSet.length; i += 1) {
        if (openSet[i].f < openSet[lowestIndex].f) {
          lowestIndex = i
        }
      }

      const current = openSet.splice(lowestIndex, 1)[0]
      const currentKey = `${current.column},${current.row}`

      if (currentKey === destKey) {
        return this.reconstructPath(cameFrom, current)
      }

      closedSet.add(currentKey)

      for (const dir of cardinalDirections) {
        const neighborCol = current.column + dir.column
        const neighborRow = current.row + dir.row
        const neighborKey = `${neighborCol},${neighborRow}`

        if (closedSet.has(neighborKey)) {
          continue
        }

        if (!this.isWalkable(neighborCol, neighborRow, dynamicObstacles)) {
          continue
        }

        const tentativeG = current.g + 1
        const recordedG = gScore.get(neighborKey) ?? Infinity

        if (tentativeG < recordedG) {
          cameFrom.set(neighborKey, { column: current.column, row: current.row })
          gScore.set(neighborKey, tentativeG)

          const f = tentativeG + this.heuristic({ column: neighborCol, row: neighborRow }, destination)

          const existingOpenNode = openSet.find(
            (node) => node.column === neighborCol && node.row === neighborRow,
          )

          if (existingOpenNode) {
            existingOpenNode.g = tentativeG
            existingOpenNode.f = f
          } else {
            openSet.push({
              column: neighborCol,
              row: neighborRow,
              g: tentativeG,
              f,
            })
          }
        }
      }
    }

    // No path found
    return null
  }

  private heuristic(a: GridCoord, b: GridCoord): number {
    return Math.abs(a.column - b.column) + Math.abs(a.row - b.row)
  }

  private reconstructPath(
    cameFrom: Map<string, GridCoord>,
    current: GridCoord,
  ): GridCoord[] {
    const path: GridCoord[] = [{ column: current.column, row: current.row }]
    let currKey = `${current.column},${current.row}`

    while (cameFrom.has(currKey)) {
      const prev = cameFrom.get(currKey)!
      path.unshift(prev)
      currKey = `${prev.column},${prev.row}`
    }

    // Exclude the starting point so path contains only subsequent waypoints
    path.shift()
    return path
  }
}


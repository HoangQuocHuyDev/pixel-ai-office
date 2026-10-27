import Character, { type VisualState } from '../characters/Character'
import type { CharacterDirection } from '../characters/characterDefinitions'
import { TILE_SIZE } from '../maps/officeMap'
import PathfindingSystem, { type GridCoord } from './PathfindingSystem'

export const DEFAULT_AGENT_SPEED = 80 // pixels per second
const MAX_WAIT_RETRIES = 3
const WAIT_DURATION_SECONDS = 0.6

export type AgentMovementState = {
  character: Character
  priority: number
  path: GridCoord[]
  currentTile: GridCoord
  destination: GridCoord | null
  finalFacing?: CharacterDirection
  isMoving: boolean
  waitTimer: number
  retryCount: number
}

export type DestinationReachedCallback = (
  characterId: string,
  destination: GridCoord,
) => void

export default class MovementSystem {
  private readonly pathfinding: PathfindingSystem
  private readonly agents = new Map<string, AgentMovementState>()
  private destinationReachedCallbacks: DestinationReachedCallback[] = []

  constructor(
    characters: Character[],
    pathfinding: PathfindingSystem,
  ) {
    this.pathfinding = pathfinding

    // Priority hierarchy for resolving corridor/space contention:
    // Manager (3) > Developer (2) > Researcher (1)
    const priorityMap: Record<string, number> = {
      manager: 3,
      developer: 2,
      researcher: 1,
    }

    for (const character of characters) {
      const id = character.definition.id
      const col = Math.floor(character.x / TILE_SIZE)
      const row = Math.floor((character.y - 1) / TILE_SIZE)

      this.agents.set(id, {
        character,
        priority: priorityMap[id] ?? 1,
        path: [],
        currentTile: { column: col, row: row },
        destination: null,
        isMoving: false,
        waitTimer: 0,
        retryCount: 0,
      })
    }
  }

  onDestinationReached(callback: DestinationReachedCallback) {
    this.destinationReachedCallbacks.push(callback)
  }

  /**
   * Plans and starts movement for an agent to the target grid coordinate.
   * Returns true if a valid path was found, false otherwise.
   */
  moveTo(
    characterId: string,
    destination: GridCoord,
    finalFacing?: CharacterDirection,
  ): boolean {
    const agent = this.agents.get(characterId)
    if (!agent) return false

    const startTile = this.getAgentGridCoord(agent.character)
    agent.currentTile = startTile

    // If already at destination
    if (
      startTile.column === destination.column &&
      startTile.row === destination.row
    ) {
      agent.path = []
      agent.isMoving = false
      agent.destination = destination
      if (finalFacing) {
        agent.character.setVisualState(agent.character.getVisualState(), finalFacing)
      }
      this.notifyDestinationReached(characterId, destination)
      return true
    }

    // Dynamic obstacles: other agents' current positions
    const blockedCells = this.getOtherAgentsPositions(characterId)

    const path = this.pathfinding.findPath(startTile, destination, blockedCells)
    if (!path || path.length === 0) {
      // If direct route is temporarily blocked by an agent, try finding any path ignoring dynamic obstacles
      const fallbackPath = this.pathfinding.findPath(startTile, destination)
      if (!fallbackPath || fallbackPath.length === 0) {
        return false
      }
      agent.path = fallbackPath
    } else {
      agent.path = path
    }

    agent.destination = destination
    agent.finalFacing = finalFacing
    agent.isMoving = true
    agent.waitTimer = 0
    agent.retryCount = 0

    return true
  }

  stop(
    characterId: string,
    visualState: VisualState = 'idle',
    facing?: CharacterDirection,
  ) {
    const agent = this.agents.get(characterId)
    if (!agent) return

    agent.path = []
    agent.isMoving = false
    agent.destination = null
    agent.waitTimer = 0
    agent.retryCount = 0
    agent.character.setVisualState(visualState, facing)
    agent.character.syncVisuals()
  }

  isCharacterMoving(characterId: string): boolean {
    const agent = this.agents.get(characterId)
    return agent ? agent.isMoving : false
  }

  getAgentGridCoord(character: Character): GridCoord {
    return {
      column: Math.floor(character.x / TILE_SIZE),
      row: Math.floor((character.y - 1) / TILE_SIZE),
    }
  }

  update(delta: number) {
    const dt = Math.min(delta, 50) / 1000 // delta in seconds, clamped

    for (const [id, agent] of this.agents.entries()) {
      if (!agent.isMoving) continue

      // Handle waiting / backoff
      if (agent.waitTimer > 0) {
        agent.waitTimer -= dt
        if (agent.waitTimer > 0) {
          continue
        }
      }

      if (agent.path.length === 0) {
        this.finishMovement(id, agent)
        continue
      }

      const nextWaypoint = agent.path[0]

      // Check collision/contention with other agents at next waypoint
      const contention = this.checkContention(id, agent, nextWaypoint)
      if (contention === 'wait') {
        agent.character.setVisualState('waiting')
        agent.waitTimer = WAIT_DURATION_SECONDS
        agent.retryCount += 1

        if (agent.retryCount > MAX_WAIT_RETRIES && agent.destination) {
          // Attempt to reroute around the blocked cell
          const dynamicObstacles = new Set<string>([
            `${nextWaypoint.column},${nextWaypoint.row}`,
            ...this.getOtherAgentsPositions(id),
          ])
          const start = this.getAgentGridCoord(agent.character)
          const newPath = this.pathfinding.findPath(start, agent.destination, dynamicObstacles)

          if (newPath && newPath.length > 0) {
            agent.path = newPath
            agent.retryCount = 0
            agent.waitTimer = 0
          } else {
            // Cannot reroute, stop safely
            this.stop(id, 'idle')
          }
        }
        continue
      }

      // Move toward next waypoint
      const targetPixelX = (nextWaypoint.column + 0.5) * TILE_SIZE
      const targetPixelY = (nextWaypoint.row + 1) * TILE_SIZE

      const dx = targetPixelX - agent.character.x
      const dy = targetPixelY - agent.character.y
      const distance = Math.hypot(dx, dy)
      const step = DEFAULT_AGENT_SPEED * dt

      const direction = this.computeDirection(dx, dy)

      if (distance <= step) {
        // Snap directly to waypoint tile center
        agent.character.setPosition(targetPixelX, targetPixelY)
        agent.currentTile = nextWaypoint
        agent.path.shift()
        agent.retryCount = 0

        if (agent.path.length === 0) {
          this.finishMovement(id, agent)
        } else {
          agent.character.setVisualState('walking', direction)
        }
      } else {
        // Linear movement along the axis
        agent.character.x += (dx / distance) * step
        agent.character.y += (dy / distance) * step
        agent.character.setVisualState('walking', direction)
      }

      agent.character.syncVisuals()
    }
  }

  destroy() {
    this.agents.clear()
    this.destinationReachedCallbacks = []
  }

  private finishMovement(id: string, agent: AgentMovementState) {
    agent.isMoving = false
    const reachedDest = agent.destination ?? agent.currentTile
    agent.destination = null

    if (agent.finalFacing) {
      agent.character.setVisualState('idle', agent.finalFacing)
    } else {
      agent.character.setVisualState('idle')
    }
    agent.character.syncVisuals()

    this.notifyDestinationReached(id, reachedDest)
  }

  private notifyDestinationReached(id: string, destination: GridCoord) {
    for (const callback of this.destinationReachedCallbacks) {
      callback(id, destination)
    }
  }

  private computeDirection(dx: number, dy: number): CharacterDirection {
    if (Math.abs(dx) > Math.abs(dy)) {
      return dx > 0 ? 'right' : 'left'
    }
    return dy > 0 ? 'down' : 'up'
  }

  private checkContention(
    agentId: string,
    agent: AgentMovementState,
    nextWaypoint: GridCoord,
  ): 'ok' | 'wait' {
    for (const [otherId, other] of this.agents.entries()) {
      if (otherId === agentId) continue

      const otherCoord = this.getAgentGridCoord(other.character)

      // 1. Is another agent currently on the next waypoint?
      const isOtherOnWaypoint =
        otherCoord.column === nextWaypoint.column &&
        otherCoord.row === nextWaypoint.row

      // 2. Is another agent also heading to the same waypoint as their immediate step?
      const isOtherHeadingToSame =
        other.isMoving &&
        other.path.length > 0 &&
        other.path[0].column === nextWaypoint.column &&
        other.path[0].row === nextWaypoint.row

      if (isOtherOnWaypoint || isOtherHeadingToSame) {
        // Lower priority yields and waits
        if (agent.priority < other.priority) {
          return 'wait'
        }
        // If other agent is stationary, we must wait regardless of priority
        if (!other.isMoving) {
          return 'wait'
        }
      }

      // 3. Proximity check (prevent visual overlap during continuous motion)
      const targetPixelX = (nextWaypoint.column + 0.5) * TILE_SIZE
      const targetPixelY = (nextWaypoint.row + 1) * TILE_SIZE
      const distToOther = Math.hypot(
        targetPixelX - other.character.x,
        targetPixelY - other.character.y,
      )

      if (distToOther < TILE_SIZE * 0.75) {
        if (agent.priority <= other.priority) {
          return 'wait'
        }
      }
    }

    return 'ok'
  }

  private getOtherAgentsPositions(excludeId: string): Set<string> {
    const blocked = new Set<string>()
    for (const [id, agent] of this.agents.entries()) {
      if (id === excludeId) continue
      const coord = this.getAgentGridCoord(agent.character)
      blocked.add(`${coord.column},${coord.row}`)
    }
    return blocked
  }
}

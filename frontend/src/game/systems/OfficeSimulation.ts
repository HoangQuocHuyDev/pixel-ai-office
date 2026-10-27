import Character from '../characters/Character'
import type { CharacterDirection } from '../characters/characterDefinitions'
import { MEETING_SPOTS } from '../maps/officeMap'
import type { OfficeFurnitureItem } from '../maps/officeLayout'
import MovementSystem from './MovementSystem'
import type { GridCoord } from './PathfindingSystem'
import type { AgentActivity, AgentActivityStatus } from '../../features/agents/types'
import { retroSFX } from '../utils/sfx'

export type AgentSimState =
  | 'SPAWN_WAIT'
  | 'WALKING_TO_WORK'
  | 'WORKING'
  | 'WALKING_TO_BREAK'
  | 'RESTING'
  | 'REMOTE_WALKING_TO_WORK'
  | 'REMOTE_WORKING'
  | 'REMOTE_FAILED'
  | 'WALKING_TO_MEETING'
  | 'IN_MEETING'
  | 'WALKING_FROM_MEETING'

export type HuddleSession = {
  initiatorId: string
  receiverId: string
  topic: string
  response: string
  stage: 'walking_to_meeting' | 'in_dialogue_step1' | 'in_dialogue_step2' | 'concluding'
  timer: number
}

type AgentConfig = {
  characterId: string
  character: Character
  workstation: GridCoord
  workFacing: CharacterDirection
  breakSpot: GridCoord
  breakFacing: CharacterDirection
  initialWaitSeconds: number
  workDurationSeconds: number
  restDurationSeconds: number
  currentState: AgentSimState
  timer: number
  remoteStatus: AgentActivityStatus | null
  remoteTaskTitle: string | null
}

export default class OfficeSimulation {
  private readonly movementSystem: MovementSystem
  private readonly agentConfigs = new Map<string, AgentConfig>()
  private isPaused = false
  private activeHuddle: HuddleSession | null = null

  constructor(
    characters: Character[],
    movementSystem: MovementSystem,
  ) {
    this.movementSystem = movementSystem

    const configs: Array<{
      id: string
      workstation: GridCoord
      workFacing: CharacterDirection
      breakSpot: GridCoord
      breakFacing: CharacterDirection
      initialWait: number
      workDuration: number
      restDuration: number
    }> = [
      {
        id: 'manager',
        workstation: { column: 9, row: 5 },
        workFacing: 'up',
        breakSpot: { column: 13, row: 2 },
        breakFacing: 'up',
        initialWait: 1.0,
        workDuration: 6.0,
        restDuration: 4.0,
      },
      {
        id: 'developer',
        workstation: { column: 7, row: 12 },
        workFacing: 'up',
        breakSpot: { column: 4, row: 12 },
        breakFacing: 'left',
        initialWait: 2.0,
        workDuration: 5.5,
        restDuration: 3.5,
      },
      {
        id: 'researcher',
        workstation: { column: 21, row: 12 },
        workFacing: 'up',
        breakSpot: { column: 3, row: 4 },
        breakFacing: 'left',
        initialWait: 3.0,
        workDuration: 7.0,
        restDuration: 4.5,
      },
    ]

    for (const character of characters) {
      const cfg = configs.find((c) => c.id === character.definition.id)
      if (!cfg) continue

      this.agentConfigs.set(cfg.id, {
        characterId: cfg.id,
        character,
        workstation: cfg.workstation,
        workFacing: cfg.workFacing,
        breakSpot: cfg.breakSpot,
        breakFacing: cfg.breakFacing,
        initialWaitSeconds: cfg.initialWait,
        workDurationSeconds: cfg.workDuration,
        restDurationSeconds: cfg.restDuration,
        currentState: 'SPAWN_WAIT',
        timer: cfg.initialWait,
        remoteStatus: null,
        remoteTaskTitle: null,
      })
    }

    this.movementSystem.onDestinationReached(this.handleDestinationReached)
  }

  pause() {
    this.isPaused = true
  }

  resume() {
    this.isPaused = false
  }

  isSimulationPaused(): boolean {
    return this.isPaused
  }

  updateLayout(layout: readonly OfficeFurnitureItem[]) {
    const ws2 = layout.find((i) => i.id === 'workstation-2')
    const ws3 = layout.find((i) => i.id === 'workstation-3')
    const ws6 = layout.find((i) => i.id === 'workstation-6')

    const mgr = this.agentConfigs.get('manager')
    if (mgr && ws2) {
      mgr.workstation = { column: ws2.column, row: ws2.row + 1 }
    }
    const dev = this.agentConfigs.get('developer')
    if (dev && ws3) {
      dev.workstation = { column: ws3.column, row: ws3.row + 1 }
    }
    const res = this.agentConfigs.get('researcher')
    if (res && ws6) {
      res.workstation = { column: ws6.column, row: ws6.row + 1 }
    }
  }

  reassignAgentWorkstation(agentId: string, seatCoord: GridCoord): boolean {
    const config = this.agentConfigs.get(agentId)
    if (!config) return false

    config.workstation = { column: seatCoord.column, row: seatCoord.row }
    config.currentState = config.remoteStatus === 'working' ? 'REMOTE_WALKING_TO_WORK' : 'WALKING_TO_WORK'
    const success = this.movementSystem.moveTo(agentId, config.workstation, config.workFacing)
    config.character.showSpeech(`Moving to desk (${seatCoord.column}, ${seatCoord.row})`, 3000)
    retroSFX.playRelocateSound()
    return success
  }

  getAgentWorkstation(agentId: string): GridCoord | null {
    const config = this.agentConfigs.get(agentId)
    return config ? { ...config.workstation } : null
  }

  isHuddleActive(): boolean {
    return this.activeHuddle !== null
  }

  getActiveHuddle(): HuddleSession | null {
    return this.activeHuddle ? { ...this.activeHuddle } : null
  }

  startHuddle(
    initiatorId = 'manager',
    receiverId = 'developer',
    options?: { topic?: string; response?: string },
  ): boolean {
    if (this.isPaused) return false
    if (this.activeHuddle) return false

    const initiatorConfig = this.agentConfigs.get(initiatorId)
    const receiverConfig = this.agentConfigs.get(receiverId)
    if (!initiatorConfig || !receiverConfig) return false

    const initSpot = MEETING_SPOTS[initiatorId] ?? { column: 13, row: 5, facing: 'right' }
    const recvSpot = MEETING_SPOTS[receiverId] ?? { column: 16, row: 5, facing: 'left' }

    initiatorConfig.currentState = 'WALKING_TO_MEETING'
    receiverConfig.currentState = 'WALKING_TO_MEETING'

    this.activeHuddle = {
      initiatorId,
      receiverId,
      topic: options?.topic ?? "Here's the plan for next task. Ready to coordinate?",
      response: options?.response ?? "Understood! Starting development now.",
      stage: 'walking_to_meeting',
      timer: 0,
    }

    this.movementSystem.moveTo(initiatorId, { column: initSpot.column, row: initSpot.row }, initSpot.facing)
    this.movementSystem.moveTo(receiverId, { column: recvSpot.column, row: recvSpot.row }, recvSpot.facing)

    return true
  }

  endHuddle() {
    if (!this.activeHuddle) return
    const { initiatorId, receiverId } = this.activeHuddle
    const initiatorConfig = this.agentConfigs.get(initiatorId)
    const receiverConfig = this.agentConfigs.get(receiverId)

    this.activeHuddle = null

    if (initiatorConfig) {
      initiatorConfig.currentState = 'WALKING_FROM_MEETING'
      this.movementSystem.moveTo(initiatorId, initiatorConfig.workstation, initiatorConfig.workFacing)
    }
    if (receiverConfig) {
      receiverConfig.currentState = 'WALKING_FROM_MEETING'
      this.movementSystem.moveTo(receiverId, receiverConfig.workstation, receiverConfig.workFacing)
    }
  }

  update(delta: number) {
    if (this.isPaused) return
    const dt = Math.min(delta, 50) / 1000

    // Manage Collaborative Meeting Huddle dialogue lifecycle
    if (this.activeHuddle) {
      const huddle = this.activeHuddle
      const initConfig = this.agentConfigs.get(huddle.initiatorId)
      const recvConfig = this.agentConfigs.get(huddle.receiverId)

      if (huddle.stage === 'in_dialogue_step1') {
        huddle.timer -= dt
        if (huddle.timer <= 0) {
          huddle.stage = 'in_dialogue_step2'
          huddle.timer = 2.4
          if (recvConfig) {
            const recvSpot = MEETING_SPOTS[huddle.receiverId] ?? { column: 16, row: 5, facing: 'left' }
            recvConfig.character.setVisualState('working', recvSpot.facing)
            recvConfig.character.showSpeech(huddle.response, 2500)
          }
        }
      } else if (huddle.stage === 'in_dialogue_step2') {
        huddle.timer -= dt
        if (huddle.timer <= 0) {
          huddle.stage = 'concluding'
          huddle.timer = 1.0
          initConfig?.character.spawnHuddleEffect()
          recvConfig?.character.spawnHuddleEffect()
          retroSFX.playCompleteSound()
        }
      } else if (huddle.stage === 'concluding') {
        huddle.timer -= dt
        if (huddle.timer <= 0) {
          this.endHuddle()
        }
      }
    }

    for (const config of this.agentConfigs.values()) {
      switch (config.currentState) {
        case 'SPAWN_WAIT': {
          config.timer -= dt
          if (config.timer <= 0) {
            config.currentState = 'WALKING_TO_WORK'
            this.movementSystem.moveTo(
              config.characterId,
              config.workstation,
              config.workFacing,
            )
          }
          break
        }

        case 'WORKING': {
          config.timer -= dt
          if (config.timer <= 0) {
            config.currentState = 'WALKING_TO_BREAK'
            this.movementSystem.moveTo(
              config.characterId,
              config.breakSpot,
              config.breakFacing,
            )
          }
          break
        }

        case 'RESTING': {
          config.timer -= dt
          if (config.timer <= 0) {
            config.currentState = 'WALKING_TO_WORK'
            this.movementSystem.moveTo(
              config.characterId,
              config.workstation,
              config.workFacing,
            )
          }
          break
        }

        case 'WALKING_TO_WORK':
        case 'WALKING_TO_BREAK':
        case 'REMOTE_WALKING_TO_WORK':
        case 'REMOTE_WORKING':
        case 'REMOTE_FAILED':
          // Managed by movement system callbacks
          break
      }
    }
  }

  destroy() {
    this.agentConfigs.clear()
  }

  applyActivities(activities: AgentActivity[]) {
    const byId = new Map(activities.map((activity) => [activity.agent_id, activity]))
    for (const config of this.agentConfigs.values()) {
      const activity = byId.get(config.characterId as AgentActivity['agent_id'])
      if (!activity) continue
      const unchanged = config.remoteStatus === activity.status && config.remoteTaskTitle === activity.current_task_title
      if (unchanged) continue
      const previousStatus = config.remoteStatus
      config.remoteStatus = activity.status
      config.remoteTaskTitle = activity.current_task_title
      config.character.setActivityLabel(activity.status, activity.current_task_title)

      if (activity.status === 'working') {
        config.currentState = 'REMOTE_WALKING_TO_WORK'
        this.movementSystem.moveTo(config.characterId, config.workstation, config.workFacing)
        if (activity.current_task_title) {
          config.character.showSpeech(activity.current_task_title, 4500)
        }
      } else if (activity.status === 'failed') {
        config.currentState = 'REMOTE_FAILED'
        this.movementSystem.stop(config.characterId, 'error', config.workFacing)
        config.character.showSpeech('Execution encountered an issue', 4000)
      } else if (previousStatus !== null && previousStatus !== 'idle') {
        config.currentState = 'RESTING'
        config.timer = config.restDurationSeconds
        this.movementSystem.stop(config.characterId, 'idle', config.breakFacing)
      } else if (activity.status === 'idle' && activities.some((a) => a.status === 'working')) {
        if (!this.movementSystem.isCharacterMoving(config.characterId)) {
          config.character.setVisualState('waiting')
        }
      }
    }
  }

  private readonly handleDestinationReached = (
    characterId: string,
    destination: GridCoord,
  ) => {
    const config = this.agentConfigs.get(characterId)
    if (!config) return

    // 1. Collaborative Meeting arrival check
    if (this.activeHuddle && this.activeHuddle.stage === 'walking_to_meeting') {
      const { initiatorId, receiverId } = this.activeHuddle
      const initSpot = MEETING_SPOTS[initiatorId] ?? { column: 13, row: 5, facing: 'right' }
      const recvSpot = MEETING_SPOTS[receiverId] ?? { column: 16, row: 5, facing: 'left' }

      if (
        characterId === initiatorId &&
        destination.column === initSpot.column &&
        destination.row === initSpot.row
      ) {
        config.currentState = 'IN_MEETING'
        config.character.setVisualState('working', initSpot.facing)
      } else if (
        characterId === receiverId &&
        destination.column === recvSpot.column &&
        destination.row === recvSpot.row
      ) {
        config.currentState = 'IN_MEETING'
        config.character.setVisualState('waiting', recvSpot.facing)
      }

      const initConfig = this.agentConfigs.get(initiatorId)
      const recvConfig = this.agentConfigs.get(receiverId)
      if (initConfig?.currentState === 'IN_MEETING' && recvConfig?.currentState === 'IN_MEETING') {
        this.activeHuddle.stage = 'in_dialogue_step1'
        this.activeHuddle.timer = 2.2
        initConfig.character.showSpeech(this.activeHuddle.topic, 2500)
      }
      return
    }

    // 2. Workstation or break arrival
    if (
      (config.currentState === 'REMOTE_WALKING_TO_WORK' ||
        config.currentState === 'WALKING_FROM_MEETING' ||
        config.currentState === 'WALKING_TO_WORK') &&
      destination.column === config.workstation.column &&
      destination.row === config.workstation.row
    ) {
      if (config.remoteStatus === 'working') {
        config.currentState = 'REMOTE_WORKING'
        config.character.setVisualState('working', config.workFacing)
      } else {
        config.currentState = 'WORKING'
        config.timer = config.workDurationSeconds
        config.character.setVisualState('working', config.workFacing)
      }
    } else if (
      config.currentState === 'WALKING_TO_BREAK' &&
      destination.column === config.breakSpot.column &&
      destination.row === config.breakSpot.row
    ) {
      config.currentState = 'RESTING'
      config.timer = config.restDurationSeconds
      config.character.setVisualState('idle', config.breakFacing)
    }
  }
}


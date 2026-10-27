import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import Phaser from 'phaser'

import { createGameConfig } from './config/gameConfig'
import type { OfficeFurnitureItem } from './maps/officeLayout'
import type OfficeScene from './scenes/OfficeScene'
import type { AgentActivity, AgentId } from '../features/agents/types'
import type { GridCoord } from './systems/PathfindingSystem'

export type PhaserGameHandle = {
  resetView: () => void
  syncSize: () => void
  startLayoutEdit: () => void
  cancelLayoutEdit: () => OfficeFurnitureItem[]
  saveLayoutEdit: () => { success: boolean; layout?: OfficeFurnitureItem[]; error?: string }
  resetLayoutToDefault: () => OfficeFurnitureItem[]
  isEditingLayout: () => boolean
  selectAgent: (agentId: AgentId | null) => void
  showAgentSpeech: (agentId: string, text: string, durationMs?: number) => void
  reassignSeat: (agentId: string, seatCoord: GridCoord) => boolean
  startHuddle: (initiatorId?: string, receiverId?: string, options?: { topic?: string; response?: string }) => boolean
  endHuddle: () => void
  isHuddleActive: () => boolean
}

type PhaserGameProps = {
  activities?: AgentActivity[]
  onAgentSelect?: (agentId: AgentId | null) => void
  onAgentRelocate?: (agentId: string, coord: GridCoord) => void
}

const PhaserGame = forwardRef<PhaserGameHandle, PhaserGameProps>(function PhaserGame(
  { activities = [], onAgentSelect, onAgentRelocate },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const gameRef = useRef<Phaser.Game | null>(null)
  const onAgentSelectRef = useRef(onAgentSelect)
  onAgentSelectRef.current = onAgentSelect
  const onAgentRelocateRef = useRef(onAgentRelocate)
  onAgentRelocateRef.current = onAgentRelocate

  useImperativeHandle(ref, () => ({
    resetView() {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as
        | { resetView?: () => void }
        | undefined
      scene?.resetView?.()
    },
    syncSize() {
      const game = gameRef.current
      const container = containerRef.current
      if (!game || !container) return

      const width = Math.round(container.clientWidth)
      const height = Math.round(container.clientHeight)
      if (width <= 0 || height <= 0) return
      if (game.scale.gameSize.width !== width || game.scale.gameSize.height !== height) {
        game.scale.resize(width, height)
      }
    },
    startLayoutEdit() {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      scene?.startLayoutEdit?.()
    },
    cancelLayoutEdit() {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      return scene?.cancelLayoutEdit?.() ?? []
    },
    saveLayoutEdit() {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      return scene?.saveLayoutEdit?.() ?? { success: false, error: 'Scene unavailable' }
    },
    resetLayoutToDefault() {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      return scene?.resetLayoutToDefault?.() ?? []
    },
    isEditingLayout() {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      return scene?.isEditingLayout?.() ?? false
    },
    selectAgent(agentId: AgentId | null) {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      scene?.selectAgent(agentId)
    },
    showAgentSpeech(agentId: string, text: string, durationMs?: number) {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      scene?.showAgentSpeech(agentId, text, durationMs)
    },
    reassignSeat(agentId: string, seatCoord: GridCoord) {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      return scene?.reassignSeat(agentId, seatCoord) ?? false
    },
    startHuddle(initiatorId?: string, receiverId?: string, options?: { topic?: string; response?: string }) {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      return scene?.startHuddle(initiatorId, receiverId, options) ?? false
    },
    endHuddle() {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      scene?.endHuddle()
    },
    isHuddleActive() {
      const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
      return scene?.isHuddleActive() ?? false
    },
  }), [])

  useEffect(() => {
    const container = containerRef.current
    if (!container || gameRef.current) return

    let observedWidth = 0
    let observedHeight = 0

    const applySize = (width: number, height: number) => {
      const nextWidth = Math.round(width)
      const nextHeight = Math.round(height)
      if (nextWidth <= 0 || nextHeight <= 0) return
      if (nextWidth === observedWidth && nextHeight === observedHeight) return

      observedWidth = nextWidth
      observedHeight = nextHeight

      const game = gameRef.current
      if (!game) {
        const newGame = new Phaser.Game(
          createGameConfig(container, nextWidth, nextHeight),
        )
        gameRef.current = newGame

        // Attach callbacks once scene is boot-ready
        newGame.events.once(Phaser.Core.Events.READY, () => {
          const scene = newGame.scene.getScene('OfficeScene') as OfficeScene | undefined
          if (scene) {
            scene.setOnAgentSelect((agentId) => {
              onAgentSelectRef.current?.(agentId as AgentId | null)
            })
            scene.setOnAgentRelocate((agentId, coord) => {
              onAgentRelocateRef.current?.(agentId, coord)
            })
          }
        })
        return
      }

      const currentSize = game.scale.gameSize
      if (currentSize.width !== nextWidth || currentSize.height !== nextHeight) {
        game.scale.resize(nextWidth, nextHeight)
      }
    }

    const resizeObserver = new ResizeObserver(([entry]) => {
      if (!entry) return
      applySize(entry.contentRect.width, entry.contentRect.height)
    })
    resizeObserver.observe(container)

    const initialBounds = container.getBoundingClientRect()
    applySize(initialBounds.width, initialBounds.height)

    return () => {
      resizeObserver.disconnect()
      gameRef.current?.destroy(true)
      gameRef.current = null
      container.replaceChildren()
    }
  }, [])

  useEffect(() => {
    const game = gameRef.current
    game?.registry.set('agentActivities', activities)
    const scene = game?.scene.getScene('OfficeScene') as OfficeScene | undefined
    scene?.updateAgentActivities?.(activities)
  }, [activities])

  return (
    <div
      ref={containerRef}
      className="phaser-game"
      aria-label="Pixel AI Office game viewport"
      role="application"
      tabIndex={0}
    />
  )
})

export default PhaserGame

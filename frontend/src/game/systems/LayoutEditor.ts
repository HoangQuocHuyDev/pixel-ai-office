import Phaser from 'phaser'

import {
  DEFAULT_FURNITURE_LAYOUT,
  saveLayoutToStorage,
  validateItemPlacement,
  validateOfficeLayout,
  type OfficeFurnitureItem,
} from '../maps/officeLayout'
import { MAP_COLUMNS, MAP_ROWS, TILE_SIZE } from '../maps/officeMap'

export type LayoutEditorCallbacks = {
  onLayoutUpdated: (layout: OfficeFurnitureItem[]) => void
  onEditStateChanged: (isEditing: boolean) => void
  onError?: (error: string) => void
}

export default class LayoutEditor {
  private readonly scene: Phaser.Scene
  private readonly callbacks: LayoutEditorCallbacks
  private isEditing = false
  private initialLayout: OfficeFurnitureItem[] = []
  private draftLayout: OfficeFurnitureItem[] = []
  private selectedItem: OfficeFurnitureItem | null = null
  private draggedItem: OfficeFurnitureItem | null = null
  private dragOffset = { col: 0, row: 0 }
  private originalPos = { col: 0, row: 0 }
  private hoverCol = 0
  private hoverRow = 0

  private readonly graphics: Phaser.GameObjects.Graphics
  private readonly previewText: Phaser.GameObjects.Text

  constructor(scene: Phaser.Scene, callbacks: LayoutEditorCallbacks) {
    this.scene = scene
    this.callbacks = callbacks

    this.graphics = scene.add.graphics()
    this.graphics.setDepth(300)
    this.graphics.setVisible(false)

    this.previewText = scene.add.text(0, 0, '', {
      fontFamily: '"Courier New", Courier, monospace',
      fontSize: '10px',
      color: '#ffffff',
      backgroundColor: '#0f172acc',
      padding: { x: 4, y: 2 },
    }).setDepth(301).setOrigin(0.5, 1).setVisible(false)

    scene.input.on(Phaser.Input.Events.POINTER_DOWN, this.onPointerDown, this)
    scene.input.on(Phaser.Input.Events.POINTER_MOVE, this.onPointerMove, this)
    scene.input.on(Phaser.Input.Events.POINTER_UP, this.onPointerUp, this)
  }

  isEditorActive(): boolean {
    return this.isEditing
  }

  getDraftLayout(): OfficeFurnitureItem[] {
    return JSON.parse(JSON.stringify(this.draftLayout))
  }

  startEditing(currentLayout: readonly OfficeFurnitureItem[]) {
    this.isEditing = true
    this.initialLayout = JSON.parse(JSON.stringify(currentLayout))
    this.draftLayout = JSON.parse(JSON.stringify(currentLayout))
    this.selectedItem = null
    this.draggedItem = null

    this.graphics.setVisible(true)
    this.renderOverlay()
    this.callbacks.onEditStateChanged(true)
  }

  cancelEditing(): OfficeFurnitureItem[] {
    if (!this.isEditing) return this.draftLayout
    this.isEditing = false
    this.draftLayout = JSON.parse(JSON.stringify(this.initialLayout))
    this.selectedItem = null
    this.draggedItem = null

    this.graphics.clear()
    this.graphics.setVisible(false)
    this.previewText.setVisible(false)

    this.callbacks.onLayoutUpdated(this.draftLayout)
    this.callbacks.onEditStateChanged(false)
    return this.draftLayout
  }

  saveEditing(): { success: boolean; layout: OfficeFurnitureItem[]; error?: string } {
    const validation = validateOfficeLayout(this.draftLayout)
    if (!validation.isValid) {
      const errorMsg = validation.errors[0] ?? 'Invalid layout configuration'
      this.callbacks.onError?.(errorMsg)
      return { success: false, layout: this.draftLayout, error: errorMsg }
    }

    const saveResult = saveLayoutToStorage(this.draftLayout)
    if (!saveResult.success) {
      const errorMsg = saveResult.error ?? 'Failed to save layout to storage'
      this.callbacks.onError?.(errorMsg)
      return { success: false, layout: this.draftLayout, error: errorMsg }
    }

    this.isEditing = false
    this.initialLayout = JSON.parse(JSON.stringify(this.draftLayout))
    this.selectedItem = null
    this.draggedItem = null

    this.graphics.clear()
    this.graphics.setVisible(false)
    this.previewText.setVisible(false)

    this.callbacks.onLayoutUpdated(this.draftLayout)
    this.callbacks.onEditStateChanged(false)
    return { success: true, layout: this.draftLayout }
  }

  resetToDefault(): OfficeFurnitureItem[] {
    this.draftLayout = JSON.parse(JSON.stringify(DEFAULT_FURNITURE_LAYOUT))
    this.selectedItem = null
    this.draggedItem = null
    this.callbacks.onLayoutUpdated(this.draftLayout)
    this.renderOverlay()
    return this.draftLayout
  }

  destroy() {
    this.scene.input.off(Phaser.Input.Events.POINTER_DOWN, this.onPointerDown, this)
    this.scene.input.off(Phaser.Input.Events.POINTER_MOVE, this.onPointerMove, this)
    this.scene.input.off(Phaser.Input.Events.POINTER_UP, this.onPointerUp, this)
    this.graphics.destroy()
    this.previewText.destroy()
  }

  private onPointerDown(pointer: Phaser.Input.Pointer) {
    if (!this.isEditing || pointer.rightButtonDown() || pointer.middleButtonDown()) return

    const tileCol = Math.floor(pointer.worldX / TILE_SIZE)
    const tileRow = Math.floor(pointer.worldY / TILE_SIZE)

    const hit = this.findItemAt(tileCol, tileRow)
    if (hit) {
      this.selectedItem = hit
      this.draggedItem = hit
      this.originalPos = { col: hit.column, row: hit.row }
      this.dragOffset = { col: tileCol - hit.column, row: tileRow - hit.row }
      this.hoverCol = hit.column
      this.hoverRow = hit.row
      this.renderOverlay()
    } else {
      this.selectedItem = null
      this.renderOverlay()
    }
  }

  private onPointerMove(pointer: Phaser.Input.Pointer) {
    if (!this.isEditing || !this.draggedItem) return

    const tileCol = Math.floor(pointer.worldX / TILE_SIZE)
    const tileRow = Math.floor(pointer.worldY / TILE_SIZE)

    this.hoverCol = tileCol - this.dragOffset.col
    this.hoverRow = tileRow - this.dragOffset.row

    this.renderOverlay()
  }

  private onPointerUp(_pointer: Phaser.Input.Pointer) {
    if (!this.isEditing || !this.draggedItem) return

    const targetCol = this.hoverCol
    const targetRow = this.hoverRow
    const item = this.draggedItem

    const validation = validateItemPlacement(item, targetCol, targetRow, this.draftLayout)
    if (validation.isValid) {
      item.column = targetCol
      item.row = targetRow
      this.callbacks.onLayoutUpdated(this.draftLayout)
    } else {
      // Revert to original position
      item.column = this.originalPos.col
      item.row = this.originalPos.row
      if (validation.reason) {
        this.callbacks.onError?.(validation.reason)
      }
    }

    this.draggedItem = null
    this.previewText.setVisible(false)
    this.renderOverlay()
  }

  private findItemAt(col: number, row: number): OfficeFurnitureItem | null {
    for (const item of this.draftLayout) {
      if (
        col >= item.column &&
        col < item.column + item.width &&
        row >= item.row &&
        row < item.row + item.height
      ) {
        return item
      }
    }
    return null
  }

  private renderOverlay() {
    this.graphics.clear()
    if (!this.isEditing) return

    // 1. Draw subtle grid across the playable floor area
    this.graphics.lineStyle(1, 0x94a3b8, 0.25)
    for (let c = 1; c <= MAP_COLUMNS - 1; c += 1) {
      this.graphics.lineBetween(
        c * TILE_SIZE,
        2 * TILE_SIZE,
        c * TILE_SIZE,
        (MAP_ROWS - 1) * TILE_SIZE,
      )
    }
    for (let r = 2; r <= MAP_ROWS - 1; r += 1) {
      this.graphics.lineBetween(
        1 * TILE_SIZE,
        r * TILE_SIZE,
        (MAP_COLUMNS - 1) * TILE_SIZE,
        r * TILE_SIZE,
      )
    }

    // 2. Highlight existing furniture bounding boxes
    for (const item of this.draftLayout) {
      const isSelected = this.selectedItem?.id === item.id
      const isBeingDragged = this.draggedItem?.id === item.id

      if (isBeingDragged) continue // Rendered separately below

      const x = item.column * TILE_SIZE
      const y = item.row * TILE_SIZE
      const w = item.width * TILE_SIZE
      const h = item.height * TILE_SIZE

      if (isSelected) {
        this.graphics.fillStyle(0x38bdf8, 0.2)
        this.graphics.fillRect(x, y, w, h)
        this.graphics.lineStyle(2, 0x0284c7, 0.9)
        this.graphics.strokeRect(x, y, w, h)
      } else {
        this.graphics.fillStyle(0x64748b, 0.08)
        this.graphics.fillRect(x, y, w, h)
        this.graphics.lineStyle(1, 0x64748b, 0.5)
        this.graphics.strokeRect(x, y, w, h)
      }
    }

    // 3. Render dragged item candidate preview
    if (this.draggedItem) {
      const item = this.draggedItem
      const x = this.hoverCol * TILE_SIZE
      const y = this.hoverRow * TILE_SIZE
      const w = item.width * TILE_SIZE
      const h = item.height * TILE_SIZE

      const validation = validateItemPlacement(item, this.hoverCol, this.hoverRow, this.draftLayout)

      if (validation.isValid) {
        // Valid: Emerald green
        this.graphics.fillStyle(0x22c55e, 0.3)
        this.graphics.fillRect(x, y, w, h)
        this.graphics.lineStyle(2, 0x16a34a, 0.95)
        this.graphics.strokeRect(x, y, w, h)

        this.previewText
          .setText(`✓ ${item.label ?? item.id}`)
          .setColor('#4ade80')
          .setPosition(x + w / 2, y - 4)
          .setVisible(true)
      } else {
        // Invalid: Crimson red
        this.graphics.fillStyle(0xef4444, 0.4)
        this.graphics.fillRect(x, y, w, h)
        this.graphics.lineStyle(2, 0xdc2626, 0.95)
        this.graphics.strokeRect(x, y, w, h)

        this.previewText
          .setText(`✕ ${validation.reason ?? 'Invalid placement'}`)
          .setColor('#f87171')
          .setPosition(x + w / 2, y - 4)
          .setVisible(true)
      }
    }
  }
}

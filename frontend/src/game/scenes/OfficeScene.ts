import Phaser from 'phaser'

import Character from '../characters/Character'
import {
  characterDefinitions,
  createCharacterAssets,
  type CharacterDirection,
} from '../characters/characterDefinitions'
import {
  MAP_COLUMNS,
  MAP_ROWS,
  TILE,
  TILE_COUNT,
  TILE_SIZE,
  createOfficeMapData,
} from '../maps/officeMap'
import type { OfficeFurnitureItem } from '../maps/officeLayout'
import CameraController from '../systems/CameraController'
import LayoutEditor from '../systems/LayoutEditor'
import MovementSystem from '../systems/MovementSystem'
import OfficeSimulation from '../systems/OfficeSimulation'
import PathfindingSystem, { type GridCoord } from '../systems/PathfindingSystem'
import type { AgentActivity } from '../../features/agents/types'
import { retroSFX } from '../utils/sfx'

const TILESET_KEY = 'generated-office-tiles'

class OfficeScene extends Phaser.Scene {
  private characters: Character[] = []
  private pathfindingSystem?: PathfindingSystem
  private movementSystem?: MovementSystem
  private simulation?: OfficeSimulation
  private cameraController?: CameraController
  private layoutEditor?: LayoutEditor
  private furnitureLayer?: Phaser.Tilemaps.TilemapLayer
  private decorationsLayer?: Phaser.Tilemaps.TilemapLayer
  private currentLayout: OfficeFurnitureItem[] = []
  private selectedAgentId: string | null = null
  private onAgentSelectCallback?: (agentId: string | null) => void
  private onAgentRelocateCallback?: (agentId: string, coord: GridCoord) => void

  constructor() {
    super({ key: 'OfficeScene' })
  }

  create() {
    this.cameras.main.setBackgroundColor('#dfe4e8')
    this.cameras.main.roundPixels = true

    if (!this.textures.exists(TILESET_KEY)) this.createTilesetTexture()

    const mapData = createOfficeMapData()
    this.currentLayout = JSON.parse(JSON.stringify(mapData.layout))

    const map = this.make.tilemap({
      tileWidth: TILE_SIZE,
      tileHeight: TILE_SIZE,
      width: MAP_COLUMNS,
      height: MAP_ROWS,
    })
    const tileset = map.addTilesetImage(
      TILESET_KEY,
      TILESET_KEY,
      TILE_SIZE,
      TILE_SIZE,
      0,
      0,
    )
    if (!tileset) throw new Error('Unable to create the office tileset.')

    const layerDefinitions = [
      { name: 'Floor', data: mapData.floor },
      { name: 'Walls', data: mapData.walls },
      { name: 'Furniture', data: mapData.furniture },
      { name: 'Decorations', data: mapData.decorations },
    ]

    layerDefinitions.forEach(({ name, data }, depth) => {
      const layer = map.createBlankLayer(name, tileset, 0, 0)
      if (!layer) throw new Error(`Unable to create the ${name} tilemap layer.`)
      layer.putTilesAt(data, 0, 0)
      layer.setDepth(depth)

      if (name === 'Furniture') {
        this.furnitureLayer = layer
      } else if (name === 'Decorations') {
        this.decorationsLayer = layer
      }
    })

    createCharacterAssets(this)
    this.characters = characterDefinitions.map((definition) => {
      const cellKey = `${definition.spawn.column},${definition.spawn.row}`
      if (!mapData.walkableCells.has(cellKey)) {
        throw new Error(`${definition.id} must be placed on a walkable office cell.`)
      }
      return new Character(this, definition)
    })

    const focusElement = this.game.canvas.parentElement
    if (!focusElement) throw new Error('Game viewport is unavailable.')

    this.pathfindingSystem = new PathfindingSystem(mapData.walkableCells)
    this.movementSystem = new MovementSystem(
      this.characters,
      this.pathfindingSystem,
    )
    this.simulation = new OfficeSimulation(
      this.characters,
      this.movementSystem,
    )
    const initialActivities = this.registry.get('agentActivities') as AgentActivity[] | undefined
    if (initialActivities) this.simulation.applyActivities(initialActivities)

    this.cameraController = new CameraController(this, focusElement)
    this.cameraController.resize(this.scale.gameSize.width, this.scale.gameSize.height, false)
    this.scale.on(Phaser.Scale.Events.RESIZE, this.resizeCamera, this)

    // Initialize Layout Editor
    this.layoutEditor = new LayoutEditor(this, {
      onLayoutUpdated: (layout) => this.applyLayoutToMap(layout),
      onEditStateChanged: (isEditing) => {
        if (isEditing) {
          this.simulation?.pause()
        } else {
          this.simulation?.resume()
        }
      },
    })

    // Agent selection event listener
    this.events.on('character-selected', (agentId: string) => {
      if (this.layoutEditor?.isEditorActive()) return
      this.selectAgent(agentId)
    })

    // Pointer down on scene for seat reassignment or deselecting
    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer, gameObjects: Phaser.GameObjects.GameObject[]) => {
      if (this.layoutEditor?.isEditorActive()) return
      if (!pointer.leftButtonDown()) return
      if (gameObjects.length > 0) return // Handled by interactive character sprite

      const col = Math.floor(pointer.worldX / TILE_SIZE)
      const row = Math.floor(pointer.worldY / TILE_SIZE)

      if (this.selectedAgentId) {
        // Check if clicked tile corresponds to a workstation chair
        const targetWorkstation = this.currentLayout.find((item) => {
          if (item.type !== 'workstation') return false
          return (
            (col === item.column && row === item.row + 1) ||
            (col >= item.column && col < item.column + item.width && row >= item.row && row < item.row + item.height)
          )
        })

        if (targetWorkstation) {
          const seatCoord = { column: targetWorkstation.column, row: targetWorkstation.row + 1 }
          this.reassignSeat(this.selectedAgentId, seatCoord)
          return
        }

        // Clicked outside chair/workstation: deselect
        this.selectAgent(null)
      }
    })

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      this.scale.off(Phaser.Scale.Events.RESIZE, this.resizeCamera, this)
      this.events.off('character-selected')
      this.input.off('pointerdown')
      this.layoutEditor?.destroy()
      this.simulation?.destroy()
      this.movementSystem?.destroy()
      this.cameraController?.destroy()
      this.layoutEditor = undefined
      this.simulation = undefined
      this.movementSystem = undefined
      this.pathfindingSystem = undefined
      this.cameraController = undefined
      this.characters.forEach((character) => character.destroy())
      this.characters = []
    })
  }

  update(_time: number, delta: number) {
    this.movementSystem?.update(delta)
    this.simulation?.update(delta)
    this.cameraController?.update()
  }

  resetView() {
    this.cameraController?.reset()
  }

  updateAgentActivities(activities: AgentActivity[]) {
    this.simulation?.applyActivities(activities)
  }

  /**
   * Layout Editor API
   */
  startLayoutEdit() {
    this.layoutEditor?.startEditing(this.currentLayout)
  }

  cancelLayoutEdit(): OfficeFurnitureItem[] {
    const layout = this.layoutEditor?.cancelEditing() ?? this.currentLayout
    this.applyLayoutToMap(layout)
    return layout
  }

  saveLayoutEdit(): { success: boolean; layout: OfficeFurnitureItem[]; error?: string } {
    const result = this.layoutEditor?.saveEditing() ?? {
      success: false,
      layout: this.currentLayout,
      error: 'Layout editor unavailable',
    }
    if (result.success) {
      this.applyLayoutToMap(result.layout)
    }
    return result
  }

  resetLayoutToDefault(): OfficeFurnitureItem[] {
    const layout = this.layoutEditor?.resetToDefault() ?? this.currentLayout
    this.applyLayoutToMap(layout)
    return layout
  }

  isEditingLayout(): boolean {
    return this.layoutEditor?.isEditorActive() ?? false
  }

  getOfficeLayout(): OfficeFurnitureItem[] {
    return this.layoutEditor?.isEditorActive()
      ? this.layoutEditor.getDraftLayout()
      : this.currentLayout
  }

  private applyLayoutToMap(layout: readonly OfficeFurnitureItem[]) {
    this.currentLayout = JSON.parse(JSON.stringify(layout))
    const mapData = createOfficeMapData(layout)

    if (this.furnitureLayer && this.decorationsLayer) {
      for (let r = 0; r < MAP_ROWS; r += 1) {
        for (let c = 0; c < MAP_COLUMNS; c += 1) {
          this.furnitureLayer.putTileAt(-1, c, r)
          this.decorationsLayer.putTileAt(-1, c, r)
        }
      }
      this.furnitureLayer.putTilesAt(mapData.furniture, 0, 0)
      this.decorationsLayer.putTilesAt(mapData.decorations, 0, 0)
    }

    this.pathfindingSystem?.setWalkableCells(mapData.walkableCells)
    this.simulation?.updateLayout(layout)
  }

  /**
   * Internal Movement API for future AI backend event integration:
   * moveTo(agentId, destination, facing)
   */
  moveTo(agentId: string, destination: GridCoord, facing?: CharacterDirection): boolean {
    return this.movementSystem?.moveTo(agentId, destination, facing) ?? false
  }

  /**
   * Interactive Agent Selection & Inspection API
   */
  selectAgent(agentId: string | null) {
    if (this.selectedAgentId === agentId && agentId !== null) return

    this.selectedAgentId = agentId
    this.characters.forEach((char) => {
      char.setSelected(char.definition.id === agentId)
    })

    if (agentId) {
      const selectedChar = this.characters.find((c) => c.definition.id === agentId)
      if (selectedChar) {
        this.cameras.main.pan(selectedChar.x, selectedChar.y - 16, 400, 'Cubic.easeOut')
        retroSFX.playSelectSound()
      }
    }

    this.onAgentSelectCallback?.(agentId)
  }

  getSelectedAgentId(): string | null {
    return this.selectedAgentId
  }

  reassignSeat(agentId: string, seatCoord: GridCoord): boolean {
    if (!this.simulation) return false
    const success = this.simulation.reassignAgentWorkstation(agentId, seatCoord)
    if (success) {
      this.onAgentRelocateCallback?.(agentId, seatCoord)
    }
    return success
  }

  showAgentSpeech(agentId: string, text: string, durationMs = 4000) {
    const character = this.characters.find((c) => c.definition.id === agentId)
    character?.showSpeech(text, durationMs)
  }

  setOnAgentSelect(callback: (agentId: string | null) => void) {
    this.onAgentSelectCallback = callback
  }

  setOnAgentRelocate(callback: (agentId: string, coord: GridCoord) => void) {
    this.onAgentRelocateCallback = callback
  }

  /**
   * Collaborative Meeting Huddle API
   */
  startHuddle(
    initiatorId = 'manager',
    receiverId = 'developer',
    options?: { topic?: string; response?: string },
  ): boolean {
    if (!this.simulation) return false
    const success = this.simulation.startHuddle(initiatorId, receiverId, options)
    if (success) {
      // Gently pan camera toward central conference / meeting area
      this.cameras.main.pan(15 * TILE_SIZE, 5 * TILE_SIZE, 450, 'Cubic.easeOut')
    }
    return success
  }

  endHuddle() {
    this.simulation?.endHuddle()
  }

  isHuddleActive(): boolean {
    return this.simulation?.isHuddleActive() ?? false
  }

  private resizeCamera(gameSize: Phaser.Structs.Size) {
    this.cameraController?.resize(gameSize.width, gameSize.height)
  }

  private createTilesetTexture() {
    const graphics = this.make.graphics({ x: 0, y: 0 })
    const tileX = (index: number) => index * TILE_SIZE

    const fillTile = (index: number, color: number) => {
      graphics.fillStyle(color)
      graphics.fillRect(tileX(index), 0, TILE_SIZE, TILE_SIZE)
    }

    fillTile(TILE.floor, 0xead8b7)
    graphics.fillStyle(0xd9c39f)
    graphics.fillRect(tileX(TILE.floor), 15, TILE_SIZE, 2)
    graphics.fillRect(tileX(TILE.floor) + 7, 0, 2, 15)
    graphics.fillRect(tileX(TILE.floor) + 23, 17, 2, 15)

    fillTile(TILE.floorAlternate, 0xe7d3af)
    graphics.fillStyle(0xd4bc96)
    graphics.fillRect(tileX(TILE.floorAlternate), 15, TILE_SIZE, 2)
    graphics.fillRect(tileX(TILE.floorAlternate) + 15, 0, 2, 15)
    graphics.fillRect(tileX(TILE.floorAlternate) + 5, 17, 2, 15)

    fillTile(TILE.walkway, 0xdedbd1)
    graphics.fillStyle(0xcac6ba)
    graphics.fillRect(tileX(TILE.walkway) + 3, 3, 2, 2)
    graphics.fillRect(tileX(TILE.walkway) + 25, 20, 2, 2)

    fillTile(TILE.wallTop, 0xf7f1e5)
    graphics.fillStyle(0xd4cbb9)
    graphics.fillRect(tileX(TILE.wallTop), 0, TILE_SIZE, 4)
    graphics.fillStyle(0xe4dac8)
    graphics.fillRect(tileX(TILE.wallTop), 27, TILE_SIZE, 5)

    fillTile(TILE.wallFace, 0xeee5d7)
    graphics.fillStyle(0xd4c8b7)
    graphics.fillRect(tileX(TILE.wallFace), 25, TILE_SIZE, 7)
    graphics.fillStyle(0xfaf6ef)
    graphics.fillRect(tileX(TILE.wallFace) + 2, 3, TILE_SIZE - 4, 3)

    fillTile(TILE.door, 0xb78355)
    graphics.fillStyle(0x895d3c)
    graphics.fillRect(tileX(TILE.door), 0, 3, TILE_SIZE)
    graphics.fillRect(tileX(TILE.door) + 29, 0, 3, TILE_SIZE)
    graphics.fillRect(tileX(TILE.door), 0, TILE_SIZE, 3)
    graphics.fillStyle(0xf3c96b)
    graphics.fillRect(tileX(TILE.door) + 6, 16, 3, 3)

    for (const index of [TILE.deskLeft, TILE.deskRight]) {
      graphics.fillStyle(0x8f5e3f)
      graphics.fillRect(tileX(index) + 2, 7, 30, 21)
      graphics.fillStyle(0xc88f5f)
      graphics.fillRect(tileX(index) + 2, 4, 30, 20)
      graphics.fillStyle(0xe0ac78)
      graphics.fillRect(tileX(index) + 4, 28, 3, 3)
      graphics.fillStyle(0x664630)
      graphics.fillRect(tileX(index) + 5, 24, 4, 7)
      graphics.fillRect(tileX(index) + 25, 24, 4, 7)
    }

    graphics.fillStyle(0x27364d)
    graphics.fillRect(tileX(TILE.monitor) + 7, 3, 19, 13)
    graphics.fillStyle(0x8fd3e8)
    graphics.fillRect(tileX(TILE.monitor) + 9, 5, 15, 9)
    graphics.fillStyle(0x475569)
    graphics.fillRect(tileX(TILE.monitor) + 15, 16, 3, 5)
    graphics.fillRect(tileX(TILE.monitor) + 11, 20, 11, 2)

    graphics.fillStyle(0x596b8a)
    graphics.fillRect(tileX(TILE.chair) + 8, 5, 16, 17)
    graphics.fillStyle(0x7890b5)
    graphics.fillRect(tileX(TILE.chair) + 10, 7, 12, 11)
    graphics.fillStyle(0x3d4c66)
    graphics.fillRect(tileX(TILE.chair) + 14, 22, 4, 7)
    graphics.fillRect(tileX(TILE.chair) + 8, 27, 16, 3)

    graphics.fillStyle(0x9a643f)
    graphics.fillRect(tileX(TILE.plant) + 9, 20, 14, 10)
    graphics.fillStyle(0x2f855a)
    graphics.fillRect(tileX(TILE.plant) + 7, 8, 8, 14)
    graphics.fillRect(tileX(TILE.plant) + 17, 4, 8, 18)
    graphics.fillStyle(0x65a765)
    graphics.fillRect(tileX(TILE.plant) + 12, 2, 7, 17)

    graphics.fillStyle(0x805738)
    graphics.fillRect(tileX(TILE.bookshelf) + 3, 2, 26, 29)
    graphics.fillStyle(0xe4c07a)
    graphics.fillRect(tileX(TILE.bookshelf) + 6, 6, 4, 9)
    graphics.fillStyle(0x6681b5)
    graphics.fillRect(tileX(TILE.bookshelf) + 11, 5, 5, 10)
    graphics.fillStyle(0xb95f5f)
    graphics.fillRect(tileX(TILE.bookshelf) + 17, 7, 4, 8)
    graphics.fillStyle(0x5d9b75)
    graphics.fillRect(tileX(TILE.bookshelf) + 22, 4, 4, 11)
    graphics.fillStyle(0x5f3f2a)
    graphics.fillRect(tileX(TILE.bookshelf) + 4, 16, 24, 3)

    graphics.fillStyle(0xb8864f)
    graphics.fillRect(tileX(TILE.noticeboard) + 2, 5, 28, 22)
    graphics.fillStyle(0xf1dfb4)
    graphics.fillRect(tileX(TILE.noticeboard) + 5, 8, 22, 16)
    graphics.fillStyle(0x6f86bd)
    graphics.fillRect(tileX(TILE.noticeboard) + 8, 11, 7, 5)
    graphics.fillStyle(0xd87863)
    graphics.fillRect(tileX(TILE.noticeboard) + 18, 14, 6, 7)

    graphics.fillStyle(0x8fa0ae)
    graphics.fillRect(tileX(TILE.cabinet) + 5, 3, 22, 28)
    graphics.fillStyle(0xc5d0d8)
    graphics.fillRect(tileX(TILE.cabinet) + 7, 5, 18, 11)
    graphics.fillRect(tileX(TILE.cabinet) + 7, 18, 18, 10)
    graphics.fillStyle(0x647584)
    graphics.fillRect(tileX(TILE.cabinet) + 21, 10, 2, 2)
    graphics.fillRect(tileX(TILE.cabinet) + 21, 22, 2, 2)

    graphics.fillStyle(0xf8fafc)
    graphics.fillRect(tileX(TILE.cup) + 11, 8, 10, 10)
    graphics.fillStyle(0x596b8a)
    graphics.fillRect(tileX(TILE.cup) + 13, 10, 6, 6)
    graphics.fillRect(tileX(TILE.cup) + 20, 11, 3, 5)

    graphics.fillStyle(0xe7eef2)
    graphics.fillRect(tileX(TILE.waterCooler) + 8, 3, 16, 27)
    graphics.fillStyle(0x8fd3e8)
    graphics.fillRect(tileX(TILE.waterCooler) + 10, 5, 12, 11)
    graphics.fillStyle(0x526777)
    graphics.fillRect(tileX(TILE.waterCooler) + 10, 20, 12, 8)
    graphics.fillStyle(0x4f46e5)
    graphics.fillRect(tileX(TILE.waterCooler) + 12, 18, 3, 3)

    graphics.generateTexture(TILESET_KEY, TILE_SIZE * TILE_COUNT, TILE_SIZE)
    graphics.destroy()
  }
}

export default OfficeScene

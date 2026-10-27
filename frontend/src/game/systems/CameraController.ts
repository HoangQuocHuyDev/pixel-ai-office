import Phaser from 'phaser'

import { MAP_HEIGHT, MAP_WIDTH } from '../maps/officeMap'
import { setupKeyboardScope } from './keyboardScope'

const MAX_ZOOM_MULTIPLIER = 3

export default class CameraController {
  private readonly scene: Phaser.Scene
  private readonly focusElement: HTMLElement
  private fitZoom = 1
  private targetZoom = 1
  private anchorX = 0
  private anchorY = 0
  private anchorWorldX = MAP_WIDTH / 2
  private anchorWorldY = MAP_HEIGHT / 2
  private dragging = false
  private dragX = 0
  private dragY = 0
  private readonly spaceKey: Phaser.Input.Keyboard.Key | null
  private readonly canvas: HTMLCanvasElement
  private readonly cleanupKeyboardScope?: () => void

  constructor(
    scene: Phaser.Scene,
    focusElement: HTMLElement,
  ) {
    this.scene = scene
    this.focusElement = focusElement
    this.canvas = scene.game.canvas
    this.cleanupKeyboardScope = setupKeyboardScope(scene)
    this.spaceKey = scene.input.keyboard?.addKey('SPACE') ?? null
    this.canvas.addEventListener('wheel', this.onWheel, { passive: false })
    scene.input.on(Phaser.Input.Events.POINTER_DOWN, this.onPointerDown, this)
    scene.input.on(Phaser.Input.Events.POINTER_MOVE, this.onPointerMove, this)
    scene.input.on(Phaser.Input.Events.POINTER_UP, this.onPointerUp, this)
  }

  resize(width: number, height: number, preserveView = true) {
    const camera = this.scene.cameras.main
    const oldFit = this.fitZoom
    this.fitZoom = Math.min(width / MAP_WIDTH, height / MAP_HEIGHT)
    camera.setBounds(0, 0, MAP_WIDTH, MAP_HEIGHT)
    if (!preserveView || Math.abs(camera.zoom - oldFit) < 0.001) {
      this.reset()
      return
    }
    const center = camera.midPoint.clone()
    const zoom = Phaser.Math.Clamp(camera.zoom, this.fitZoom, this.fitZoom * MAX_ZOOM_MULTIPLIER)
    camera.setZoom(zoom).centerOn(center.x, center.y)
    this.targetZoom = zoom
  }

  update() {
    const camera = this.scene.cameras.main
    if (Math.abs(camera.zoom - this.targetZoom) < 0.001) return
    const zoom = Phaser.Math.Linear(camera.zoom, this.targetZoom, 0.18)
    camera.setZoom(zoom)
    camera.scrollX = this.anchorWorldX - this.anchorX / zoom
    camera.scrollY = this.anchorWorldY - this.anchorY / zoom
    this.clampScroll()
  }

  reset() {
    const camera = this.scene.cameras.main
    this.targetZoom = this.fitZoom
    camera.setZoom(this.fitZoom).centerOn(MAP_WIDTH / 2, MAP_HEIGHT / 2)
    this.setAnchor(camera.width / 2, camera.height / 2)
  }

  destroy() {
    this.canvas.removeEventListener('wheel', this.onWheel)
    this.scene.input.off(Phaser.Input.Events.POINTER_DOWN, this.onPointerDown, this)
    this.scene.input.off(Phaser.Input.Events.POINTER_MOVE, this.onPointerMove, this)
    this.scene.input.off(Phaser.Input.Events.POINTER_UP, this.onPointerUp, this)
    if (this.spaceKey && this.scene.input.keyboard) {
      this.scene.input.keyboard.removeKey(this.spaceKey, true, true)
    }
    this.cleanupKeyboardScope?.()
  }

  private readonly onWheel = (event: WheelEvent) => {
    event.preventDefault()
    this.focusElement.focus({ preventScroll: true })
    const bounds = this.canvas.getBoundingClientRect()
    const pointerX = (event.clientX - bounds.left) * (this.canvas.width / bounds.width)
    const pointerY = (event.clientY - bounds.top) * (this.canvas.height / bounds.height)
    this.setAnchor(pointerX, pointerY)
    const factor = event.deltaY < 0 ? 1.14 : 1 / 1.14
    this.targetZoom = Phaser.Math.Clamp(this.targetZoom * factor, this.fitZoom, this.fitZoom * MAX_ZOOM_MULTIPLIER)
  }

  private onPointerDown(pointer: Phaser.Input.Pointer) {
    const spaceDown = this.spaceKey?.isDown ?? false
    if (!pointer.middleButtonDown() && !(spaceDown && pointer.leftButtonDown())) return
    this.dragging = true
    this.dragX = pointer.x
    this.dragY = pointer.y
    this.focusElement.focus({ preventScroll: true })
  }

  private onPointerMove(pointer: Phaser.Input.Pointer) {
    if (!this.dragging) return
    const camera = this.scene.cameras.main
    camera.scrollX -= (pointer.x - this.dragX) / camera.zoom
    camera.scrollY -= (pointer.y - this.dragY) / camera.zoom
    this.clampScroll()
    this.dragX = pointer.x
    this.dragY = pointer.y
  }

  private onPointerUp() {
    this.dragging = false
  }

  private setAnchor(screenX: number, screenY: number) {
    const camera = this.scene.cameras.main
    this.anchorX = screenX
    this.anchorY = screenY
    this.anchorWorldX = camera.scrollX + screenX / camera.zoom
    this.anchorWorldY = camera.scrollY + screenY / camera.zoom
  }

  private clampScroll() {
    const camera = this.scene.cameras.main
    const visibleWidth = camera.width / camera.zoom
    const visibleHeight = camera.height / camera.zoom
    if (visibleWidth <= MAP_WIDTH) {
      camera.scrollX = Phaser.Math.Clamp(camera.scrollX, 0, MAP_WIDTH - visibleWidth)
    }
    if (visibleHeight <= MAP_HEIGHT) {
      camera.scrollY = Phaser.Math.Clamp(camera.scrollY, 0, MAP_HEIGHT - visibleHeight)
    }
  }
}

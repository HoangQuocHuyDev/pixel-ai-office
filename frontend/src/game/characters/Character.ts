import Phaser from 'phaser'

import { TILE_SIZE } from '../maps/officeMap'
import {
  getCharacterAnimationKey,
  type CharacterAnimation,
  type CharacterDefinition,
  type CharacterDirection,
} from './characterDefinitions'
import type { AgentActivityStatus } from '../../features/agents/types'
import { retroSFX } from '../utils/sfx'

export type VisualState = 'idle' | 'walking' | 'working' | 'waiting' | 'error'

class Character extends Phaser.GameObjects.Sprite {
  readonly definition: CharacterDefinition
  private direction: CharacterDirection
  private visualState: VisualState = 'idle'
  private readonly activityLabel: Phaser.GameObjects.Text
  private readonly statusBubble: Phaser.GameObjects.Text
  private readonly speechBubble: Phaser.GameObjects.Text
  private speechFadeTween?: Phaser.Tweens.Tween
  private speechTimeout?: ReturnType<typeof setTimeout>
  private readonly selectionAura: Phaser.GameObjects.Graphics
  private isSelected = false
  private currentActivityStatus: AgentActivityStatus = 'idle'

  constructor(scene: Phaser.Scene, definition: CharacterDefinition) {
    super(scene, 0, 0, definition.textureKey, 0)
    this.definition = definition

    scene.add.existing(this)
    this.setName(definition.id)
    this.setOrigin(0.5, 1)
    this.setPosition(
      (definition.spawn.column + 0.5) * TILE_SIZE,
      (definition.spawn.row + 1) * TILE_SIZE,
    )

    this.direction = definition.facing
    this.updateDepth()
    this.playAnimation(`idle_${definition.facing}`)

    // Interactive pointer setup for left-click selection
    this.setInteractive({ useHandCursor: true })
    this.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      if (pointer.leftButtonDown()) {
        this.scene.events.emit('character-selected', this.definition.id)
      }
    })

    // Selection aura/ring graphic under agent feet
    this.selectionAura = scene.add.graphics()
    this.selectionAura.setVisible(false)

    // Crisp pixel-art overhead status badge with monospace typography
    this.activityLabel = scene.add.text(this.x, this.y - 38, '', {
      fontFamily: '"Courier New", Courier, monospace',
      fontSize: '9px',
      color: '#334155',
      backgroundColor: '#fffffffa',
      padding: { x: 4, y: 2 },
      align: 'center',
    }).setOrigin(0.5, 1).setDepth(200)

    // Floating emotion / status bubble (···, !, ⚡)
    this.statusBubble = scene.add.text(this.x, this.y - 52, '', {
      fontFamily: '"Courier New", Courier, monospace',
      fontSize: '8px',
      color: '#0f172a',
      backgroundColor: '#f8fafcee',
      padding: { x: 3, y: 1 },
      align: 'center',
    }).setOrigin(0.5, 1).setDepth(201).setVisible(false)

    // Live speech bubble for agent dialogue / status quotes
    this.speechBubble = scene.add.text(this.x, this.y - 66, '', {
      fontFamily: '"Courier New", Courier, monospace',
      fontSize: '8px',
      color: '#090d16',
      backgroundColor: '#ffffffee',
      padding: { x: 5, y: 3 },
      align: 'center',
      wordWrap: { width: 140, useAdvancedWrap: true },
    }).setOrigin(0.5, 1).setDepth(202).setVisible(false)

    this.setActivityLabel('idle')
  }

  playAnimation(animation: CharacterAnimation) {
    const key = getCharacterAnimationKey(this.definition.id, animation)
    if (this.anims.currentAnim?.key === key && this.anims.isPlaying) {
      return
    }
    this.play(key, true)
  }

  setVisualState(state: VisualState, direction?: CharacterDirection) {
    const previousState = this.visualState
    const directionChanged = direction !== undefined && direction !== this.direction
    if (direction !== undefined) {
      this.direction = direction
    }

    if (this.visualState === state && !directionChanged) {
      return
    }

    this.visualState = state

    // 1. Play motion animation corresponding to state and current direction
    switch (state) {
      case 'walking':
        this.playAnimation(`walk_${this.direction}`)
        break
      case 'working':
        this.playAnimation(`work_${this.direction}`)
        break
      case 'waiting':
        this.playAnimation(`wait_${this.direction}`)
        break
      case 'error':
      case 'idle':
      default:
        this.playAnimation(`idle_${this.direction}`)
        break
    }

    // 2. Trigger work start / complete micro-effects
    if (previousState !== 'working' && state === 'working') {
      this.spawnWorkStartEffect()
    } else if (previousState === 'working' && state === 'idle') {
      this.spawnWorkCompleteEffect()
    }

    // 3. Update status bubble
    this.updateStatusBubble()
    this.syncVisuals()
  }

  getVisualState(): VisualState {
    return this.visualState
  }

  getDirection(): CharacterDirection {
    return this.direction
  }

  syncVisuals() {
    this.updateDepth()
    this.activityLabel.setPosition(this.x, this.y - 35)
    this.statusBubble.setPosition(this.x, this.y - 48)
    this.speechBubble.setPosition(this.x, this.y - 66)
    this.renderSelectionAura()
  }

  setSelected(selected: boolean) {
    if (this.isSelected === selected) return
    this.isSelected = selected
    this.renderSelectionAura()
  }

  isSelectedAgent(): boolean {
    return this.isSelected
  }

  showSpeech(text: string, durationMs = 4000) {
    if (!text || text.trim().length === 0) return
    const truncated = text.length > 70 ? `${text.slice(0, 67)}...` : text

    if (this.speechFadeTween) {
      this.speechFadeTween.stop()
      this.speechFadeTween = undefined
    }
    if (this.speechTimeout) {
      clearTimeout(this.speechTimeout)
      this.speechTimeout = undefined
    }

    this.speechBubble.setText(`"${truncated}"`)
    this.speechBubble.setAlpha(1)
    this.speechBubble.setVisible(true)
    this.syncVisuals()

    retroSFX.playSpeechSound()

    const fadeStartMs = Math.max(durationMs - 600, 500)
    this.speechTimeout = setTimeout(() => {
      if (!this.scene) return
      this.speechFadeTween = this.scene.tweens.add({
        targets: this.speechBubble,
        alpha: 0,
        duration: 500,
        ease: 'Quad.easeOut',
        onComplete: () => {
          this.speechBubble.setVisible(false)
          this.speechFadeTween = undefined
        },
      })
    }, fadeStartMs)
  }

  private renderSelectionAura() {
    this.selectionAura.clear()
    if (!this.isSelected) {
      this.selectionAura.setVisible(false)
      return
    }
    this.selectionAura.setVisible(true)
    this.selectionAura.setDepth(this.depth - 0.1)

    this.selectionAura.lineStyle(1.5, 0x0284c7, 0.9)
    this.selectionAura.fillStyle(0x38bdf8, 0.28)
    this.selectionAura.fillEllipse(this.x, this.y - 2, 22, 10)
    this.selectionAura.strokeEllipse(this.x, this.y - 2, 22, 10)
  }

  setActivityLabel(status: AgentActivityStatus, taskTitle?: string | null) {
    this.currentActivityStatus = status

    const names: Record<CharacterDefinition['id'], string> = {
      manager: 'Manager',
      developer: 'Developer',
      researcher: 'Researcher',
    }

    const agentName = names[this.definition.id]
    let statusText: string
    let dotColor: string

    if (status === 'failed') {
      statusText = 'Failed'
      dotColor = '● '
      this.activityLabel.setColor('#991b1b')
      this.activityLabel.setBackgroundColor('#fef2f2fa')
      this.setTint(0xfca5a5)
      this.setVisualState('error')
    } else if (status === 'working') {
      statusText = taskTitle ? `Working: ${taskTitle.slice(0, 22)}` : 'Working'
      dotColor = '● '
      this.activityLabel.setColor('#1e3a8a')
      this.activityLabel.setBackgroundColor('#eff6fffa')
      this.clearTint()
    } else {
      statusText = this.visualState === 'waiting' ? 'Waiting' : 'Idle'
      dotColor = this.visualState === 'waiting' ? '◐ ' : '○ '
      this.activityLabel.setColor('#334155')
      this.activityLabel.setBackgroundColor('#fffffffa')
      this.clearTint()
    }

    this.activityLabel.setText(`${dotColor}${agentName} · ${statusText}`)
    this.updateStatusBubble()
    this.syncVisuals()
  }

  private updateStatusBubble() {
    if (this.visualState === 'error' || this.currentActivityStatus === 'failed') {
      this.statusBubble.setText(' ! ')
      this.statusBubble.setColor('#ef4444')
      this.statusBubble.setBackgroundColor('#fee2e2')
      this.statusBubble.setVisible(true)
    } else if (this.visualState === 'waiting') {
      this.statusBubble.setText(' ··· ')
      this.statusBubble.setColor('#b45309')
      this.statusBubble.setBackgroundColor('#fef3c7')
      this.statusBubble.setVisible(true)
    } else if (this.visualState === 'working') {
      const toolIcons: Record<CharacterDefinition['id'], string> = {
        developer: '⚡ DEV',
        researcher: '🔍 RES',
        manager: '📋 MGR',
      }
      this.statusBubble.setText(` ${toolIcons[this.definition.id]} `)
      this.statusBubble.setColor('#1d4ed8')
      this.statusBubble.setBackgroundColor('#dbeafe')
      this.statusBubble.setVisible(true)
    } else {
      this.statusBubble.setVisible(false)
    }
  }

  /**
   * Subtle pixel-art work start burst: 3 colored sparkles rising & fading
   */
  spawnHuddleEffect() {
    this.spawnWorkStartEffect()
  }

  private spawnWorkStartEffect() {
    const colors = ['#38bdf8', '#fbbf24', '#34d399']
    for (let i = 0; i < 3; i += 1) {
      const offsetX = (i - 1) * 6
      const sparkle = this.scene.add.text(this.x + offsetX, this.y - 28, '✦', {
        fontFamily: 'Courier, monospace',
        fontSize: '9px',
        color: colors[i % colors.length],
      }).setOrigin(0.5, 0.5).setDepth(205)

      this.scene.tweens.add({
        targets: sparkle,
        y: this.y - 44 - (i * 3),
        alpha: { from: 1, to: 0 },
        duration: 500 + (i * 100),
        ease: 'Cubic.easeOut',
        onComplete: () => {
          sparkle.destroy()
        },
      })
    }
  }

  /**
   * Subtle pixel-art work complete effect: green checkmark rising & fading
   */
  private spawnWorkCompleteEffect() {
    retroSFX.playCompleteSound()
    const checkmark = this.scene.add.text(this.x, this.y - 30, '✓ Done', {
      fontFamily: '"Courier New", Courier, monospace',
      fontSize: '8px',
      color: '#15803d',
      backgroundColor: '#dcfce7ee',
      padding: { x: 3, y: 1 },
    }).setOrigin(0.5, 1).setDepth(205)

    this.scene.tweens.add({
      targets: checkmark,
      y: this.y - 46,
      alpha: { from: 1, to: 0 },
      duration: 800,
      ease: 'Quad.easeOut',
      onComplete: () => {
        checkmark.destroy()
      },
    })
  }

  destroy(fromScene?: boolean) {
    if (this.speechTimeout) clearTimeout(this.speechTimeout)
    this.speechFadeTween?.stop()
    this.selectionAura.destroy()
    this.activityLabel.destroy()
    this.statusBubble.destroy()
    this.speechBubble.destroy()
    super.destroy(fromScene)
  }

  private updateDepth() {
    const depth = 20 + this.y / TILE_SIZE
    this.setDepth(depth)
  }
}

export default Character

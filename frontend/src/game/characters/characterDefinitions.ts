import Phaser from 'phaser'

import type { AgentId } from '../../features/agents/types'

export const CHARACTER_SIZE = 32
export const FRAMES_PER_DIRECTION = 12

export type CharacterDirection = 'down' | 'up' | 'left' | 'right'
export type CharacterMotion = 'idle' | 'walk' | 'work' | 'wait'
export type CharacterAnimation = `${CharacterMotion}_${CharacterDirection}`

type CharacterPalette = {
  skin: number
  hair: number
  shirt: number
  accent: number
  pants: number
  shoes: number
}

export type CharacterDefinition = {
  id: AgentId
  textureKey: string
  spawn: { column: number; row: number }
  facing: CharacterDirection
  palette: CharacterPalette
}

export const characterDefinitions: readonly CharacterDefinition[] = [
  {
    id: 'manager',
    textureKey: 'character-manager',
    spawn: { column: 14, row: 7 },
    facing: 'down',
    palette: {
      skin: 0xd9a078,
      hair: 0x3f2c26,
      shirt: 0x344b72,
      accent: 0xc24e4e,
      pants: 0x29354c,
      shoes: 0x312923,
    },
  },
  {
    id: 'developer',
    textureKey: 'character-developer',
    spawn: { column: 11, row: 12 },
    facing: 'right',
    palette: {
      skin: 0xc98963,
      hair: 0x252735,
      shirt: 0x7357a6,
      accent: 0xa990dc,
      pants: 0x33415f,
      shoes: 0x252936,
    },
  },
  {
    id: 'researcher',
    textureKey: 'character-researcher',
    spawn: { column: 17, row: 12 },
    facing: 'left',
    palette: {
      skin: 0xe0ad83,
      hair: 0x8a543b,
      shirt: 0xe8f0ed,
      accent: 0x2d8f88,
      pants: 0x46616e,
      shoes: 0x35454c,
    },
  },
]

const directions: readonly CharacterDirection[] = ['down', 'up', 'left', 'right']

export function getCharacterAnimationKey(
  characterId: CharacterDefinition['id'],
  animation: CharacterAnimation,
) {
  return `${characterId}-${animation}`
}

export function createCharacterAssets(scene: Phaser.Scene) {
  for (const definition of characterDefinitions) {
    if (!scene.textures.exists(definition.textureKey)) {
      createCharacterTexture(scene, definition)
    }
    createCharacterAnimations(scene, definition)
  }
}

function createCharacterAnimations(
  scene: Phaser.Scene,
  definition: CharacterDefinition,
) {
  directions.forEach((direction, directionIndex) => {
    const baseFrame = directionIndex * FRAMES_PER_DIRECTION
    const animations: Array<{
      name: CharacterAnimation
      frames: number[]
      frameRate: number
    }> = [
      {
        name: `idle_${direction}`,
        frames: [baseFrame + 0, baseFrame + 1],
        frameRate: 2,
      },
      {
        name: `walk_${direction}`,
        frames: [baseFrame + 2, baseFrame + 3, baseFrame + 4, baseFrame + 5],
        frameRate: 8,
      },
      {
        name: `work_${direction}`,
        frames: [baseFrame + 6, baseFrame + 7, baseFrame + 8, baseFrame + 9],
        frameRate: 4,
      },
      {
        name: `wait_${direction}`,
        frames: [baseFrame + 10, baseFrame + 11],
        frameRate: 2,
      },
    ]

    for (const animation of animations) {
      const key = getCharacterAnimationKey(definition.id, animation.name)
      if (scene.anims.exists(key)) continue

      scene.anims.create({
        key,
        frames: animation.frames.map((frame) => ({
          key: definition.textureKey,
          frame,
        })),
        frameRate: animation.frameRate,
        repeat: -1,
      })
    }
  })
}

function createCharacterTexture(
  scene: Phaser.Scene,
  definition: CharacterDefinition,
) {
  const frameCount = directions.length * FRAMES_PER_DIRECTION
  const texture = scene.textures.createCanvas(
    definition.textureKey,
    CHARACTER_SIZE * frameCount,
    CHARACTER_SIZE,
  )
  if (!texture) throw new Error(`Unable to create ${definition.id} spritesheet.`)

  const context = texture.getContext()
  context.imageSmoothingEnabled = false

  directions.forEach((direction, directionIndex) => {
    const baseFrame = directionIndex * FRAMES_PER_DIRECTION

    // Idle frames: 0 (standing), 1 (breathing bob + blink)
    drawCharacterFrame(context, definition, direction, baseFrame + 0, 0, 'idle', 0)
    drawCharacterFrame(context, definition, direction, baseFrame + 1, 1, 'idle', 1)

    // Walk frames: 2..5 (4-frame cadence walk cycle)
    drawCharacterFrame(context, definition, direction, baseFrame + 2, 0, 'walk', 0)
    drawCharacterFrame(context, definition, direction, baseFrame + 3, 1, 'walk', 1)
    drawCharacterFrame(context, definition, direction, baseFrame + 4, 0, 'walk', 2)
    drawCharacterFrame(context, definition, direction, baseFrame + 5, 1, 'walk', 3)

    // Work frames: 6..9 (agent-specific 4-frame work cycle)
    drawCharacterFrame(context, definition, direction, baseFrame + 6, 0, 'work', 0)
    drawCharacterFrame(context, definition, direction, baseFrame + 7, 1, 'work', 1)
    drawCharacterFrame(context, definition, direction, baseFrame + 8, 0, 'work', 2)
    drawCharacterFrame(context, definition, direction, baseFrame + 9, 1, 'work', 3)

    // Wait frames: 10..11 (2-frame thoughtful / pondering pose)
    drawCharacterFrame(context, definition, direction, baseFrame + 10, 0, 'wait', 0)
    drawCharacterFrame(context, definition, direction, baseFrame + 11, 1, 'wait', 1)
  })

  for (let frame = 0; frame < frameCount; frame += 1) {
    texture.add(
      frame,
      0,
      frame * CHARACTER_SIZE,
      0,
      CHARACTER_SIZE,
      CHARACTER_SIZE,
    )
  }
  texture.refresh()
}

function drawCharacterFrame(
  context: CanvasRenderingContext2D,
  definition: CharacterDefinition,
  direction: CharacterDirection,
  frame: number,
  bob: number,
  motion: CharacterMotion,
  phase: number,
) {
  const originX = frame * CHARACTER_SIZE
  const palette = definition.palette

  const fill = (color: number, x: number, y: number, width: number, height: number) => {
    context.fillStyle = `#${color.toString(16).padStart(6, '0')}`
    context.fillRect(originX + x, y + bob, width, height)
  }

  // 1. Drop shadow beneath feet
  fill(0x1e293b, 8, 29, 16, 2)

  // 2. Leg kinematics per motion
  let leftLegOffset = 0
  let rightLegOffset = 0
  let leftArmOffset = 0
  let rightArmOffset = 0

  if (motion === 'walk') {
    if (phase === 0) {
      leftLegOffset = 2
      rightLegOffset = -2
      leftArmOffset = -2
      rightArmOffset = 2
    } else if (phase === 1) {
      leftLegOffset = 1
      rightLegOffset = 0
      leftArmOffset = -1
      rightArmOffset = 1
    } else if (phase === 2) {
      leftLegOffset = -2
      rightLegOffset = 2
      leftArmOffset = 2
      rightArmOffset = -2
    } else if (phase === 3) {
      leftLegOffset = 0
      rightLegOffset = 1
      leftArmOffset = 1
      rightArmOffset = -1
    }
  } else if (motion === 'wait') {
    // Pondering weight shift
    leftLegOffset = phase === 0 ? 0 : -1
    rightLegOffset = phase === 0 ? 0 : 1
  }

  // 3. Pants & Shoes
  if (direction === 'left' || direction === 'right') {
    const isLeft = direction === 'left'
    fill(palette.pants, 12 + (isLeft ? -leftLegOffset : leftLegOffset), 22, 8, 7)
    fill(palette.shoes, 11 + (isLeft ? -leftLegOffset : leftLegOffset), 28, 9, 3)
  } else {
    fill(palette.pants, 10 + leftLegOffset, 22, 5, 7)
    fill(palette.pants, 18 - rightLegOffset, 22, 5, 7)
    fill(palette.shoes, 9 + leftLegOffset, 28, 6, 3)
    fill(palette.shoes, 18 - rightLegOffset, 28, 6, 3)
  }

  // 4. Arms
  if (motion === 'work') {
    // In working mode, arms position varies by agent and direction
    drawWorkArms(fill, definition, direction, phase, palette)
  } else if (motion === 'wait') {
    // Wait / thinking pose: hand on chin
    drawWaitArms(fill, definition, direction, phase, palette)
  } else {
    // Normal arms (idle or walk)
    fill(palette.skin, 5, 15 + leftArmOffset, 4, 7)
    fill(palette.skin, 23, 15 - rightArmOffset, 4, 7)
  }

  // 5. Torso / Shirt
  fill(palette.shirt, 8, 13, 16, 11)

  // 6. Agent-specific clothing details
  if (definition.id === 'manager') {
    // Manager: Navy blazer, white collar, ruby tie
    fill(0xf5f0e8, 13, 14, 6, 7)
    fill(palette.accent, 15, 15, 2, 7)
    fill(0x25324a, 9, 13, 4, 8)
    fill(0x25324a, 19, 13, 4, 8)
  } else if (definition.id === 'developer') {
    // Developer: Purple hoodie with lilac drawstring trim & pouch
    fill(palette.accent, 10, 13, 12, 3)
    fill(0x4e3a73, 12, 19, 8, 4)
    // Headphone band over head & ear cups
    fill(0x2d3748, 9, 5, 14, 2)
    fill(palette.accent, 7, 7, 3, 7)
    fill(palette.accent, 22, 7, 3, 7)
  } else {
    // Researcher: White lab coat, teal ID badge & pen pocket
    fill(palette.accent, 15, 13, 2, 11)
    fill(0xffffff, 9, 13, 5, 10)
    fill(0xffffff, 18, 13, 5, 10)
    fill(0x7dc8c1, 19, 17, 3, 3)
    fill(0x2d8f88, 11, 16, 2, 3) // pocket pen
  }

  // 7. Head & Face (Skin)
  fill(palette.skin, 9, 4, 14, 11)

  // 8. Hair & Eyes / Facial Expression
  const isBlinking = motion === 'idle' && phase === 1

  if (direction === 'down') {
    fill(palette.hair, 9, 3, 14, 4)
    fill(palette.hair, 8, 6, 3, 5)
    fill(palette.hair, 21, 6, 3, 5)
    if (isBlinking) {
      // 1px relaxed blink line
      fill(0x2a2626, 12, 11, 2, 1)
      fill(0x2a2626, 19, 11, 2, 1)
    } else {
      fill(0x2a2626, 12, 10, 2, 2)
      fill(0x2a2626, 19, 10, 2, 2)
    }
  } else if (direction === 'up') {
    fill(palette.hair, 8, 3, 16, 10)
    fill(palette.hair, 11, 12, 10, 4)
  } else {
    const facingLeft = direction === 'left'
    fill(palette.hair, 9, 3, 14, 5)
    fill(palette.hair, facingLeft ? 8 : 21, 6, 3, 7)
    if (isBlinking) {
      fill(0x2a2626, facingLeft ? 11 : 20, 10, 2, 1)
    } else {
      fill(0x2a2626, facingLeft ? 11 : 20, 9, 2, 2)
    }
    fill(palette.skin, facingLeft ? 7 : 23, 10, 3, 2)
  }

  // Researcher glasses
  if (definition.id === 'researcher' && direction !== 'up') {
    fill(0x4f6472, 10, 9, 5, 3)
    fill(0x4f6472, 18, 9, 5, 3)
    fill(0x4f6472, 15, 10, 3, 1)
    // Lens glare
    fill(0xe0f2fe, 11, 10, 2, 1)
    fill(0xe0f2fe, 19, 10, 2, 1)
  }

  // 9. Working-specific accessories & interactive tools
  if (motion === 'work') {
    drawWorkAccessories(fill, definition, direction, phase)
  }
}

function drawWorkArms(
  fill: (color: number, x: number, y: number, w: number, h: number) => void,
  definition: CharacterDefinition,
  _direction: CharacterDirection,
  phase: number,
  palette: CharacterPalette,
) {
  if (definition.id === 'developer') {
    // Developer hands reaching forward toward keyboard
    const leftY = phase % 2 === 0 ? 16 : 18
    const rightY = phase % 2 === 0 ? 18 : 16
    fill(palette.skin, 6, leftY, 4, 6)
    fill(palette.skin, 22, rightY, 4, 6)
  } else if (definition.id === 'researcher') {
    // Researcher holding notebook and magnifying glass
    fill(palette.skin, 6, 16, 4, 6)
    fill(palette.skin, 22, phase === 1 || phase === 2 ? 14 : 16, 4, 6)
  } else {
    // Manager holding clipboard in left hand, pen in right hand
    fill(palette.skin, 6, 16, 4, 6)
    fill(palette.skin, 22, phase === 1 ? 14 : 17, 4, 6)
  }
}

function drawWaitArms(
  fill: (color: number, x: number, y: number, w: number, h: number) => void,
  _definition: CharacterDefinition,
  direction: CharacterDirection,
  phase: number,
  palette: CharacterPalette,
) {
  // Pondering pose: hand brought to chin
  if (direction === 'left') {
    fill(palette.skin, 8, 12 + phase, 4, 6)
    fill(palette.skin, 21, 17, 4, 6)
  } else if (direction === 'right') {
    fill(palette.skin, 7, 17, 4, 6)
    fill(palette.skin, 20, 12 + phase, 4, 6)
  } else {
    // Down or Up: right hand to chin, left arm resting
    fill(palette.skin, 6, 17, 4, 6)
    fill(palette.skin, 19, 12 + phase, 4, 6)
  }
}

function drawWorkAccessories(
  fill: (color: number, x: number, y: number, w: number, h: number) => void,
  definition: CharacterDefinition,
  direction: CharacterDirection,
  phase: number,
) {
  if (definition.id === 'developer') {
    // Laptop / Keyboard with glowing screen & matrix light
    if (direction === 'down' || direction === 'left' || direction === 'right') {
      // Laptop base
      fill(0x334155, 9, 21, 14, 3)
      // Screen
      fill(0x0f172a, 10, 15, 12, 6)
      // Screen code glow
      const glowColor = phase % 2 === 0 ? 0x38bdf8 : 0x06b6d4
      fill(glowColor, 11, 16, 10, 4)
      // Code syntax highlight lines
      fill(0x22c55e, 12, 17, 4, 1)
      fill(0xfbbf24, 17, 17, 3, 1)
      fill(0xffffff, 12, 19, 6, 1)
    } else {
      // Facing up at workstation monitor: back of head glows slightly with monitor reflection
      const glowTop = phase % 2 === 0 ? 0x38bdf8 : 0x67e8f9
      fill(glowTop, 10, 1, 12, 2)
    }
  } else if (definition.id === 'researcher') {
    // Open Research Journal + Magnifying Glass
    if (direction === 'down' || direction === 'left' || direction === 'right') {
      // Notebook
      fill(0x78350f, 8, 18, 8, 7) // leather cover
      fill(0xfef9c3, 9, 19, 6, 5) // parchment pages
      fill(0x334155, 10, 20, 4, 1) // text line
      fill(0x334155, 10, 22, 3, 1) // text line

      // Magnifying glass with crystal lens
      const lensY = phase === 1 || phase === 2 ? 14 : 16
      fill(0xd97706, 21, lensY + 3, 2, 4) // handle
      fill(0x0d9488, 19, lensY, 5, 4)     // metal rim
      fill(0x5eead4, 20, lensY + 1, 3, 2) // crystal lens
      if (phase === 2) {
        fill(0xffffff, 20, lensY + 1, 1, 1) // lens glint sparkle
      }
    } else {
      // Facing up: book open on desk
      fill(0xfef9c3, 10, 18, 12, 4)
      fill(0x2d8f88, 11, 19, 10, 2)
    }
  } else if (definition.id === 'manager') {
    // Executive Clipboard with Tasks & Pen
    if (direction === 'down' || direction === 'left' || direction === 'right') {
      // Clipboard board & paper
      fill(0x92400e, 7, 17, 10, 9)  // board
      fill(0xffffff, 8, 18, 8, 7)   // paper
      fill(0xc24e4e, 10, 16, 4, 2)  // clip
      // Checklist items
      fill(0x16a34a, 9, 19, 2, 2)   // green check
      fill(0x475569, 12, 19, 3, 1)  // line
      fill(0x16a34a, 9, 22, 2, 2)   // green check
      fill(0x475569, 12, 22, 3, 1)  // line
      // Red pen in hand
      const penY = phase === 1 ? 15 : 18
      fill(0xef4444, 21, penY, 2, 5)
    } else {
      // Facing up: organizing desk planner
      fill(0xffffff, 9, 18, 14, 4)
      fill(0xc24e4e, 13, 17, 6, 2)
    }
  }
}

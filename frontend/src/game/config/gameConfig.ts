import Phaser from 'phaser'

import BootScene from '../scenes/BootScene'
import OfficeScene from '../scenes/OfficeScene'

export function createGameConfig(
  parent: HTMLDivElement,
  width: number,
  height: number,
): Phaser.Types.Core.GameConfig {
  return {
    type: Phaser.CANVAS,
    parent,
    width,
    height,
    backgroundColor: '#f8fafc',
    pixelArt: true,
    antialias: false,
    audio: {
      noAudio: true,
    },
    scale: {
      mode: Phaser.Scale.RESIZE,
      width,
      height,
    },
    scene: [BootScene, OfficeScene],
  }
}

import Phaser from 'phaser'

class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' })
  }

  create() {
    this.scene.start('OfficeScene')
  }
}

export default BootScene

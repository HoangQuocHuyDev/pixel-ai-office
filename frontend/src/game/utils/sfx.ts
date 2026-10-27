/**
 * Retro 8-bit Sound Effects Synthesizer using Web Audio API.
 * Generates procedural retro sound effects without external audio files.
 */

const SFX_MUTED_STORAGE_KEY = 'pixel_office_sfx_muted'

class RetroSFX {
  private audioCtx: AudioContext | null = null
  private muted: boolean = false

  constructor() {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(SFX_MUTED_STORAGE_KEY)
      this.muted = saved === 'true'
    }
  }

  isMuted(): boolean {
    return this.muted
  }

  setMuted(muted: boolean): boolean {
    this.muted = muted
    if (typeof window !== 'undefined') {
      localStorage.setItem(SFX_MUTED_STORAGE_KEY, String(muted))
    }
    return this.muted
  }

  toggleMute(): boolean {
    return this.setMuted(!this.muted)
  }

  private getAudioContext(): AudioContext | null {
    if (this.muted) return null
    if (typeof window === 'undefined') return null

    if (!this.audioCtx) {
      const AudioCtxClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      if (!AudioCtxClass) return null
      this.audioCtx = new AudioCtxClass()
    }

    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume().catch(() => {})
    }

    return this.audioCtx
  }

  /**
   * Short 8-bit blip for agent selection (triangle wave sweep 440Hz -> 880Hz)
   */
  playSelectSound() {
    const ctx = this.getAudioContext()
    if (!ctx) return

    try {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()

      osc.type = 'triangle'
      osc.frequency.setValueAtTime(440, ctx.currentTime)
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.07)

      gain.gain.setValueAtTime(0.12, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08)

      osc.connect(gain)
      gain.connect(ctx.destination)

      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.09)
    } catch {
      // Audio playback failsafe
    }
  }

  /**
   * 8-bit victory chime for task completion (C5 -> E5 -> G5)
   */
  playCompleteSound() {
    const ctx = this.getAudioContext()
    if (!ctx) return

    try {
      const notes = [523.25, 659.25, 783.99] // C5, E5, G5
      notes.forEach((freq, i) => {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        const startTime = ctx.currentTime + i * 0.08

        osc.type = 'square'
        osc.frequency.setValueAtTime(freq, startTime)

        gain.gain.setValueAtTime(0.08, startTime)
        gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.12)

        osc.connect(gain)
        gain.connect(ctx.destination)

        osc.start(startTime)
        osc.stop(startTime + 0.13)
      })
    } catch {
      // Audio failsafe
    }
  }

  /**
   * 8-bit step/slide chirp for seat relocation (330Hz -> 587Hz)
   */
  playRelocateSound() {
    const ctx = this.getAudioContext()
    if (!ctx) return

    try {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()

      osc.type = 'sine'
      osc.frequency.setValueAtTime(330, ctx.currentTime)
      osc.frequency.exponentialRampToValueAtTime(587, ctx.currentTime + 0.1)

      gain.gain.setValueAtTime(0.1, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.12)

      osc.connect(gain)
      gain.connect(ctx.destination)

      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.13)
    } catch {
      // Audio failsafe
    }
  }

  /**
   * Gentle speech chirp when speech bubble appears (587Hz -> 659Hz)
   */
  playSpeechSound() {
    const ctx = this.getAudioContext()
    if (!ctx) return

    try {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()

      osc.type = 'triangle'
      osc.frequency.setValueAtTime(587.33, ctx.currentTime)
      osc.frequency.exponentialRampToValueAtTime(659.25, ctx.currentTime + 0.05)

      gain.gain.setValueAtTime(0.06, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.06)

      osc.connect(gain)
      gain.connect(ctx.destination)

      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.07)
    } catch {
      // Audio failsafe
    }
  }
}

export const retroSFX = new RetroSFX()
export default retroSFX


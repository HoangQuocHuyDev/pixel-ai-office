import type Phaser from 'phaser'

/**
 * Checks if a target DOM element is a text input field where
 * keyboard typing should not be captured or prevented by Phaser.
 */
export function isTextInputElement(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) {
    return false
  }
  const tag = target.tagName
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    target.isContentEditable
  )
}

/**
 * Returns true if the event target or current active element is a text input.
 */
export function isInputFocused(eventTarget: EventTarget | null): boolean {
  if (isTextInputElement(eventTarget)) {
    return true
  }
  if (typeof document !== 'undefined' && isTextInputElement(document.activeElement)) {
    return true
  }
  return false
}

/**
 * Scopes Phaser's global KeyboardManager so that keyboard events originating
 * from or directed to HTML text input elements (inputs, textareas, contenteditables)
 * are completely ignored by Phaser — preventing preventDefault from blocking
 * typing (like Space, Enter, Backspace) while preserving full game controls
 * (camera panning with Space + drag) when interacting with the canvas.
 */
export function setupKeyboardScope(scene: Phaser.Scene): () => void {
  const keyboardManager = scene.game.input?.keyboard
  if (!keyboardManager) return () => {}

  const target = keyboardManager.target as (EventTarget & {
    addEventListener: typeof window.addEventListener
    removeEventListener: typeof window.removeEventListener
  }) | null

  if (!target) return () => {}

  const originalOnKeyDown = keyboardManager.onKeyDown as (event: KeyboardEvent) => void
  const originalOnKeyUp = keyboardManager.onKeyUp as (event: KeyboardEvent) => void

  // Detach raw Phaser listeners
  target.removeEventListener('keydown', originalOnKeyDown, false)
  target.removeEventListener('keyup', originalOnKeyUp, false)

  const filteredOnKeyDown = (event: KeyboardEvent) => {
    // If the event originates from or focus is in an input element, bypass Phaser
    if (isInputFocused(event.target)) {
      return
    }
    originalOnKeyDown(event)
  }

  const filteredOnKeyUp = (event: KeyboardEvent) => {
    if (isInputFocused(event.target)) {
      return
    }
    originalOnKeyUp(event)
  }

  // Attach scoped listeners
  target.addEventListener('keydown', filteredOnKeyDown, false)
  target.addEventListener('keyup', filteredOnKeyUp, false)

  keyboardManager.onKeyDown = filteredOnKeyDown
  keyboardManager.onKeyUp = filteredOnKeyUp

  // When focus moves to an input element, reset all keys in Phaser
  // so no key remains stuck in a "down" state during text entry
  const onFocusIn = (event: FocusEvent) => {
    if (isTextInputElement(event.target)) {
      scene.input.keyboard?.resetKeys()
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('focusin', onFocusIn)
  }

  return () => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('focusin', onFocusIn)
    }
    target.removeEventListener('keydown', filteredOnKeyDown, false)
    target.removeEventListener('keyup', filteredOnKeyUp, false)
    target.addEventListener('keydown', originalOnKeyDown, false)
    target.addEventListener('keyup', originalOnKeyUp, false)
    keyboardManager.onKeyDown = originalOnKeyDown
    keyboardManager.onKeyUp = originalOnKeyUp
  }
}


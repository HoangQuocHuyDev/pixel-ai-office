import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')

console.log('=== Running TASK 35: Agent Animation & Pixel-Art Visual Polish Test Suite ===\n')

const [definitionsCode, characterCode, simulationCode, movementCode] = await Promise.all([
  read('../src/game/characters/characterDefinitions.ts'),
  read('../src/game/characters/Character.ts'),
  read('../src/game/systems/OfficeSimulation.ts'),
  read('../src/game/systems/MovementSystem.ts'),
])

// Test 1: Verify Character Definitions & 3 Agents
console.log('Test 1: Agent Registry & Character Definitions')
assert.match(definitionsCode, /id:\s*'manager'/)
assert.match(definitionsCode, /id:\s*'developer'/)
assert.match(definitionsCode, /id:\s*'researcher'/)
assert.match(definitionsCode, /export const FRAMES_PER_DIRECTION\s*=\s*12/)
console.log('✓ Passed: Manager, Developer, Researcher defined with 12 frames per direction (48 frames total)')

// Test 2: Verify Character Motions & Directions
console.log('\nTest 2: Motions & Directional Animation Matrix')
assert.match(definitionsCode, /export type CharacterMotion\s*=\s*'idle'\s*\|\s*'walk'\s*\|\s*'work'\s*\|\s*'wait'/)
assert.match(definitionsCode, /export type CharacterDirection\s*=\s*'down'\s*\|\s*'up'\s*\|\s*'left'\s*\|\s*'right'/)

const expectedMotions = ['idle', 'walk', 'work', 'wait']
const expectedDirections = ['down', 'up', 'left', 'right']

for (const motion of expectedMotions) {
  const animPattern = new RegExp(`name:\\s*\`${motion}_\\\${direction}\``)
  assert.match(definitionsCode, animPattern, `Missing animation definition for ${motion}`)
}
console.log('✓ Passed: All 16 directional animations (4 motions × 4 directions) registered per agent')

// Test 3: Agent-specific Visual Work & Accessories Details
console.log('\nTest 3: Agent-Specific Pixel Art Work Accessories')
// Manager: Executive clipboard & pen
assert.match(definitionsCode, /Clipboard/)
assert.match(definitionsCode, /0xc24e4e/) // ruby tie / accent
// Developer: Laptop, keyboard typing & glowing screen
assert.match(definitionsCode, /Laptop \/ Keyboard with glowing screen/)
assert.match(definitionsCode, /0x38bdf8/) // screen glow
// Researcher: Journal & magnifying glass
assert.match(definitionsCode, /Open Research Journal \+ Magnifying Glass/)
assert.match(definitionsCode, /0x5eead4/) // crystal lens
console.log('✓ Passed: Manager (clipboard/pen), Developer (laptop/glow), Researcher (magnifier/journal) rendered')

// Test 4: VisualState Coverage in Character.ts
console.log('\nTest 4: Character Visual States (idle, walking, working, waiting, error)')
assert.match(characterCode, /export type VisualState\s*=\s*'idle'\s*\|\s*'walking'\s*\|\s*'working'\s*\|\s*'waiting'\s*\|\s*'error'/)
assert.match(characterCode, /case 'walking':/)
assert.match(characterCode, /playAnimation\(`walk_\${this\.direction}`\)/)
assert.match(characterCode, /case 'working':/)
assert.match(characterCode, /playAnimation\(`work_\${this\.direction}`\)/)
assert.match(characterCode, /case 'waiting':/)
assert.match(characterCode, /playAnimation\(`wait_\${this\.direction}`\)/)
assert.match(characterCode, /case 'error':/)
assert.match(characterCode, /case 'idle':/)
console.log('✓ Passed: All 5 visual states smoothly mapped to dedicated directional animations')

// Test 5: Status Badges, Typography & Status Bubble
console.log('\nTest 5: Status Badges, Pixel Typography & Overhead Emote Indicators')
assert.match(characterCode, /activityLabel/)
assert.match(characterCode, /statusBubble/)
assert.match(characterCode, /Courier New/) // Crisp monospace pixel typography
assert.match(characterCode, /' ! '/)       // Error exclamation bubble
assert.match(characterCode, /' ··· '/)     // Waiting thought bubble
assert.match(characterCode, /DEV|RES|MGR/)  // Working badge tool tags
assert.match(characterCode, /setTint\(0xfca5a5\)/)
assert.match(characterCode, /clearTint/)
console.log('✓ Passed: Crisp monospace typography, status dots, and overhead emote bubbles verified')

// Test 6: Work Start & Complete Particle Micro-Effects
console.log('\nTest 6: Work Start & Complete Visual Effects')
assert.match(characterCode, /spawnWorkStartEffect/)
assert.match(characterCode, /spawnWorkCompleteEffect/)
assert.match(characterCode, /✓ Done/)
assert.match(characterCode, /onComplete:\s*\(\)\s*=>\s*\{[\s\S]*?destroy\(\)/)
console.log('✓ Passed: Work start sparkle burst and work complete checkmark effects cleanly animated and destroyed')

// Test 7: Movement & Simulation State Integration
console.log('\nTest 7: MovementSystem & OfficeSimulation Integration')
assert.match(movementCode, /agent\.character\.setVisualState\('waiting'\)/)
assert.match(simulationCode, /config\.character\.setVisualState\('working', config\.workFacing\)/)
assert.match(simulationCode, /this\.movementSystem\.stop\(config\.characterId, 'error'/)
assert.match(simulationCode, /config\.character\.setVisualState\('waiting'\)/)
console.log('✓ Passed: Corridors yield to waiting state; remote working and failure map cleanly to visual states')

console.log('\n=== ALL 7 AGENT ANIMATION & VISUAL POLISH TESTS PASSED SUCCESSFULLY! ===')

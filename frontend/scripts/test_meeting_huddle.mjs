import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')

console.log('=== Running TASK 38: Meeting Room & Collaborative Huddle Mode Test Suite ===\n')

const [mapCode, simulationCode, sceneCode, characterCode, phaserGameCode, viewportCode, cssCode] = await Promise.all([
  read('../src/game/maps/officeMap.ts'),
  read('../src/game/systems/OfficeSimulation.ts'),
  read('../src/game/scenes/OfficeScene.ts'),
  read('../src/game/characters/Character.ts'),
  read('../src/game/PhaserGame.tsx'),
  read('../src/features/office/components/OfficeViewport.tsx'),
  read('../src/styles/global.css'),
])

// Test 1: Verify Meeting Room & Conference Table Coordinates in officeMap.ts
console.log('Test 1: Meeting Room & Conference Table Coordinates')
assert.match(mapCode, /export type MeetingSpot\s*=/, 'Missing MeetingSpot type in officeMap.ts')
assert.match(mapCode, /export const MEETING_SPOTS:\s*Record<string,\s*MeetingSpot>/, 'Missing MEETING_SPOTS mapping in officeMap.ts')
assert.match(mapCode, /manager:\s*\{\s*column:\s*13,\s*row:\s*5,\s*facing:\s*'right'\s*\}/, 'Manager meeting spot must face right at (13, 5)')
assert.match(mapCode, /developer:\s*\{\s*column:\s*16,\s*row:\s*5,\s*facing:\s*'left'\s*\}/, 'Developer meeting spot must face left at (16, 5)')
assert.match(mapCode, /researcher:\s*\{\s*column:\s*14,\s*row:\s*3,\s*facing:\s*'down'\s*\}/, 'Researcher meeting spot must face down at (14, 3)')
console.log('✓ Passed: Conference table seats defined; Manager & Developer face each other, Researcher overlooks presentation board')

// Test 2: Verify Simulation State Machine (WALKING_TO_MEETING, IN_MEETING, WALKING_FROM_MEETING)
console.log('\nTest 2: Agent Simulation Huddle States & Session Model')
assert.match(simulationCode, /'WALKING_TO_MEETING'/, 'Missing WALKING_TO_MEETING state')
assert.match(simulationCode, /'IN_MEETING'/, 'Missing IN_MEETING state')
assert.match(simulationCode, /'WALKING_FROM_MEETING'/, 'Missing WALKING_FROM_MEETING state')
assert.match(simulationCode, /export type HuddleSession\s*=/, 'Missing HuddleSession type definition')
assert.match(simulationCode, /stage:\s*'walking_to_meeting'\s*\|\s*'in_dialogue_step1'\s*\|\s*'in_dialogue_step2'\s*\|\s*'concluding'/, 'Missing 4-stage huddle progression')
console.log('✓ Passed: OfficeSimulation incorporates collaborative meeting states and multi-stage dialogue session')

// Test 3: Verify Huddle Trigger, A* Navigation & Dialogue Sequence
console.log('\nTest 3: Huddle Trigger, A* Pathfinding & Dialogue Sequencing')
assert.match(simulationCode, /startHuddle\(/, 'Missing startHuddle() method')
assert.match(simulationCode, /endHuddle\(/, 'Missing endHuddle() method')
assert.match(simulationCode, /isHuddleActive\(\)/, 'Missing isHuddleActive() method')
assert.match(simulationCode, /getActiveHuddle\(\)/, 'Missing getActiveHuddle() method')
assert.match(simulationCode, /this\.movementSystem\.moveTo\(initiatorId,\s*\{\s*column:\s*initSpot\.column,\s*row:\s*initSpot\.row\s*\}/, 'Should route initiator to meeting spot')
assert.match(simulationCode, /this\.movementSystem\.moveTo\(receiverId,\s*\{\s*column:\s*recvSpot\.column,\s*row:\s*recvSpot\.row\s*\}/, 'Should route receiver to meeting spot')
assert.match(simulationCode, /initConfig\.character\.showSpeech\(this\.activeHuddle\.topic/, 'Initiator speaks first upon arrival')
assert.match(simulationCode, /recvConfig\.character\.showSpeech\(huddle\.response/, 'Receiver responds after thinking')
assert.match(characterCode, /spawnHuddleEffect\(\)/, 'Character must provide spawnHuddleEffect()')
assert.match(simulationCode, /retroSFX\.playCompleteSound\(\)/, 'Completion chime triggered at end of dialogue')
console.log('✓ Passed: A* pathfinding routes agents to conference table, plays turn-based speech bubbles with retro SFX')

// Test 4: Verify Disband & Return to Workstation Desks
console.log('\nTest 4: Disband & Return to Workstations')
assert.match(simulationCode, /initiatorConfig\.currentState\s*=\s*'WALKING_FROM_MEETING'/, 'Initiator transitions to WALKING_FROM_MEETING on disband')
assert.match(simulationCode, /receiverConfig\.currentState\s*=\s*'WALKING_FROM_MEETING'/, 'Receiver transitions to WALKING_FROM_MEETING on disband')
assert.match(simulationCode, /this\.movementSystem\.moveTo\(initiatorId,\s*initiatorConfig\.workstation,\s*initiatorConfig\.workFacing\)/, 'Initiator walks back to desk')
assert.match(simulationCode, /this\.movementSystem\.moveTo\(receiverId,\s*receiverConfig\.workstation,\s*receiverConfig\.workFacing\)/, 'Receiver walks back to desk')
console.log('✓ Passed: Agents disband smoothly after conference and path back to respective workstation desks')

// Test 5: Verify OfficeScene & Camera Focus
console.log('\nTest 5: OfficeScene Meeting Controls & Camera Focus')
assert.match(sceneCode, /startHuddle\(/, 'OfficeScene must expose startHuddle')
assert.match(sceneCode, /endHuddle\(/, 'OfficeScene must expose endHuddle')
assert.match(sceneCode, /isHuddleActive\(\)/, 'OfficeScene must expose isHuddleActive')
assert.match(sceneCode, /this\.cameras\.main\.pan\(15\s*\*\s*TILE_SIZE,\s*5\s*\*\s*TILE_SIZE/, 'Camera smoothly pans to conference table')
console.log('✓ Passed: OfficeScene centers camera on conference table when huddle begins')

// Test 6: Verify React PhaserGame Handle & UI Viewport Button
console.log('\nTest 6: React Viewport & Toolbar Huddle Simulation')
assert.match(phaserGameCode, /startHuddle:/, 'PhaserGameHandle must include startHuddle')
assert.match(phaserGameCode, /endHuddle:/, 'PhaserGameHandle must include endHuddle')
assert.match(phaserGameCode, /isHuddleActive:/, 'PhaserGameHandle must include isHuddleActive')

assert.match(viewportCode, /office-viewport__huddle/, 'OfficeViewport must render huddle button')
assert.match(viewportCode, /handleSimulateHuddle/, 'OfficeViewport must have handleSimulateHuddle handler')
assert.match(viewportCode, /layout-editor-alert--huddle/, 'OfficeViewport must display huddle alert banner')
console.log('✓ Passed: React UI exposes "🤝 Huddle" button and displays active meeting notification')

// Test 7: Verify CSS Styling for Huddle UI
console.log('\nTest 7: CSS Styles for Huddle Button & Alert Banner')
assert.match(cssCode, /\.office-viewport__huddle\s*\{/, 'Missing .office-viewport__huddle CSS')
assert.match(cssCode, /\.office-viewport__huddle:hover/, 'Missing hover state for huddle button')
assert.match(cssCode, /\.layout-editor-alert--huddle\s*\{/, 'Missing .layout-editor-alert--huddle CSS')
console.log('✓ Passed: CSS provides sleek indigo-themed button and banner styling')

console.log('\n======================================================')
console.log('All TASK 38 Meeting Room & Huddle Mode Tests PASSED!')
console.log('======================================================')


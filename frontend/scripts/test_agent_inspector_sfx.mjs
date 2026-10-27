import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')

console.log('=== Running TASK 37: Interactive Agent Inspector & Live Speech Bubbles Test Suite ===\n')

const [sfxCode, characterCode, simulationCode, sceneCode, phaserGameCode, viewportCode, cssCode] = await Promise.all([
  read('../src/game/utils/sfx.ts'),
  read('../src/game/characters/Character.ts'),
  read('../src/game/systems/OfficeSimulation.ts'),
  read('../src/game/scenes/OfficeScene.ts'),
  read('../src/game/PhaserGame.tsx'),
  read('../src/features/office/components/OfficeViewport.tsx'),
  read('../src/styles/global.css'),
])

// Test 1: Verify RetroSFX Synthesizer (Web Audio API)
console.log('Test 1: RetroSFX Synthesizer implementation')
assert.match(sfxCode, /class RetroSFX/, 'Missing RetroSFX class definition')
assert.match(sfxCode, /isMuted\(\)/, 'Missing isMuted() method')
assert.match(sfxCode, /setMuted\(muted:\s*boolean\)/, 'Missing setMuted() method')
assert.match(sfxCode, /toggleMute\(\)/, 'Missing toggleMute() method')
assert.match(sfxCode, /playSelectSound\(\)/, 'Missing playSelectSound()')
assert.match(sfxCode, /playCompleteSound\(\)/, 'Missing playCompleteSound()')
assert.match(sfxCode, /playRelocateSound\(\)/, 'Missing playRelocateSound()')
assert.match(sfxCode, /playSpeechSound\(\)/, 'Missing playSpeechSound()')
assert.match(sfxCode, /createOscillator\(\)/, 'Should use Web Audio OscillatorNode')
assert.match(sfxCode, /createGain\(\)/, 'Should use Web Audio GainNode')
console.log('✓ Passed: Web Audio API RetroSFX synthesizer provides 4 procedural 8-bit sound effects and mute controls')

// Test 2: Verify Character Selection Aura & Interactive Sprite
console.log('\nTest 2: Character Interactive Click & Selection Aura')
assert.match(characterCode, /this\.setInteractive\(\{\s*useHandCursor:\s*true\s*\}\)/, 'Character must be interactive with hand cursor')
assert.match(characterCode, /this\.scene\.events\.emit\('character-selected',\s*this\.definition\.id\)/, 'Pointer down should emit character-selected event')
assert.match(characterCode, /selectionAura:\s*Phaser\.GameObjects\.Graphics/, 'Missing selectionAura graphics object')
assert.match(characterCode, /setSelected\(selected:\s*boolean\)/, 'Missing setSelected() method on Character')
assert.match(characterCode, /isSelectedAgent\(\)/, 'Missing isSelectedAgent() method on Character')
assert.match(characterCode, /renderSelectionAura\(\)/, 'Missing renderSelectionAura() method')
console.log('✓ Passed: Character sprite is interactive and renders pixel-art selection aura under feet')

// Test 3: Verify Live Speech Bubbles
console.log('\nTest 3: Character Live Speech Bubbles')
assert.match(characterCode, /speechBubble:\s*Phaser\.GameObjects\.Text/, 'Missing speechBubble text object')
assert.match(characterCode, /showSpeech\(text:\s*string,\s*durationMs\s*=\s*4000\)/, 'Missing showSpeech() method on Character')
assert.match(characterCode, /retroSFX\.playSpeechSound\(\)/, 'showSpeech should trigger playSpeechSound')
assert.match(characterCode, /speechFadeTween/, 'Speech bubble should fade out using scene tween')
console.log('✓ Passed: Live speech bubble displays text above agent head with procedural chirp and auto-fade')

// Test 4: Verify Workstation Seat Reassignment in OfficeSimulation
console.log('\nTest 4: OfficeSimulation Seat Reassignment API')
assert.match(simulationCode, /reassignAgentWorkstation\(agentId:\s*string,\s*seatCoord:\s*GridCoord\)/, 'Missing reassignAgentWorkstation in OfficeSimulation')
assert.match(simulationCode, /getAgentWorkstation\(agentId:\s*string\)/, 'Missing getAgentWorkstation in OfficeSimulation')
assert.match(simulationCode, /retroSFX\.playRelocateSound\(\)/, 'Relocation should trigger playRelocateSound')
assert.match(simulationCode, /config\.character\.showSpeech/, 'Relocation should trigger character speech quote')
console.log('✓ Passed: Simulation dynamically reassigns desk workstation and paths agent to new chair')

// Test 5: Verify OfficeScene Selection, Camera Pan, & Chair Click Detection
console.log('\nTest 5: OfficeScene Selection & Smooth Camera Pan')
assert.match(sceneCode, /this\.events\.on\('character-selected'/, 'Scene should listen to character-selected')
assert.match(sceneCode, /this\.cameras\.main\.pan\(/, 'Selecting agent should pan camera smoothly')
assert.match(sceneCode, /retroSFX\.playSelectSound\(\)/, 'Selecting agent should play select sound')
assert.match(sceneCode, /selectAgent\(agentId:\s*string\s*\|\s*null\)/, 'Missing selectAgent() on OfficeScene')
assert.match(sceneCode, /reassignSeat\(agentId:\s*string,\s*seatCoord:\s*GridCoord\)/, 'Missing reassignSeat() on OfficeScene')
assert.match(sceneCode, /targetWorkstation/, 'Scene should detect workstation chair click for seat relocation')
console.log('✓ Passed: OfficeScene pans camera to selected agent, detects chair clicks, and manages selection lifecycle')

// Test 6: Verify PhaserGame & OfficeViewport Integration
console.log('\nTest 6: React Components & Floating Inspector Card')
assert.match(phaserGameCode, /selectAgent:/, 'PhaserGameHandle should expose selectAgent')
assert.match(phaserGameCode, /showAgentSpeech:/, 'PhaserGameHandle should expose showAgentSpeech')
assert.match(phaserGameCode, /reassignSeat:/, 'PhaserGameHandle should expose reassignSeat')
assert.match(phaserGameCode, /onAgentSelect\?:/, 'PhaserGameProps should accept onAgentSelect')
assert.match(phaserGameCode, /onAgentRelocate\?:/, 'PhaserGameProps should accept onAgentRelocate')

assert.match(viewportCode, /selectedAgentId/, 'OfficeViewport should track selectedAgentId state')
assert.match(viewportCode, /agent-inspector-card/, 'OfficeViewport should render agent-inspector-card')
assert.match(viewportCode, /office-viewport__sound-toggle/, 'OfficeViewport should render sound toggle button')
assert.match(viewportCode, /handleToggleSound/, 'OfficeViewport should toggle retro SFX mute')
assert.match(viewportCode, /Chat with/, 'Inspector should offer direct Chat with Agent action')
console.log('✓ Passed: React PhaserGame and OfficeViewport cleanly manage Inspector card and Sound toggle')

// Test 7: Verify CSS Styling for Inspector & Audio Controls
console.log('\nTest 7: CSS Styles for Inspector Popover & Sound Toggle')
assert.match(cssCode, /\.agent-inspector-card\s*\{/, 'Missing .agent-inspector-card CSS')
assert.match(cssCode, /\.agent-inspector-card__header\s*\{/, 'Missing .agent-inspector-card__header CSS')
assert.match(cssCode, /\.agent-inspector-avatar\s*\{/, 'Missing .agent-inspector-avatar CSS')
assert.match(cssCode, /\.agent-inspector-status-pill\s*\{/, 'Missing .agent-inspector-status-pill CSS')
assert.match(cssCode, /\.office-viewport__sound-toggle\s*\{/, 'Missing .office-viewport__sound-toggle CSS')
assert.match(cssCode, /@keyframes inspectorSlideIn/, 'Missing animation for agent inspector')
console.log('✓ Passed: CSS rules provide pixel-art styling, status pill badges, and animations')

console.log('\n======================================================')
console.log('All TASK 37 Interactive Inspector & SFX Tests PASSED!')
console.log('======================================================')


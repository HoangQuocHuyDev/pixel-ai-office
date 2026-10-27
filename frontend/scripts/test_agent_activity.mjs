import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')
const [hook, client, game, scene, simulation, character, viewport] = await Promise.all([
  read('../src/features/agents/hooks/useAgentActivities.ts'),
  read('../src/features/agents/api/agentClient.ts'),
  read('../src/game/PhaserGame.tsx'),
  read('../src/game/scenes/OfficeScene.ts'),
  read('../src/game/systems/OfficeSimulation.ts'),
  read('../src/game/characters/Character.ts'),
  read('../src/features/office/components/OfficeViewport.tsx'),
])

assert.match(client, /\/api\/v1\/agents\/activities/)
assert.match(client, /signal/)
assert.match(hook, /2500/)
assert.match(hook, /setTimeout\(poll/)
assert.doesNotMatch(hook, /setInterval/)
assert.match(hook, /controller\?\.abort\(\)/)
assert.match(hook, /clearTimeout/)
assert.match(hook, /snapshot !== snapshotRef\.current/)
assert.equal((game.match(/new Phaser\.Game/g) ?? []).length, 1)
assert.match(game, /registry\.set\('agentActivities'/)
assert.match(scene, /updateAgentActivities/)
assert.match(scene, /simulation\?\.applyActivities/)
assert.match(simulation, /REMOTE_WALKING_TO_WORK/)
assert.match(simulation, /movementSystem\.moveTo\(config\.characterId, config\.workstation/)
assert.match(simulation, /movementSystem\.stop\(config\.characterId/)
assert.match(simulation, /previousStatus !== null && previousStatus !== 'idle'/)
assert.match(character, /setActivityLabel/)
assert.match(character, /setTint\(0xfca5a5\)/)
assert.match(viewport, /Agent activity connection unavailable/)
assert.match(viewport, /activities=\{activities\}/)

console.log('Agent activity and React-Phaser bridge checks passed.')

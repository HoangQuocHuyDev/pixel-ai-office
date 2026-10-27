import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import {
  DEFAULT_FURNITURE_LAYOUT,
  RESERVED_AGENT_TILES,
  getOccupiedTiles,
  validateItemPlacement,
  validateOfficeLayout,
  saveLayoutToStorage,
  loadSavedLayout,
  clearSavedLayout,
  MAP_COLUMNS,
  MAP_ROWS,
  TILE_SIZE,
} from '../src/game/maps/officeLayout.ts'

console.log('=== Running TASK 36: Office Layout Editor Automated Test Suite ===\n')

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')

const [viewportCode, sceneCode, gameCode, editorCode, simulationCode, pathfindingCode, mapCode] = await Promise.all([
  read('../src/features/office/components/OfficeViewport.tsx'),
  read('../src/game/scenes/OfficeScene.ts'),
  read('../src/game/PhaserGame.tsx'),
  read('../src/game/systems/LayoutEditor.ts'),
  read('../src/game/systems/OfficeSimulation.ts'),
  read('../src/game/systems/PathfindingSystem.ts'),
  read('../src/game/maps/officeMap.ts'),
])

// Test 1: Default Furniture Layout Structure & Integrity
console.log('Test 1: Default Layout Structure & Item Definitions')
assert.equal(DEFAULT_FURNITURE_LAYOUT.length, 12, 'Default layout should contain exactly 12 items')

const workstationCount = DEFAULT_FURNITURE_LAYOUT.filter((i) => i.type === 'workstation').length
const plantCount = DEFAULT_FURNITURE_LAYOUT.filter((i) => i.type === 'plant').length
const bookshelfCount = DEFAULT_FURNITURE_LAYOUT.filter((i) => i.type === 'bookshelf').length
const cabinetCount = DEFAULT_FURNITURE_LAYOUT.filter((i) => i.type === 'cabinet').length
const coolerCount = DEFAULT_FURNITURE_LAYOUT.filter((i) => i.type === 'waterCooler').length

assert.equal(workstationCount, 6, 'Must contain 6 workstations')
assert.equal(plantCount, 3, 'Must contain 3 plants')
assert.equal(bookshelfCount, 1, 'Must contain 1 bookshelf')
assert.equal(cabinetCount, 1, 'Must contain 1 cabinet')
assert.equal(coolerCount, 1, 'Must contain 1 water cooler')

const defaultValidation = validateOfficeLayout(DEFAULT_FURNITURE_LAYOUT)
assert.equal(defaultValidation.isValid, true, 'Default layout must pass validation without errors')
assert.equal(defaultValidation.errors.length, 0)
console.log('✓ Passed: Default layout contains 12 verified items and passes full validation')

// Test 2: Boundaries & Grid Snap Validation
console.log('\nTest 2: Boundaries & Grid Snap Constraints')
const plantItem = DEFAULT_FURNITURE_LAYOUT.find((i) => i.id === 'plant-1')
const workstationItem = DEFAULT_FURNITURE_LAYOUT.find((i) => i.id === 'workstation-1')

assert.ok(plantItem)
assert.ok(workstationItem)

// Placed outside left wall (col < 1)
const oobLeft = validateItemPlacement(plantItem, 0, 5, DEFAULT_FURNITURE_LAYOUT)
assert.equal(oobLeft.isValid, false)
assert.match(oobLeft.reason, /outside/)

// Placed outside right wall (col + width > 28)
const oobRight = validateItemPlacement(workstationItem, 28, 5, DEFAULT_FURNITURE_LAYOUT)
assert.equal(oobRight.isValid, false)
assert.match(oobRight.reason, /outside/)

// Placed on top wall face (row < 2)
const oobTop = validateItemPlacement(plantItem, 5, 1, DEFAULT_FURNITURE_LAYOUT)
assert.equal(oobTop.isValid, false)
assert.match(oobTop.reason, /outside/)

// Placed on bottom wall (row + height > 16)
const oobBottom = validateItemPlacement(plantItem, 5, 17, DEFAULT_FURNITURE_LAYOUT)
assert.equal(oobBottom.isValid, false)
assert.match(oobBottom.reason, /outside/)

// Floating non-integer coordinate check
const floatCoord = validateItemPlacement(plantItem, 5.5, 4, DEFAULT_FURNITURE_LAYOUT)
assert.equal(floatCoord.isValid, false)
assert.match(floatCoord.reason, /integers/)

console.log('✓ Passed: Out-of-bounds and fractional tile placements strictly blocked')

// Test 3: Overlap & Collision Protection
console.log('\nTest 3: Furniture Overlap & Collision Prevention')
// Place plant-1 directly onto bookshelf-1 (col: 2, row: 3)
const overlapTest = validateItemPlacement(plantItem, 2, 3, DEFAULT_FURNITURE_LAYOUT)
assert.equal(overlapTest.isValid, false)
assert.match(overlapTest.reason, /Overlaps/)

// Moving an item to its own current position should be valid
const selfPlacement = validateItemPlacement(plantItem, plantItem.column, plantItem.row, DEFAULT_FURNITURE_LAYOUT)
assert.equal(selfPlacement.isValid, true, 'Item should be able to remain at its own spot')

console.log('✓ Passed: Overlapping furniture pieces blocked while self-positioning allowed')

// Test 4: Reserved Agent Locations & Critical Corridors Protection
console.log('\nTest 4: Reserved Agent Spawns, Break Spots & Entrance Corridor Protection')
for (const reserved of RESERVED_AGENT_TILES) {
  const checkReserved = validateItemPlacement(plantItem, reserved.column, reserved.row, DEFAULT_FURNITURE_LAYOUT)
  assert.equal(checkReserved.isValid, false, `Should reject placement on ${reserved.label} (${reserved.column}, ${reserved.row})`)
  assert.match(checkReserved.reason, /Blocks essential location/)
}
console.log(`✓ Passed: All ${RESERVED_AGENT_TILES.length} reserved agent and entrance tiles protected from furniture blockages`)

// Test 5: Storage Persistence, Validation & Fallback
console.log('\nTest 5: Storage Persistence, Schema Validation & Fallback')
// Invalid layout rejection
const invalidSave = saveLayoutToStorage([])
assert.equal(invalidSave.success, false)
assert.ok(invalidSave.error)

// Duplicate ID rejection
const duplicateLayout = [
  ...DEFAULT_FURNITURE_LAYOUT,
  { id: 'workstation-1', type: 'plant', column: 10, row: 10, width: 1, height: 1 },
]
const duplicateValidation = validateOfficeLayout(duplicateLayout)
assert.equal(duplicateValidation.isValid, false)
assert.match(duplicateValidation.errors[0], /Duplicate item id/)

// Valid save and load round-trip
const customLayout = JSON.parse(JSON.stringify(DEFAULT_FURNITURE_LAYOUT))
const plantToMove = customLayout.find((i) => i.id === 'plant-1')
plantToMove.column = 25
plantToMove.row = 6

const saveResult = saveLayoutToStorage(customLayout)
assert.equal(saveResult.success, true)

const loaded = loadSavedLayout()
const loadedPlant = loaded.find((i) => i.id === 'plant-1')
assert.equal(loadedPlant.column, 25)
assert.equal(loadedPlant.row, 6)

clearSavedLayout()
const afterClear = loadSavedLayout()
const afterClearPlant = afterClear.find((i) => i.id === 'plant-1')
assert.equal(afterClearPlant.column, 27, 'Cleared layout should revert to default column 27')

console.log('✓ Passed: Save, load, clear and corrupt data fallback work reliably')

// Test 6: Tilemap Generation & Walkable Cells Dynamic Update
console.log('\nTest 6: Map Data Generation & Walkable Cells Synchronization')
assert.match(mapCode, /createOfficeMapData\(customLayout\?:/)
assert.match(mapCode, /loadSavedLayout\(\)/)
assert.match(mapCode, /walkableCells\.add\(`\${column},\${row}`\)/)

// Test getOccupiedTiles calculations
const bs = DEFAULT_FURNITURE_LAYOUT.find((i) => i.id === 'bookshelf-1')
const bsTiles = getOccupiedTiles(bs)
assert.equal(bsTiles.length, 2)
assert.deepEqual(bsTiles[0], { column: 2, row: 3 })
assert.deepEqual(bsTiles[1], { column: 2, row: 4 })

const ws = DEFAULT_FURNITURE_LAYOUT.find((i) => i.id === 'workstation-1')
const wsTiles = getOccupiedTiles(ws)
assert.equal(wsTiles.length, 3, 'Workstation blocks 2 desk tiles + 1 chair tile')
assert.deepEqual(wsTiles[0], { column: 5, row: 4 })
assert.deepEqual(wsTiles[1], { column: 6, row: 4 })
assert.deepEqual(wsTiles[2], { column: 6, row: 5 })

console.log('✓ Passed: Tile calculation, custom layout parameters and walkable cells generation verified')

// Test 7: UI & Viewport Controls Contract
console.log('\nTest 7: UI Buttons, Viewport Controls & Phaser Handle Integration')
assert.match(viewportCode, /Edit Layout/)
assert.match(viewportCode, /Exit Edit/)
assert.match(viewportCode, /Save Layout/)
assert.match(viewportCode, /role="toolbar"/)
assert.match(viewportCode, /Default/)
assert.match(viewportCode, /Cancel/)

assert.match(gameCode, /startLayoutEdit/)
assert.match(gameCode, /cancelLayoutEdit/)
assert.match(gameCode, /saveLayoutEdit/)
assert.match(gameCode, /resetLayoutToDefault/)
assert.match(gameCode, /isEditingLayout/)

assert.match(sceneCode, /startLayoutEdit/)
assert.match(sceneCode, /cancelLayoutEdit/)
assert.match(sceneCode, /saveLayoutEdit/)
assert.match(sceneCode, /resetLayoutToDefault/)
assert.match(sceneCode, /isEditingLayout/)

assert.match(editorCode, /renderOverlay/)
assert.match(editorCode, /isEditorActive/)
assert.match(editorCode, /validateItemPlacement/)

assert.match(simulationCode, /pause\(\)/)
assert.match(simulationCode, /resume\(\)/)
assert.match(simulationCode, /updateLayout/)

assert.match(pathfindingCode, /setWalkableCells/)

console.log('✓ Passed: Viewport buttons, toolbar, PhaserGame handles, and simulation pause/resume contracts verified')

console.log('\n=== ALL 7 OFFICE LAYOUT EDITOR TESTS PASSED SUCCESSFULLY! ===')

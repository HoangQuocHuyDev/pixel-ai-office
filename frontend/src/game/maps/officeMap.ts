import {
  DEFAULT_FURNITURE_LAYOUT,
  loadSavedLayout,
  type OfficeFurnitureItem,
} from './officeLayout'

export const TILE_SIZE = 32
export const MAP_COLUMNS = 30
export const MAP_ROWS = 18
export const MAP_WIDTH = MAP_COLUMNS * TILE_SIZE
export const MAP_HEIGHT = MAP_ROWS * TILE_SIZE

export const TILE = {
  floor: 0,
  floorAlternate: 1,
  walkway: 2,
  wallTop: 3,
  wallFace: 4,
  door: 5,
  deskLeft: 6,
  deskRight: 7,
  monitor: 8,
  chair: 9,
  plant: 10,
  bookshelf: 11,
  noticeboard: 12,
  cabinet: 13,
  cup: 14,
  waterCooler: 15,
} as const

export const TILE_COUNT = Object.keys(TILE).length

export type WorkstationPosition = {
  id: string
  column: number
  row: number
}

export function getWorkstationPositions(
  layout: readonly OfficeFurnitureItem[] = DEFAULT_FURNITURE_LAYOUT,
): WorkstationPosition[] {
  return layout
    .filter((item) => item.type === 'workstation')
    .map((item) => ({
      id: item.id,
      column: item.column,
      row: item.row,
    }))
}

export const workstationPositions: readonly WorkstationPosition[] = getWorkstationPositions(DEFAULT_FURNITURE_LAYOUT)

export type MeetingSpot = {
  column: number
  row: number
  facing: 'up' | 'down' | 'left' | 'right'
}

export const MEETING_SPOTS: Record<string, MeetingSpot> = {
  manager: { column: 13, row: 5, facing: 'right' },
  developer: { column: 16, row: 5, facing: 'left' },
  researcher: { column: 14, row: 3, facing: 'down' },
}

export type OfficeMapData = {
  floor: number[][]
  walls: number[][]
  furniture: number[][]
  decorations: number[][]
  walkableCells: ReadonlySet<string>
  layout: readonly OfficeFurnitureItem[]
}

function createGrid(value: number): number[][] {
  return Array.from({ length: MAP_ROWS }, () =>
    Array.from({ length: MAP_COLUMNS }, () => value),
  )
}

export function createOfficeMapData(customLayout?: readonly OfficeFurnitureItem[]): OfficeMapData {
  const layout = customLayout ?? loadSavedLayout()
  const floor = createGrid(TILE.floor)
  const walls = createGrid(-1)
  const furniture = createGrid(-1)
  const decorations = createGrid(-1)

  for (let row = 0; row < MAP_ROWS; row += 1) {
    for (let column = 0; column < MAP_COLUMNS; column += 1) {
      floor[row][column] =
        (row + column) % 2 === 0 ? TILE.floor : TILE.floorAlternate
    }
  }

  for (let row = 2; row < MAP_ROWS - 1; row += 1) {
    floor[row][14] = TILE.walkway
    floor[row][15] = TILE.walkway
  }
  for (let column = 1; column < MAP_COLUMNS - 1; column += 1) {
    floor[8][column] = TILE.walkway
    floor[9][column] = TILE.walkway
  }

  for (let column = 0; column < MAP_COLUMNS; column += 1) {
    walls[0][column] = TILE.wallTop
    walls[1][column] = TILE.wallFace
    walls[MAP_ROWS - 1][column] = TILE.wallFace
  }
  for (let row = 2; row < MAP_ROWS - 1; row += 1) {
    walls[row][0] = TILE.wallFace
    walls[row][MAP_COLUMNS - 1] = TILE.wallFace
  }
  walls[MAP_ROWS - 1][14] = TILE.door
  walls[MAP_ROWS - 1][15] = TILE.door

  // Noticeboards along the north wall
  decorations[1][13] = TILE.noticeboard
  decorations[1][14] = TILE.noticeboard

  // Populate furniture and decoration layers from layout items
  for (const item of layout) {
    if (item.type === 'workstation') {
      furniture[item.row][item.column] = TILE.deskLeft
      furniture[item.row][item.column + 1] = TILE.deskRight
      decorations[item.row][item.column] = TILE.monitor
      decorations[item.row][item.column + 1] = TILE.cup
      decorations[item.row + 1][item.column + 1] = TILE.chair
    } else if (item.type === 'bookshelf') {
      for (let r = 0; r < item.height; r += 1) {
        decorations[item.row + r][item.column] = TILE.bookshelf
      }
    } else if (item.type === 'cabinet') {
      for (let r = 0; r < item.height; r += 1) {
        decorations[item.row + r][item.column] = TILE.cabinet
      }
    } else if (item.type === 'waterCooler') {
      decorations[item.row][item.column] = TILE.waterCooler
    } else if (item.type === 'plant') {
      decorations[item.row][item.column] = TILE.plant
    }
  }

  const walkableCells = new Set<string>()
  for (let row = 2; row < MAP_ROWS - 1; row += 1) {
    for (let column = 1; column < MAP_COLUMNS - 1; column += 1) {
      if (furniture[row][column] === -1 && decorations[row][column] === -1) {
        walkableCells.add(`${column},${row}`)
      }
    }
  }

  return { floor, walls, furniture, decorations, walkableCells, layout }
}

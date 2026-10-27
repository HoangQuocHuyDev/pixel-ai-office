export const MAP_COLUMNS = 30
export const MAP_ROWS = 18
export const TILE_SIZE = 32

export type FurnitureType =
  | 'workstation'
  | 'bookshelf'
  | 'cabinet'
  | 'plant'
  | 'waterCooler'

export type OfficeFurnitureItem = {
  id: string
  type: FurnitureType
  column: number
  row: number
  width: number
  height: number
  label?: string
}

export const OFFICE_LAYOUT_STORAGE_KEY = 'pixel_office_layout_v1'

export const DEFAULT_FURNITURE_LAYOUT: readonly OfficeFurnitureItem[] = [
  { id: 'workstation-1', type: 'workstation', column: 5, row: 4, width: 2, height: 2, label: 'Workstation 1' },
  { id: 'workstation-2', type: 'workstation', column: 9, row: 4, width: 2, height: 2, label: 'Manager Desk' },
  { id: 'workstation-3', type: 'workstation', column: 7, row: 11, width: 2, height: 2, label: 'Developer Desk' },
  { id: 'workstation-4', type: 'workstation', column: 19, row: 4, width: 2, height: 2, label: 'Workstation 4' },
  { id: 'workstation-5', type: 'workstation', column: 23, row: 4, width: 2, height: 2, label: 'Workstation 5' },
  { id: 'workstation-6', type: 'workstation', column: 21, row: 11, width: 2, height: 2, label: 'Researcher Desk' },
  { id: 'bookshelf-1', type: 'bookshelf', column: 2, row: 3, width: 1, height: 2, label: 'Bookshelf' },
  { id: 'cabinet-1', type: 'cabinet', column: 26, row: 4, width: 1, height: 2, label: 'Filing Cabinet' },
  { id: 'waterCooler-1', type: 'waterCooler', column: 3, row: 12, width: 1, height: 1, label: 'Water Cooler' },
  { id: 'plant-1', type: 'plant', column: 27, row: 3, width: 1, height: 1, label: 'Plant (East)' },
  { id: 'plant-2', type: 'plant', column: 2, row: 15, width: 1, height: 1, label: 'Plant (Southwest)' },
  { id: 'plant-3', type: 'plant', column: 27, row: 15, width: 1, height: 1, label: 'Plant (Southeast)' },
]

export const RESERVED_AGENT_TILES: ReadonlyArray<{ column: number; row: number; label: string }> = [
  // Spawns
  { column: 14, row: 7, label: 'Manager Spawn' },
  { column: 11, row: 12, label: 'Developer Spawn' },
  { column: 17, row: 12, label: 'Researcher Spawn' },
  // Break spots
  { column: 13, row: 2, label: 'Manager Break Spot' },
  { column: 4, row: 12, label: 'Developer Break Spot' },
  { column: 3, row: 4, label: 'Researcher Break Spot' },
  // Office Entrance corridor
  { column: 14, row: 16, label: 'Entrance Corridor Left' },
  { column: 15, row: 16, label: 'Entrance Corridor Right' },
]

/**
 * Returns all blocked tile coordinates occupied by a furniture item.
 */
export function getOccupiedTiles(item: Pick<OfficeFurnitureItem, 'type' | 'column' | 'row' | 'width' | 'height'>): Array<{ column: number; row: number }> {
  const tiles: Array<{ column: number; row: number }> = []

  if (item.type === 'workstation') {
    // Workstation: Desks at row, chair at row+1, col+1
    tiles.push({ column: item.column, row: item.row })
    tiles.push({ column: item.column + 1, row: item.row })
    tiles.push({ column: item.column + 1, row: item.row + 1 })
    // Note: (item.column, item.row + 1) is the agent's chair/seat spot, kept walkable
  } else {
    for (let r = 0; r < item.height; r += 1) {
      for (let c = 0; c < item.width; c += 1) {
        tiles.push({ column: item.column + c, row: item.row + r })
      }
    }
  }

  return tiles
}

export type ValidationResult = {
  isValid: boolean
  errors: string[]
}

/**
 * Validates a single furniture item's placement against the map boundaries,
 * reserved agent positions, and other furniture items.
 */
export function validateItemPlacement(
  item: OfficeFurnitureItem,
  targetCol: number,
  targetRow: number,
  allItems: readonly OfficeFurnitureItem[],
): { isValid: boolean; reason?: string } {
  // 1. Integer grid coordinates check
  if (!Number.isInteger(targetCol) || !Number.isInteger(targetRow)) {
    return { isValid: false, reason: 'Coordinates must be integers' }
  }

  // 2. Map playable bounds check (walls at row 0, 1, 17 and col 0, 29)
  const minCol = 1
  const maxCol = MAP_COLUMNS - 2
  const minRow = 2
  const maxRow = MAP_ROWS - 2

  if (targetCol < minCol || targetCol + item.width - 1 > maxCol) {
    return { isValid: false, reason: 'Furniture extends outside office horizontal walls' }
  }
  if (targetRow < minRow || targetRow + item.height - 1 > maxRow) {
    return { isValid: false, reason: 'Furniture extends outside office vertical walls' }
  }

  // 3. Occupied tiles for the candidate position
  const candidateOccupied = getOccupiedTiles({
    type: item.type,
    column: targetCol,
    row: targetRow,
    width: item.width,
    height: item.height,
  })

  // 4. Check collision with reserved agent tiles
  for (const occ of candidateOccupied) {
    for (const res of RESERVED_AGENT_TILES) {
      if (occ.column === res.column && occ.row === res.row) {
        return { isValid: false, reason: `Blocks essential location: ${res.label}` }
      }
    }
  }

  // 5. Check collision / overlap with other furniture items
  for (const other of allItems) {
    if (other.id === item.id) continue

    const otherOccupied = getOccupiedTiles(other)
    for (const occ of candidateOccupied) {
      for (const oOcc of otherOccupied) {
        if (occ.column === oOcc.column && occ.row === oOcc.row) {
          return { isValid: false, reason: `Overlaps with ${other.label ?? other.id}` }
        }
      }
    }
  }

  return { isValid: true }
}

/**
 * Validates an entire office layout configuration.
 */
export function validateOfficeLayout(layout: unknown): ValidationResult {
  const errors: string[] = []

  if (!Array.isArray(layout) || layout.length === 0) {
    return { isValid: false, errors: ['Layout must be a non-empty array of furniture items'] }
  }

  const ids = new Set<string>()
  const validTypes = new Set<FurnitureType>(['workstation', 'bookshelf', 'cabinet', 'plant', 'waterCooler'])

  for (let i = 0; i < layout.length; i += 1) {
    const item = layout[i] as OfficeFurnitureItem
    if (!item || typeof item !== 'object') {
      errors.push(`Item at index ${i} is not a valid object`)
      continue
    }

    if (!item.id || typeof item.id !== 'string') {
      errors.push(`Item at index ${i} has invalid id`)
      continue
    }

    if (ids.has(item.id)) {
      errors.push(`Duplicate item id: "${item.id}"`)
    }
    ids.add(item.id)

    if (!validTypes.has(item.type)) {
      errors.push(`Item "${item.id}" has invalid type "${item.type}"`)
    }

    // Validate placement against previous items
    const previousItems = layout.slice(0, i) as OfficeFurnitureItem[]
    const placement = validateItemPlacement(item, item.column, item.row, previousItems)
    if (!placement.isValid) {
      errors.push(`Item "${item.id}" placement invalid: ${placement.reason}`)
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
  }
}

let memoryStorage: Record<string, string> = {}

function getStorage(): { getItem: (k: string) => string | null; setItem: (k: string, v: string) => void; removeItem: (k: string) => void } {
  try {
    if (typeof globalThis !== 'undefined' && globalThis.localStorage) {
      return globalThis.localStorage
    }
  } catch {
    // Fall back to memory
  }
  return {
    getItem: (key: string) => memoryStorage[key] ?? null,
    setItem: (key: string, val: string) => { memoryStorage[key] = val },
    removeItem: (key: string) => { delete memoryStorage[key] },
  }
}

/**
 * Loads the saved office layout from localStorage, falling back to DEFAULT_FURNITURE_LAYOUT.
 */
export function loadSavedLayout(): OfficeFurnitureItem[] {
  try {
    const storage = getStorage()
    const raw = storage.getItem(OFFICE_LAYOUT_STORAGE_KEY)
    if (!raw) {
      return JSON.parse(JSON.stringify(DEFAULT_FURNITURE_LAYOUT))
    }

    const parsed = JSON.parse(raw)
    const validation = validateOfficeLayout(parsed)
    if (!validation.isValid) {
      console.warn('Saved office layout was corrupted or invalid. Falling back to default:', validation.errors)
      return JSON.parse(JSON.stringify(DEFAULT_FURNITURE_LAYOUT))
    }

    return parsed as OfficeFurnitureItem[]
  } catch (err) {
    console.warn('Failed to read saved layout from localStorage:', err)
    return JSON.parse(JSON.stringify(DEFAULT_FURNITURE_LAYOUT))
  }
}

/**
 * Saves the given layout to localStorage after validation.
 */
export function saveLayoutToStorage(layout: OfficeFurnitureItem[]): { success: boolean; error?: string } {
  const validation = validateOfficeLayout(layout)
  if (!validation.isValid) {
    return {
      success: false,
      error: validation.errors[0] ?? 'Invalid layout configuration',
    }
  }

  try {
    const storage = getStorage()
    storage.setItem(OFFICE_LAYOUT_STORAGE_KEY, JSON.stringify(layout))
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Unable to write to storage',
    }
  }
}

/**
 * Clears the saved layout from storage, reverting to default.
 */
export function clearSavedLayout(): void {
  try {
    const storage = getStorage()
    storage.removeItem(OFFICE_LAYOUT_STORAGE_KEY)
    memoryStorage = {}
  } catch {
    // Ignore storage clear errors
  }
}

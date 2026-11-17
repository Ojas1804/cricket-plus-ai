export interface KeyValueStore {
  get<T>(key: string): Promise<T | undefined>
  set(key: string, value: unknown): Promise<void>
  delete(key: string): Promise<void>
}

export function createMemoryStore(initial: Record<string, unknown> = {}): KeyValueStore & { data: Map<string, unknown>; writes: number } {
  const data = new Map<string, unknown>(Object.entries(initial))
  const store = {
    data,
    writes: 0,
    async get<T>(key: string) { return data.get(key) as T | undefined },
    async set(key: string, value: unknown) { store.writes++; data.set(key, structuredClone(value)) },
    async delete(key: string) { data.delete(key) },
  }
  return store
}

const STORE = 'kv'

function openDb(name: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(name, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export function createIdbStore(dbName = 'cricket-canvas'): KeyValueStore {
  let db: Promise<IDBDatabase> | null = null
  const run = async <T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> => {
    db ??= openDb(dbName)
    const conn = await db
    return new Promise<T>((resolve, reject) => {
      const req = fn(conn.transaction(STORE, mode).objectStore(STORE))
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    })
  }
  return {
    get: <T>(key: string) => run<T | undefined>('readonly', (s) => s.get(key)),
    set: async (key, value) => { await run('readwrite', (s) => s.put(value, key)) },
    delete: async (key) => { await run('readwrite', (s) => s.delete(key)) },
  }
}

export function createDefaultStore(): KeyValueStore {
  return typeof indexedDB === 'undefined' ? createMemoryStore() : createIdbStore()
}

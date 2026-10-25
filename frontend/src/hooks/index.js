/** Data-fetching and UI hooks shared across pages. */
import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../lib/api'

/**
 * Fetch-on-mount with loading/error/refetch. Deliberately small — the app has
 * no server-state library, and every page needs exactly these three states.
 */
export function useApi(fetcher, deps = [], { enabled = true, initial = null } = {}) {
  const [data, setData] = useState(initial)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = useCallback(async () => {
    if (!enabled) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await fetcher()
      if (mounted.current) setData(result)
    } catch (err) {
      if (mounted.current) setError(err)
    } finally {
      if (mounted.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])

  useEffect(() => {
    run()
  }, [run])

  return { data, loading, error, refetch: run, setData }
}

/**
 * Poll an evaluation run until it leaves the queued/running states.
 * Backs off from 1s to 4s so a long run doesn't hammer the API.
 */
export function useRunPolling(runId, { enabled = true, onComplete } = {}) {
  const [run, setRun] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(Boolean(runId && enabled))
  const completedRef = useRef(false)

  useEffect(() => {
    if (!runId || !enabled) return undefined
    let cancelled = false
    let timer
    let interval = 1000
    completedRef.current = false

    const tick = async () => {
      try {
        const payload = await api.run(runId)
        if (cancelled) return
        setRun(payload)
        setLoading(false)
        if (payload.status === 'completed' || payload.status === 'failed') {
          if (!completedRef.current) {
            completedRef.current = true
            onComplete?.(payload)
          }
          return
        }
        interval = Math.min(interval * 1.25, 4000)
        timer = setTimeout(tick, interval)
      } catch (err) {
        if (cancelled) return
        setError(err)
        setLoading(false)
      }
    }

    tick()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, enabled])

  return { run, loading, error }
}

/** Theme state persisted to localStorage, applied as a class on <html>. */
export function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light'
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
  })

  const apply = useCallback((next) => {
    setTheme(next)
    document.documentElement.classList.toggle('dark', next === 'dark')
    try {
      localStorage.setItem('evalhub-theme', next)
    } catch {
      /* storage unavailable — theme still applies for this session */
    }
  }, [])

  return { theme, setTheme: apply, toggle: () => apply(theme === 'dark' ? 'light' : 'dark') }
}

/** Debounce a rapidly-changing value (search boxes). */
export function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** Persisted local state, used for run selections on the compare page. */
export function useLocalState(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw ? JSON.parse(raw) : initial
    } catch {
      return initial
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* ignore */
    }
  }, [key, value])
  return [value, setValue]
}

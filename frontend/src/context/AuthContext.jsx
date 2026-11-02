import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [workspaces, setWorkspaces] = useState([])
  const [currentWorkspace, setCurrentWorkspaceState] = useState(null)
  const [isLocalMode, setIsLocalMode] = useState(true)
  const [isAuthEnabled, setIsAuthEnabled] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const setCurrentWorkspace = (workspaceOrId) => {
    let ws = null
    if (typeof workspaceOrId === 'string') {
      ws = workspaces.find((w) => w.id === workspaceOrId) || null
    } else {
      ws = workspaceOrId
    }
    if (ws) {
      localStorage.setItem('evalhub_active_workspace', ws.id)
      setCurrentWorkspaceState(ws)
    }
  }

  const loadProfile = async () => {
    try {
      const modeData = await api.authMode()
      setIsLocalMode(modeData.mode === 'local')
      setIsAuthEnabled(Boolean(modeData.is_auth_enabled))

      if (!modeData.is_auth_enabled) {
        // Local mode
        setUser({
          id: 'usr_default',
          email: 'local@evalhub.local',
          full_name: 'Local Developer',
          is_superuser: true,
        })
        const wsList = await api.workspaces().catch(() => [])
        setWorkspaces(wsList)
        const savedWsId = localStorage.getItem('evalhub_active_workspace')
        const active = wsList.find((w) => w.id === savedWsId) || wsList[0] || {
          id: 'wks_default',
          name: 'Default Workspace',
          current_user_role: 'owner',
        }
        setCurrentWorkspaceState(active)
      } else {
        // Auth enabled mode
        const token = localStorage.getItem('evalhub_access_token')
        if (token) {
          const profile = await api.me()
          setUser(profile.user)
          setWorkspaces(profile.workspaces || [])
          const savedWsId = localStorage.getItem('evalhub_active_workspace')
          const active =
            profile.workspaces.find((w) => w.id === savedWsId) ||
            profile.workspaces[0] ||
            null
          if (active) {
            localStorage.setItem('evalhub_active_workspace', active.id)
            setCurrentWorkspaceState(active)
          }
        } else {
          setUser(null)
          setWorkspaces([])
          setCurrentWorkspaceState(null)
        }
      }
    } catch (err) {
      console.warn('Failed to resolve auth profile:', err)
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadProfile()

    const handleLogoutEvent = () => {
      setUser(null)
      setWorkspaces([])
      setCurrentWorkspaceState(null)
    }
    window.addEventListener('evalhub:logout', handleLogoutEvent)
    return () => window.removeEventListener('evalhub:logout', handleLogoutEvent)
  }, [])

  const login = async ({ email, password }) => {
    const tokens = await api.login({ email, password })
    localStorage.setItem('evalhub_access_token', tokens.access_token)
    localStorage.setItem('evalhub_refresh_token', tokens.refresh_token)
    await loadProfile()
    return tokens
  }

  const register = async ({ email, password, full_name }) => {
    const newUser = await api.register({ email, password, full_name })
    // Automatically log in after registration
    return login({ email, password })
  }

  const logout = async () => {
    const refreshToken = localStorage.getItem('evalhub_refresh_token')
    if (refreshToken) {
      await api.logout({ refresh_token: refreshToken }).catch(() => {})
    }
    localStorage.removeItem('evalhub_access_token')
    localStorage.removeItem('evalhub_refresh_token')
    localStorage.removeItem('evalhub_active_workspace')
    setUser(null)
    setWorkspaces([])
    setCurrentWorkspaceState(null)
    window.location.href = isAuthEnabled ? '/login' : '/'
  }

  const role = isLocalMode
    ? 'owner'
    : currentWorkspace?.current_user_role || (user?.is_superuser ? 'owner' : 'viewer')

  return (
    <AuthContext.Provider
      value={{
        user,
        workspaces,
        currentWorkspace,
        setCurrentWorkspace,
        role,
        isLocalMode,
        isAuthEnabled,
        isLoading,
        login,
        register,
        logout,
        reloadProfile: loadProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}

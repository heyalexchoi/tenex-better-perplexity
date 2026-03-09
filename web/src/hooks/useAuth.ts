import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "../lib/api"

const LOCAL_AUTH_KEY = "bp_auth_token"

export function useAuth() {
  const [authToken, setAuthToken] = useState<string>("")
  const [authChecked, setAuthChecked] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)

  const checkAuth = useCallback(async (token: string, showErrors = true) => {
    setAuthError(null)
    const res = await apiFetch("/api/auth/check", {
      method: "POST",
      headers: token ? { "x-auth": token } : {},
    })

    if (res.ok) {
      setAuthToken(token)
      if (token) {
        localStorage.setItem(LOCAL_AUTH_KEY, token)
      } else {
        localStorage.removeItem(LOCAL_AUTH_KEY)
      }
      setAuthChecked(true)
      return true
    }

    if (showErrors) {
      setAuthError("Password incorrect. Try again.")
    }
    setAuthChecked(false)
    return false
  }, [])

  useEffect(() => {
    const saved = localStorage.getItem(LOCAL_AUTH_KEY) ?? ""
    if (!saved) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAuthChecked(false)
      setAuthError(null)
      return
    }
    void checkAuth(saved, false)
  }, [checkAuth])

  return {
    authToken,
    authChecked,
    authError,
    checkAuth,
  }
}

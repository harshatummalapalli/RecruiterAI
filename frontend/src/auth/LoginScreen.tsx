import { useState } from 'react'
import { GoogleLogin, type CredentialResponse } from '@react-oauth/google'
import { API_BASE_URL } from '../services/recruiterWorkflow'
import './LoginScreen.css'

type LoginScreenProps = {
  onSuccess: () => void
}

export function LoginScreen({ onSuccess }: LoginScreenProps) {
  const [error, setError] = useState<string | null>(null)

  const handleGoogleSuccess = async (credentialResponse: CredentialResponse) => {
    setError(null)
    if (!credentialResponse.credential) {
      setError('Sign-in did not return a credential. Please try again.')
      return
    }

    try {
      const response = await fetch(`${API_BASE_URL}/auth/google`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: credentialResponse.credential }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null
        setError(body?.detail || 'Sign-in failed. Please try again.')
        return
      }

      onSuccess()
    } catch {
      setError('Could not reach the server. Please try again.')
    }
  }

  return (
    <div className="login-screen">
      <div className="login-screen__card">
        <h1 className="login-screen__title">RecruiterAI</h1>
        <p className="login-screen__subtitle">Sign in with your company Google account to continue.</p>
        <GoogleLogin onSuccess={handleGoogleSuccess} onError={() => setError('Sign-in failed. Please try again.')} />
        {error ? <p className="login-screen__error">{error}</p> : null}
      </div>
    </div>
  )
}

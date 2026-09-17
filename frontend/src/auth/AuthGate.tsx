import { useEffect, useState, type ReactNode } from 'react'
import { GoogleOAuthProvider } from '@react-oauth/google'
import { checkSession } from '../services/recruiterWorkflow'
import { LoginScreen } from './LoginScreen'

type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated'

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? ''

type AuthGateProps = {
  children: ReactNode
}

export function AuthGate({ children }: AuthGateProps) {
  const [status, setStatus] = useState<AuthStatus>('checking')

  useEffect(() => {
    let cancelled = false
    checkSession().then((authenticated) => {
      if (!cancelled) {
        setStatus(authenticated ? 'authenticated' : 'unauthenticated')
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      {status === 'checking' ? null : status === 'authenticated' ? children : (
        <LoginScreen onSuccess={() => setStatus('authenticated')} />
      )}
    </GoogleOAuthProvider>
  )
}

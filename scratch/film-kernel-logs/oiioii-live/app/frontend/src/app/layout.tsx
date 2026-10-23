import type { ReactNode } from 'react'
import './globals.css'

// This retained layout is framework-neutral; the deployed app uses Vite.
export default function RootLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-dark-950 text-dark-100">{children}</div>
}

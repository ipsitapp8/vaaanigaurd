import { createContext, useContext, useState, type ReactNode } from 'react'

export type Role = 'user' | 'analyst'
const KEY = 'vg_role'

function read(): Role {
  try { return localStorage.getItem(KEY) === 'analyst' ? 'analyst' : 'user' } catch { return 'user' }
}

const Ctx = createContext<{ role: Role; setRole: (r: Role) => void }>({ role: 'user', setRole: () => undefined })

/** Demo-only role switch. Production would use bank IAM/SSO + RBAC. */
export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(read)
  const setRole = (r: Role) => {
    setRoleState(r)
    try { localStorage.setItem(KEY, r) } catch { /* storage unavailable: keep in memory */ }
  }
  return <Ctx.Provider value={{ role, setRole }}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useRole = () => useContext(Ctx)

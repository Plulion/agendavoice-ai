import { FormEvent, useEffect, useState } from 'react'
import { api, getToken, saveTokens, clearTokens } from './services/api'

type Row = {
  id: number
  name: string
  phone?: string
  duration_minutes?: number
  price?: number
  currency?: string
  timezone?: string
  status?: string
  starts_at?: string
}

export default function App() {
  const [token, setToken] = useState(getToken())
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('admin@salon-demo.cl')
  const [password, setPassword] = useState('')
  const [company, setCompany] = useState('Salón Demo')
  const [admin, setAdmin] = useState('Administración')
  const [notice, setNotice] = useState('')
  const [me, setMe] = useState<any>(null)
  const [branches, setBranches] = useState<Row[]>([])
  const [services, setServices] = useState<Row[]>([])
  const [customers, setCustomers] = useState<Row[]>([])
  const [appointments, setAppointments] = useState<Row[]>([])

  const canAdmin = ['SUPER_ADMIN', 'TENANT_ADMIN'].includes(me?.role)

  async function refresh() {
    try {
      const [profile, b, s, c, a] = await Promise.all([
        api('/me'),
        api('/branches'),
        api('/services'),
        api('/customers'),
        api('/appointments?from_at=' + encodeURIComponent(new Date().toISOString())),
      ])
      setMe(profile)
      setBranches(b)
      setServices(s)
      setCustomers(c)
      setAppointments(a)
    } catch (e: any) {
      setNotice(e.message)
    }
  }

  useEffect(() => {
    if (token) refresh()
  }, [token])

  useEffect(() => {
    const expired = () => {
      setToken('')
      setMe(null)
      setNotice('La sesión expiró. Vuelve a ingresar.')
    }
    window.addEventListener('agv:session-expired', expired)
    return () => window.removeEventListener('agv:session-expired', expired)
  }, [])

  function switchMode(mode: 'login' | 'register') {
    setAuthMode(mode)
    setNotice('')
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setNotice('')
    if (authMode === 'register' && password.length < 12) {
      setNotice('La contraseña debe tener al menos 12 caracteres.')
      return
    }
    try {
      const data =
        authMode === 'register'
          ? await api('/auth/register', 'POST', {
              company_name: company,
              admin_name: admin,
              email,
              password,
            })
          : await api('/auth/login', 'POST', { email, password })
      saveTokens(data)
      setToken(data.access_token)
      setPassword('')
      setNotice(authMode === 'register' ? 'Empresa creada y sesión iniciada.' : 'Sesión iniciada.')
    } catch (err: any) {
      setNotice(err.message)
    }
  }

  async function logout() {
    try {
      const refresh_token = sessionStorage.getItem('agv_refresh_token')
      if (refresh_token) await api('/auth/logout', 'POST', { refresh_token }, false)
    } catch {}
    clearTokens()
    setToken('')
    setMe(null)
    setAuthMode('login')
    setNotice('')
  }

  async function addBranch() {
    const name = prompt('Nombre de la sucursal')
    if (!name) return
    try {
      await api('/branches', 'POST', { name, timezone: 'America/Santiago' })
      await refresh()
    } catch (e: any) {
      setNotice(e.message)
    }
  }

  async function addService() {
    const name = prompt('Servicio (ej. Corte de cabello)')
    if (!name) return
    try {
      await api('/services', 'POST', {
        name,
        duration_minutes: 30,
        buffer_minutes: 0,
        price: 12000,
        currency: 'CLP',
      })
      await refresh()
    } catch (e: any) {
      setNotice(e.message)
    }
  }

  return (
    <main>
      <header>
        <div className="logo">AV</div>
        <div>
          <h1>AgendaVoice AI</h1>
          <p>SaaS universal · Consola de administración R5.0.3</p>
        </div>
        <span className="tag">LOCAL · R5.0.3</span>
      </header>

      <section className="hero">
        <div>
          <span className="eyebrow">AGENDA INTELIGENTE PARA NEGOCIOS</span>
          <h2>Tu recepción, siempre disponible.</h2>
          <p>
            Administra sucursales, servicios, clientes y reservas desde una plataforma multiempresa.
          </p>
        </div>
        <div className="hero-mark">✦</div>
      </section>

      {!token ? (
        <section className="panel auth">
          <div className="tabs" role="tablist">
            <button
              type="button"
              className={`tab ${authMode === 'login' ? 'active' : ''}`}
              onClick={() => switchMode('login')}
            >
              Ingresar
            </button>
            <button
              type="button"
              className={`tab ${authMode === 'register' ? 'active' : ''}`}
              onClick={() => switchMode('register')}
            >
              Crear empresa
            </button>
          </div>

          <h3>{authMode === 'login' ? 'Inicia sesión en tu cuenta' : 'Registra una nueva empresa'}</h3>

          <form onSubmit={handleSubmit}>
            {authMode === 'register' && (
              <>
                <label>
                  Empresa
                  <input
                    required
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                  />
                </label>
                <label>
                  Nombre administrador
                  <input
                    required
                    value={admin}
                    onChange={(e) => setAdmin(e.target.value)}
                  />
                </label>
              </>
            )}

            <label>
              Correo
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>

            <label>
              {authMode === 'register' ? 'Contraseña · mínimo 12 caracteres' : 'Contraseña'}
              <input
                type="password"
                required
                minLength={authMode === 'register' ? 12 : 1}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>

            <div className="actions">
              <button type="submit" className="full">
                {authMode === 'login' ? 'Ingresar' : 'Crear empresa'}
              </button>
            </div>
          </form>
        </section>
      ) : (
        <>
          <section className="welcome">
            <div>
              <span className="eyebrow">ESPACIO DE TRABAJO</span>
              <h2>{me?.company || 'Tu empresa'}</h2>
              <p>
                {me?.email} · {me?.role}
              </p>
            </div>
            <button className="secondary" onClick={logout}>
              Cerrar sesión
            </button>
          </section>

          <section className="stats">
            <article>
              <b>{branches.length}</b>
              <span>Sucursales</span>
            </article>
            <article>
              <b>{services.length}</b>
              <span>Servicios</span>
            </article>
            <article>
              <b>{customers.length}</b>
              <span>Clientes</span>
            </article>
            <article>
              <b>{appointments.length}</b>
              <span>Reservas</span>
            </article>
          </section>

          <section className="grid">
            <div className="panel">
              <div className="panel-head">
                <h3>Sucursales</h3>
                {canAdmin && <button onClick={addBranch}>+ Agregar</button>}
              </div>
              {branches.length ? (
                branches.map((x) => (
                  <p className="item" key={x.id}>
                    {x.name}
                    <small>{x.timezone}</small>
                  </p>
                ))
              ) : (
                <p className="muted">Aún no hay sucursales.</p>
              )}
            </div>

            <div className="panel">
              <div className="panel-head">
                <h3>Servicios</h3>
                {canAdmin && <button onClick={addService}>+ Agregar</button>}
              </div>
              {services.length ? (
                services.map((x) => (
                  <p className="item" key={x.id}>
                    {x.name}
                    <small>
                      {x.duration_minutes} min ·{' '}
                      {new Intl.NumberFormat('es-CL', {
                        style: 'currency',
                        currency: x.currency || 'CLP',
                      }).format(x.price || 0)}
                    </small>
                  </p>
                ))
              ) : (
                <p className="muted">Aún no hay servicios.</p>
              )}
            </div>

            <div className="panel wide">
              <div className="panel-head">
                <h3>Próximas reservas</h3>
                <button className="secondary" onClick={refresh}>
                  Actualizar
                </button>
              </div>
              {appointments.length ? (
                appointments.map((x) => (
                  <p className="item" key={x.id}>
                    Reserva #{x.id}
                    <small>
                      {new Date(x.starts_at!).toLocaleString('es-CL')} · {x.status}
                    </small>
                  </p>
                ))
              ) : (
                <p className="muted">Las reservas aparecerán aquí cuando se creen mediante la API.</p>
              )}
            </div>
          </section>
        </>
      )}

      {notice && <p className="notice">{notice}</p>}
      <footer>
        AgendaVoice AI 5.0.3 · Núcleo SaaS en desarrollo. No utilizar con datos reales ni exponer a
        Internet.
      </footer>
    </main>
  )
}

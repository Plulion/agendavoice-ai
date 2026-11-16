const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ACCESS_KEY = 'agv_access_token'
const REFRESH_KEY = 'agv_refresh_token'
const SESSION_CHANNEL = 'agv-session'
// Tras rotar, la pestaña espera un momento antes de decidir que un 401 es robo (ver renewSession).
const ADOPT_WAIT_MS = 300
let refreshInFlight: Promise<boolean> | null = null

type TokenPair = { access_token: string; refresh_token: string }

const channel: BroadcastChannel | null =
  typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(SESSION_CHANNEL) : null

// Otra pestaña del mismo origen rotó el refresh token que esta también tiene (p. ej. una pestaña
// duplicada). Solo se adopta si el token coincide con el antiguo, para no mezclar sesiones.
channel?.addEventListener('message', (event: MessageEvent) => {
  const msg = event.data
  if (msg?.type === 'rotated' && sessionStorage.getItem(REFRESH_KEY) === msg.old) {
    sessionStorage.setItem(ACCESS_KEY, msg.access_token)
    sessionStorage.setItem(REFRESH_KEY, msg.refresh_token)
  }
})

export function getToken(){ return sessionStorage.getItem(ACCESS_KEY) || '' }

export function saveTokens(data: TokenPair){
  localStorage.removeItem('agv_token')
  sessionStorage.setItem(ACCESS_KEY, data.access_token)
  sessionStorage.setItem(REFRESH_KEY, data.refresh_token)
}

export function clearTokens(){
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem('agv_token') // Limpieza del token usado por R4.0
}

function expireSession(){
  clearTokens()
  window.dispatchEvent(new Event('agv:session-expired'))
  return false
}

async function renewSession():Promise<boolean>{
  if(refreshInFlight) return refreshInFlight
  refreshInFlight=(async()=>{
    // Dentro del lock se lee el token de nuevo: si otra pestaña ya rotó, se usa el nuevo.
    const renew = async (attempt = 0): Promise<boolean> => {
      const refresh_token = sessionStorage.getItem(REFRESH_KEY)
      if(!refresh_token) return expireSession()
      const response = await fetch(`${API}/auth/refresh`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ refresh_token }),
      })
      if(!response.ok){
        if(attempt === 0){
          // Puede ser una renovación concurrente: esperar la adopción y reintentar una vez.
          await new Promise(resolve => setTimeout(resolve, ADOPT_WAIT_MS))
          if(sessionStorage.getItem(REFRESH_KEY) !== refresh_token) return renew(1)
        }
        return expireSession()
      }
      const data: TokenPair = await response.json()
      saveTokens(data)
      channel?.postMessage({ type: 'rotated', old: refresh_token,
        access_token: data.access_token, refresh_token: data.refresh_token })
      return true
    }
    const locks = (navigator as any).locks
    try{
      return locks ? await locks.request('agv-refresh', () => renew()) : await renew()
    }catch{
      return expireSession()
    }finally{
      refreshInFlight=null
    }
  })()
  return refreshInFlight
}

export async function api(path:string, method='GET', body?:unknown, retry=true){
  const token=getToken()
  const response=await fetch(`${API}${path}`,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},...(body!==undefined?{body:JSON.stringify(body)}:{})})
  if(response.status===401 && retry && path!=='/auth/login' && path!=='/auth/register' && path!=='/auth/refresh'){
    if(await renewSession()) return api(path,method,body,false)
  }
  const payload=await response.json().catch(()=>({detail:'Respuesta no válida del servidor'}))
  if(!response.ok) throw new Error(payload.detail || `Error HTTP ${response.status}`)
  return payload
}

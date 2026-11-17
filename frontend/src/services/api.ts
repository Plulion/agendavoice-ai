const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ACCESS_KEY = 'agv_access_token'
const REFRESH_KEY = 'agv_refresh_token'
const SESSION_CHANNEL = 'agv-session'
// Wait window after rotation before treating a 401 as token replay/theft (see renewSession).
const ADOPT_WAIT_MS = 300
let refreshInFlight: Promise<boolean> | null = null

type TokenPair = { access_token: string; refresh_token: string }

const channel: BroadcastChannel | null =
  typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(SESSION_CHANNEL) : null

// Another tab from the same origin rotated the refresh token shared by this tab.
// Only adopt the new pair if the previous token matches to avoid mixing distinct sessions.
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
  localStorage.removeItem('agv_token') // Clean up legacy R4.0 token key
}

function expireSession(){
  clearTokens()
  window.dispatchEvent(new Event('agv:session-expired'))
  return false
}

async function renewSession():Promise<boolean>{
  if(refreshInFlight) return refreshInFlight
  refreshInFlight=(async()=>{
    // Re-read the token inside the lock: if another tab already rotated it, use the updated token.
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
          // Potential concurrent tab refresh: wait briefly for BroadcastChannel adoption and retry once.
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
  const payload=await response.json().catch(()=>({detail:'Invalid server response'}))
  if(!response.ok) throw new Error(payload.detail || `HTTP Error ${response.status}`)
  return payload
}

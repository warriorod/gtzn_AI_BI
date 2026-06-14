import { useUserStore } from '@/store/business/userStore'

const BASE_URL = `${location.origin}/sanic/system/data-training`

const getHeaders = () => {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

export const trainingApi = {
  getList: (pageNum: number, pageSize: number, params: any) => {
    const url = new URL(`${BASE_URL}/page/${pageNum}/${pageSize}`)
    // Append query params
    if (params) {
        Object.keys(params).forEach(key => {
            if (params[key] !== undefined && params[key] !== null && params[key] !== '') {
                url.searchParams.append(key, params[key])
            }
        })
    }
    const req = new Request(url, {
      mode: 'cors',
      method: 'get',
      headers: getHeaders(),
    })
    return fetch(req)
  },
  
  updateEmbedded: (data: any) => {
    const url = new URL(`${BASE_URL}/`)
    const req = new Request(url, {
      mode: 'cors',
      method: 'put',
      headers: getHeaders(),
      body: JSON.stringify(data)
    })
    return fetch(req)
  },
  
  deleteEmbedded: (params: any) => {
    const url = new URL(`${BASE_URL}/`)
    const req = new Request(url, {
      mode: 'cors',
      method: 'delete',
      headers: getHeaders(),
      body: JSON.stringify(params)
    })
    return fetch(req)
  },
  
  getOne: (id: any) => {
     // Not used in current view but keeping for compatibility
     // This endpoint was not defined in my backend controller, but I'll leave it as is or remove if not needed.
     // I'll skip implementation or implement if I added the endpoint. 
     // I didn't add getOne in controller.
     return Promise.resolve()
  },
  
  enable: (id: any, enabled: any) => {
    const url = new URL(`${BASE_URL}/${id}/enable/${enabled}`)
    const req = new Request(url, {
      mode: 'cors',
      method: 'get',
      headers: getHeaders(),
    })
    return fetch(req)
  }
}

import { useUserStore } from '@/store/business/userStore'

const BASE_URL = `${location.origin}/sanic/terminology`

const getHeaders = () => {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

/**
 * 分页查询术语
 */
export async function queryTerminologyList(page: number, size: number, word?: string, dslist?: number[]) {
  const url = new URL(`${BASE_URL}/list`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify({ page, size, word, dslist }),
  })
  return fetch(req)
}

/**
 * 保存术语 (新增/修改)
 */
export async function saveTerminology(data: any) {
  const url = new URL(`${BASE_URL}/save`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  return fetch(req)
}

/**
 * 删除术语
 */
export async function deleteTerminology(ids: number[]) {
  const url = new URL(`${BASE_URL}/delete`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify({ ids }),
  })
  return fetch(req)
}

/**
 * 启用/禁用术语
 */
export async function enableTerminology(id: number, enabled: boolean) {
  // 1 for true, 0 for false because backend expects int in url path <enabled:int>
  // But wait, my backend definition is: @bp.get("/<id:int>/enable/<enabled:int>")
  // So I should pass 1 or 0.
  const enabledInt = enabled ? 1 : 0
  const url = new URL(`${BASE_URL}/${id}/enable/${enabledInt}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: getHeaders(),
  })
  return fetch(req)
}

/**
 * 获取术语详情
 */
export async function getTerminologyDetail(id: number) {
  const url = new URL(`${BASE_URL}/${id}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: getHeaders(),
  })
  return fetch(req)
}

/**
 * AI生成同义词
 */
export async function generateSynonyms(word: string) {
  const url = new URL(`${BASE_URL}/generate_synonyms`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify({ word }),
  })
  return fetch(req)
}

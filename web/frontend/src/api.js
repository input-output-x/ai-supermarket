import axios from 'axios'

const api = axios.create({
  baseURL: '/',
  timeout: 120000,
})

export function getHealth() {
  return api.get('/api/health')
}

export function getLegacyVideo() {
  return api.get('/api/legacy-video')
}

export function listVideos() {
  return api.get('/api/videos')
}

export function getVideo(id) {
  return api.get(`/api/videos/${id}`)
}

export function createVideo(formData) {
  return api.post('/api/videos', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function downloadVideo(id, type = 'video') {
  return api.get(`/api/videos/${id}/download?type=${type}`, { responseType: 'blob' })
}

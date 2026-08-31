<template>
  <div class="studio">
    <section class="card legacy">
      <h2>保留成片</h2>
      <p>这是之前用 Agent 链路跑出来的原始成片，仍保留在仓库外 output/ 目录。</p>
      <video v-if="legacyUrl" :src="legacyUrl" controls preload="metadata" class="video-player"></video>
    </section>

    <section class="card generator">
      <h2>生成新口播视频</h2>
      <div class="form">
        <label>
          <span>上传图片（人物/动物/任何形象）</span>
          <input type="file" accept="image/*" @change="onFileChange" />
          <img v-if="previewUrl" :src="previewUrl" class="preview" alt="preview" />
        </label>

        <label>
          <span>口播稿</span>
          <textarea v-model="form.script" rows="5" placeholder="输入想让图片里的人物说的口播稿..."></textarea>
        </label>

        <div class="row">
          <label>
            <span>标题（可选）</span>
            <input v-model="form.title" placeholder="默认取前 30 字" />
          </label>
          <label>
            <span>音色</span>
            <select v-model="form.voice">
              <option value="zh-CN-XiaoxiaoNeural">晓晓（女声）</option>
              <option value="zh-CN-YunxiNeural">云希（男声）</option>
              <option value="zh-CN-XiaoyiNeural">晓伊（女声）</option>
              <option value="zh-CN-YunjianNeural">云健（男声）</option>
            </select>
          </label>
          <label>
            <span>Provider</span>
            <select v-model="form.provider">
              <option value="local">本地 fallback</option>
              <option value="heygen">HeyGen（需 key）</option>
            </select>
          </label>
        </div>

        <button :disabled="!canSubmit || generating" @click="submit">
          {{ generating ? '生成中...' : '一键生成口播视频' }}
        </button>

        <div v-if="currentJob" class="status">
          <p>状态：<strong>{{ statusText(currentJob.status) }}</strong></p>
          <p v-if="currentJob.message" class="msg">{{ currentJob.message }}</p>
        </div>

        <video v-if="resultVideoUrl" :src="resultVideoUrl" controls class="video-player result"></video>
      </div>
    </section>

    <section class="card history">
      <h2>历史记录</h2>
      <ul v-if="jobs.length">
        <li v-for="job in jobs" :key="job.id">
          <span>#{{ job.id }} {{ job.title }}</span>
          <span :class="['badge', job.status]">{{ statusText(job.status) }}</span>
          <button v-if="job.status === 'done'" @click="play(job)">播放</button>
        </li>
      </ul>
      <p v-else>暂无记录</p>
      <video v-if="selectedVideo" :src="selectedVideo" controls class="video-player result"></video>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getLegacyVideo, createVideo, getVideo, listVideos } from '../api.js'

const form = ref({
  script: '大家好，我是 AI 超市的虚拟主播。只需要一张图和一段口播稿，就能生成这样的短视频。快来试试吧！',
  title: '',
  voice: 'zh-CN-XiaoxiaoNeural',
  provider: 'local',
})
const file = ref(null)
const previewUrl = ref('')
const generating = ref(false)
const currentJob = ref(null)
const resultVideoUrl = ref('')
const jobs = ref([])
const legacyUrl = ref('')
const selectedVideo = ref('')
let pollTimer = null

const canSubmit = computed(() => file.value && form.value.script.trim())

function onFileChange(e) {
  const f = e.target.files[0]
  if (!f) return
  file.value = f
  previewUrl.value = URL.createObjectURL(f)
}

function statusText(s) {
  const map = { pending: '排队中', doing: '生成中', done: '已完成', failed: '失败' }
  return map[s] || s
}

async function submit() {
  if (!canSubmit.value) return
  generating.value = true
  currentJob.value = null
  resultVideoUrl.value = ''
  const data = new FormData()
  data.append('image', file.value)
  data.append('script', form.value.script)
  data.append('voice', form.value.voice)
  data.append('provider', form.value.provider)
  if (form.value.title) data.append('title', form.value.title)
  try {
    const { data: job } = await createVideo(data)
    currentJob.value = job
    startPolling(job.id)
    loadJobs()
  } catch (e) {
    alert('提交失败：' + (e.response?.data?.detail || e.message))
    generating.value = false
  }
}

function startPolling(id) {
  clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const { data: job } = await getVideo(id)
      currentJob.value = job
      if (job.status === 'done' || job.status === 'failed') {
        clearInterval(pollTimer)
        generating.value = false
        if (job.video_path) {
          resultVideoUrl.value = '/videos/' + job.video_path.split('/videos/').pop()
        }
        loadJobs()
      }
    } catch (e) {
      console.error(e)
    }
  }, 2000)
}

function play(job) {
  if (job.video_path) {
    selectedVideo.value = '/videos/' + job.video_path.split('/videos/').pop()
  }
}

async function loadJobs() {
  const { data } = await listVideos()
  jobs.value = data
}

onMounted(async () => {
  try {
    const { data } = await getLegacyVideo()
    legacyUrl.value = data.stream_url
  } catch (e) {
    console.log('legacy video not found', e)
  }
  loadJobs()
})

onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.studio {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.card {
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.card h2 { margin-top: 0; font-size: 18px; }
.form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
  color: #374151;
}
input, textarea, select {
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
}
textarea { resize: vertical; }
.row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 12px;
}
button {
  align-self: flex-start;
  padding: 12px 24px;
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 15px;
}
button:disabled { background: #93c5fd; cursor: not-allowed; }
.preview {
  max-width: 200px;
  max-height: 200px;
  border-radius: 8px;
  margin-top: 8px;
  object-fit: cover;
}
.video-player {
  width: 100%;
  max-width: 360px;
  border-radius: 12px;
  margin-top: 12px;
  background: #111;
}
.status { color: #4b5563; }
.status .msg { color: #6b7280; font-size: 13px; }
.history ul { list-style: none; padding: 0; margin: 0; }
.history li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #e5e7eb;
}
.badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
}
.badge.pending { background: #fef3c7; color: #92400e; }
.badge.doing { background: #dbeafe; color: #1e40af; }
.badge.done { background: #d1fae5; color: #065f46; }
.badge.failed { background: #fee2e2; color: #991b1b; }
</style>

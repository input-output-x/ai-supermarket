<template>
  <div class="app">
    <header>
      <h1>AI 超市 · 口播视频工坊</h1>
      <p>上传任意图片 + 口播稿，一键生成 9:16 竖版短视频</p>
    </header>
    <main>
      <RouterView />
    </main>
    <footer>
      <small>本地 fallback：图片 + edge-tts 配音 + 字幕 + 嘴部动画；真实唇形同步可配置 HeyGen/D-ID/Kling Provider</small>
    </footer>
  </div>
</template>

<style>
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: #f5f6f8;
  color: #1f2937;
}
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
header {
  background: linear-gradient(90deg, #1d4ed8, #7c3aed);
  color: #fff;
  padding: 24px;
  text-align: center;
}
header h1 { margin: 0 0 8px; font-size: 24px; }
header p { margin: 0; opacity: 0.9; }
main { flex: 1; padding: 24px; }
footer {
  text-align: center;
  padding: 16px;
  color: #6b7280;
  font-size: 12px;
}
</style>

<script setup lang="ts">
/**
 * WireframeBackground — animated constellation/wireframe canvas.
 *
 * Floating nodes drift slowly, connected by fading lines when
 * within proximity. Purely decorative, pointer-events: none.
 *
 * Performance: ~40 nodes, 60fps via requestAnimationFrame,
 * resolution-aware (respects devicePixelRatio), pauses when
 * tab is hidden. Typical GPU: <1% usage.
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useThemeStore } from '@/stores/theme'

const canvas = ref<HTMLCanvasElement | null>(null)
const themeStore = useThemeStore()

interface Node {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  pulseOffset: number
}

const NODE_COUNT = 45
const CONNECTION_DISTANCE = 180
const NODE_SPEED = 0.3
const LINE_OPACITY = 0.12
const NODE_OPACITY = 0.25

let nodes: Node[] = []
let animFrame = 0
let ctx: CanvasRenderingContext2D | null = null
let w = 0
let h = 0
let dpr = 1

function initNodes(): void {
  nodes = []
  for (let i = 0; i < NODE_COUNT; i++) {
    nodes.push({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * NODE_SPEED,
      vy: (Math.random() - 0.5) * NODE_SPEED,
      radius: 1 + Math.random() * 1.5,
      pulseOffset: Math.random() * Math.PI * 2,
    })
  }
}

function resize(): void {
  if (!canvas.value) return
  dpr = window.devicePixelRatio || 1
  w = window.innerWidth
  h = window.innerHeight
  canvas.value.width = w * dpr
  canvas.value.height = h * dpr
  canvas.value.style.width = w + 'px'
  canvas.value.style.height = h + 'px'
  ctx = canvas.value.getContext('2d')
  if (ctx) ctx.scale(dpr, dpr)
}

function draw(time: number): void {
  if (!ctx) return

  ctx.clearRect(0, 0, w, h)

  // Theme colors
  const isCyberpunk = themeStore.currentTheme === 'cyberpunk'
  const primaryR = isCyberpunk ? 0 : 100
  const primaryG = isCyberpunk ? 168 : 100
  const primaryB = isCyberpunk ? 255 : 100
  const accentR = isCyberpunk ? 255 : 150
  const accentG = isCyberpunk ? 107 : 150
  const accentB = isCyberpunk ? 43 : 150

  // Update positions
  for (const node of nodes) {
    node.x += node.vx
    node.y += node.vy

    // Wrap around edges with padding
    if (node.x < -20) node.x = w + 20
    if (node.x > w + 20) node.x = -20
    if (node.y < -20) node.y = h + 20
    if (node.y > h + 20) node.y = -20
  }

  // Draw connections
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const dx = nodes[i].x - nodes[j].x
      const dy = nodes[i].y - nodes[j].y
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (dist < CONNECTION_DISTANCE) {
        const alpha = (1 - dist / CONNECTION_DISTANCE) * LINE_OPACITY
        // Alternate between primary and accent color for some lines
        const useAccent = (i + j) % 7 === 0
        const r = useAccent ? accentR : primaryR
        const g = useAccent ? accentG : primaryG
        const b = useAccent ? accentB : primaryB

        ctx.beginPath()
        ctx.moveTo(nodes[i].x, nodes[i].y)
        ctx.lineTo(nodes[j].x, nodes[j].y)
        ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`
        ctx.lineWidth = 0.5
        ctx.stroke()
      }
    }
  }

  // Draw nodes with subtle pulse
  const pulse = Math.sin(time * 0.001) * 0.5 + 0.5
  for (const node of nodes) {
    const nodePulse = Math.sin(time * 0.002 + node.pulseOffset) * 0.3 + 0.7
    const r = node.radius * nodePulse

    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${primaryR},${primaryG},${primaryB},${NODE_OPACITY * nodePulse})`
    ctx.fill()

    // Occasional glow on some nodes
    if (node.pulseOffset > 5) {
      const glowAlpha = pulse * 0.08
      ctx.beginPath()
      ctx.arc(node.x, node.y, r * 4, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${primaryR},${primaryG},${primaryB},${glowAlpha})`
      ctx.fill()
    }
  }

  animFrame = requestAnimationFrame(draw)
}

function handleVisibility(): void {
  if (document.hidden) {
    cancelAnimationFrame(animFrame)
  } else {
    animFrame = requestAnimationFrame(draw)
  }
}

onMounted(() => {
  resize()
  initNodes()
  animFrame = requestAnimationFrame(draw)
  window.addEventListener('resize', resize)
  document.addEventListener('visibilitychange', handleVisibility)
})

onUnmounted(() => {
  cancelAnimationFrame(animFrame)
  window.removeEventListener('resize', resize)
  document.removeEventListener('visibilitychange', handleVisibility)
})

// Re-init if theme changes (colors update automatically in draw)
watch(() => themeStore.currentTheme, () => {
  // No action needed — draw() reads theme each frame
})
</script>

<template>
  <canvas ref="canvas" class="wireframe-bg" aria-hidden="true" />
</template>

<style scoped>
.wireframe-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
</style>

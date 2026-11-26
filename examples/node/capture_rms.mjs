// Run after building bindings/node:
//   node examples/node/capture_rms.mjs
import { SystemLoopback } from '../../bindings/node/dist/index.js';

const lb = new SystemLoopback();
console.log(`Backend: ${lb.backend} | ${lb.sampleRate}Hz | ${lb.channels}ch`);

const timer = setInterval(() => {
  const pcm = lb.readF32(4800);
  if (pcm.length === 0) return;
  let sum = 0;
  for (let i = 0; i < pcm.length; i += 1) sum += pcm[i] * pcm[i];
  const rms = Math.sqrt(sum / pcm.length);
  const bar = '#'.repeat(Math.min(40, Math.floor(rms * 200)));
  console.log(`frames=${String(pcm.length).padStart(4)}  rms=${rms.toFixed(4)}  |${bar}`);
}, 50);

setTimeout(() => {
  clearInterval(timer);
  lb.close();
}, 3000);

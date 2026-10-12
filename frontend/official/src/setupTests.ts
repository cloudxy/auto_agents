// jsdom 环境补齐（E0.3 工单 06）：react-router v7 与 antd 6 的运行时依赖
import { TextEncoder, TextDecoder } from 'util';
import { configure } from '@testing-library/dom'

// 并行负载下 findBy* 默认 1s 超时易抖动：全局放宽到 8s（waitFor 语义不变）
configure({ asyncUtilTimeout: 8000 })

// 缺失的全局对象经 Object.assign 挂到 globalThis（jest-environment-jsdom 下即 global / window）
if (typeof globalThis.TextEncoder === 'undefined') {
  Object.assign(globalThis, { TextEncoder });
}
if (typeof globalThis.TextDecoder === 'undefined') {
  Object.assign(globalThis, { TextDecoder });
}

interface SimpleMessagePort {
  onmessage: ((event: { data: unknown }) => void) | null;
  postMessage: (data: unknown) => void;
}

// @rc-component/form 的宏任务调度依赖 MessageChannel（jsdom 未实现）。
// 不能用 worker_threads：句柄会吊住 jest。也不能 setTimeout(0)：antd 6
// Form/Modal 会灌满宏任务队列，waitFor/Jest 超时器饿死。
if (typeof globalThis.MessageChannel === 'undefined') {
  class SimpleMessageChannel {
    port1: SimpleMessagePort = { onmessage: null, postMessage: () => undefined };
    port2: SimpleMessagePort = { onmessage: null, postMessage: () => undefined };
    constructor() {
      this.port1.postMessage = (data) =>
        queueMicrotask(() => this.port2.onmessage?.({ data }))
      this.port2.postMessage = (data) =>
        queueMicrotask(() => this.port1.onmessage?.({ data }))
    }
  }
  Object.assign(globalThis, { MessageChannel: SimpleMessageChannel });
}

// framer-motion 的 whileInView 动画依赖 IntersectionObserver（jsdom 未实现）
if (typeof globalThis.IntersectionObserver === 'undefined') {
  Object.assign(globalThis, { IntersectionObserver: class {
    root = null;
    rootMargin = '';
    thresholds: number[] = [];
    observe() { return undefined; }
    unobserve() { return undefined; }
    disconnect() { return undefined; }
    takeRecords() { return []; }
  } });
}

// antd / rc-component 依赖 window.matchMedia（jsdom 未实现）
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

// antd / rc-component 依赖 ResizeObserver（jsdom 未实现）
if (typeof globalThis.ResizeObserver === 'undefined') {
  Object.assign(globalThis, { ResizeObserver: class {
    observe() { return undefined; }
    unobserve() { return undefined; }
    disconnect() { return undefined; }
  } });
}

// jsdom 不实现滚动 API，antd 抽屉/弹层渲染时会触发
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => undefined;
}

// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

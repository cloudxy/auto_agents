// jsdom 环境补齐（E0.3 工单 06）：react-router v7 与 antd 6 的运行时依赖
import { TextEncoder, TextDecoder } from 'util';

if (typeof (global as any).TextEncoder === 'undefined') {
  (global as any).TextEncoder = TextEncoder;
}
if (typeof (global as any).TextDecoder === 'undefined') {
  (global as any).TextDecoder = TextDecoder;
}

// @rc-component/form 的宏任务调度依赖 MessageChannel（jsdom 未实现；
// 不能用 worker_threads 的实现——其句柄会吊住 jest 进程，故以 setTimeout stub）
if (typeof (global as any).MessageChannel === 'undefined') {
  (global as any).MessageChannel = class SimpleMessageChannel {
    port1 = { onmessage: null as any, postMessage: (_data: any) => undefined };
    port2 = { onmessage: null as any, postMessage: (_data: any) => undefined };
    constructor() {
      this.port1.postMessage = (data: any) =>
        setTimeout(() => this.port2.onmessage?.({ data }), 0);
      this.port2.postMessage = (data: any) =>
        setTimeout(() => this.port1.onmessage?.({ data }), 0);
    }
  };
}

// framer-motion 的 whileInView 动画依赖 IntersectionObserver（jsdom 未实现）
if (typeof (global as any).IntersectionObserver === 'undefined') {
  (global as any).IntersectionObserver = class {
    root = null;
    rootMargin = '';
    thresholds: number[] = [];
    observe() { return undefined; }
    unobserve() { return undefined; }
    disconnect() { return undefined; }
    takeRecords() { return []; }
  };
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
if (typeof (global as any).ResizeObserver === 'undefined') {
  (global as any).ResizeObserver = class {
    observe() { return undefined; }
    unobserve() { return undefined; }
    disconnect() { return undefined; }
  };
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

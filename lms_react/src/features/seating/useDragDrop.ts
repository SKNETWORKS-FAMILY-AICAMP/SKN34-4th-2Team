import { useCallback, useRef, useState, type DragEvent } from 'react';

/**
 * 끌어다 놓기 — Flutter의 Draggable/DragTarget 자리.
 *
 * 브라우저 기본 드래그를 쓴다. 끄는 동안 무엇을 끄는지는 `dataTransfer`에 싣지
 * 않고 여기 보관한다. `dragover` 중에는 브라우저가 실은 값을 읽지 못하게 막아서,
 * 받을 수 있는 칸만 밝히려면 값을 손에 쥐고 있어야 한다.
 */
export function useDragDrop<P>() {
  const payloadRef = useRef<P | null>(null);
  const [dragging, setDragging] = useState<P | null>(null);
  const [over, setOver] = useState<string | null>(null);

  const end = useCallback(() => {
    payloadRef.current = null;
    setDragging(null);
    setOver(null);
  }, []);

  /** 끌 수 있는 것에 붙인다. */
  const source = (payload: P) => ({
    draggable: true,
    onDragStart: (e: DragEvent) => {
      e.stopPropagation();
      e.dataTransfer.effectAllowed = 'move';
      // 파이어폭스는 무언가 실어야 드래그를 시작한다.
      e.dataTransfer.setData('text/plain', '');
      payloadRef.current = payload;
      // 드래그가 시작된 뒤에 다시 그린다. 시작하는 순간 모양을 바꾸면 크롬이 드래그를 취소한다.
      window.setTimeout(() => setDragging(payload), 0);
    },
    onDragEnd: end,
  });

  /** 놓을 수 있는 곳에 붙인다. `accept`가 거짓이면 놓이지 않는다. */
  const target = (key: string, accept: (p: P) => boolean, onDrop: (p: P) => void) => ({
    onDragOver: (e: DragEvent) => {
      const p = payloadRef.current;
      if (p === null || !accept(p)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      setOver((cur) => (cur === key ? cur : key));
    },
    onDragLeave: (e: DragEvent) => {
      if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
      setOver((cur) => (cur === key ? null : cur));
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      const p = payloadRef.current;
      end();
      if (p !== null && accept(p)) onDrop(p);
    },
  });

  return { dragging, over, source, target };
}
